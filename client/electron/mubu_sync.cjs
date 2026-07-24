/**
 * 幕布文档同步模块（Electron 主进程侧）
 * ================================================
 * 核心原理：
 *   1. 用独立 BrowserWindow 加载 mubu.com，用户登录一次后 cookie 由 Electron session 持久化
 *   2. 后台定时用 webContents.executeJavaScript() 在 mubu 页面上下文里调用 mubu 自己的 fetch API
 *   3. 拿到文档列表 + 正文后，通过 HTTP POST 推给本地 Flask /api/mubu/ingest
 *   4. Flask 入库到 mubu_docs 表，供 AI 日报 / MCP / 前端查询使用
 *
 * 关键设计：
 *   - cookie 持久化：用 partition 'persist:mubu'，Electron 自动保存到 userData
 *   - 无头同步：同步窗口隐藏，不干扰用户
 *   - 渐进式拉取：先拉列表（轻量），再按需拉正文（重量）
 *   - 错误恢复：cookie 失效时通过事件总线通知前端弹登录窗口
 */
const { BrowserWindow, session, app } = require('electron')
const path = require('path')
const http = require('http')

const MUBU_URL = 'https://mubu.com/'
const MUBU_LIST_URL = 'https://mubu.com/list'
const MUBU_LOGIN_URL = 'https://mubu.com/login'
const PARTITION = 'persist:mubu'
const SYNC_INTERVAL_MS = 30 * 60 * 1000  // 30 分钟同步一次（全量同步耗时更长）

let _loginWindow = null
let _syncWindow = null
let _syncTimer = null
let _isSyncing = false
let _onStatusChange = null  // 状态变化回调（通知前端）

// 后端 HTTP 配置（与 main.cjs 共享）
const BACKEND_PORT = 58888
const BACKEND_HOST = '127.0.0.1'

// ─── 读取后端 token（用于推数据给 Flask）────────────
let _backendToken = ''
let _userDataPath = ''

function setBackendConfig(token, userDataPath) {
  _backendToken = token
  _userDataPath = userDataPath
}

function _readTokenFromDisk() {
  try {
    const fs = require('fs')
    const tokenPath = path.join(_userDataPath, 'backend-data', '.api_token')
    if (fs.existsSync(tokenPath)) {
      return fs.readFileSync(tokenPath, 'utf-8').trim()
    }
  } catch (e) {
    console.error('[MubuSync] read token failed:', e)
  }
  return ''
}

// ─── 从 Electron session 获取 mubu cookie（用于 Node.js 端 API 调用）──
async function _getMubuCookies() {
  try {
    const ses = session.fromPartition(PARTITION)
    const cookies = await ses.cookies.get({ domain: 'mubu.com' })
    return cookies.map(c => `${c.name}=${c.value}`).join('; ')
  } catch (e) {
    console.error('[MubuSync] get cookies failed:', e?.message || String(e))
    return ''
  }
}

// 从 cookie 中提取 token 值（mubu 可能在 cookie 中存 token）
async function _getMubuToken() {
  try {
    const ses = session.fromPartition(PARTITION)
    const cookies = await ses.cookies.get({ domain: 'mubu.com' })
    // 找 token / _token / mubu_token / sessionId 等
    for (const c of cookies) {
      const n = c.name.toLowerCase()
      if (n === 'token' || n === '_token' || n === 'mubu_token' || n === 'auth_token' || n === 'session_token') {
        return c.value
      }
    }
    // 也尝试从 localStorage 获取（需要 BrowserWindow）
  } catch (e) {}
  return ''
}

// 从 BrowserWindow 的 localStorage 中获取 token
async function _getMubuTokenFromStorage() {
  try {
    const win = _getSyncWindow(false)
    if (!win || win.isDestroyed()) return ''
    const token = await win.webContents.executeJavaScript(`
      (function() {
        // 尝试从 localStorage 各个 key 中提取 token
        const keys = ['token', '_token', 'mubu_token', 'auth_token', 'accessToken', 'access_token'];
        for (const k of keys) {
          const v = localStorage.getItem(k);
          if (v) return v;
        }
        // 尝试从 sessionStorage 获取
        for (const k of keys) {
          const v = sessionStorage.getItem(k);
          if (v) return v;
        }
        // 尝试从 window 全局对象获取
        try {
          if (window.__INITIAL_STATE__?.user?.token) return window.__INITIAL_STATE__.user.token;
          if (window.g_config?.token) return window.g_config.token;
        } catch (e) {}
        return '';
      })()
    `, true)
    return token || ''
  } catch (e) {
    return ''
  }
}

// ─── Node.js 端直接调用幕布 v3 API（绕过浏览器 CORS 限制）──
const https = require('https')

function _mubuApiPost(pathname, bodyObj, cookieStr, extraHeaders) {
  return new Promise((resolve, reject) => {
    const bodyStr = JSON.stringify(bodyObj)
    const headers = {
      'Content-Type': 'application/json',
      'Cookie': cookieStr,
      'Origin': 'https://mubu.com',
      'Referer': 'https://mubu.com/',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      'Content-Length': Buffer.byteLength(bodyStr),
    }
    if (extraHeaders) Object.assign(headers, extraHeaders)
    const req = https.request({
      hostname: 'api2.mubu.com',
      port: 443,
      path: pathname,
      method: 'POST',
      headers,
    }, (res) => {
      let data = ''
      res.on('data', (chunk) => { data += chunk })
      res.on('end', () => {
        try { resolve({ ok: res.statusCode === 200, code: res.statusCode, data: JSON.parse(data) }) }
        catch (e) { resolve({ ok: false, code: res.statusCode, data: null, raw: data.slice(0, 500) }) }
      })
    })
    req.on('error', reject)
    req.write(bodyStr)
    req.end()
  })
}

// ─── Node.js 端全量拉取文档列表（v3 API 翻页）──
// 经诊断：正确 body 是空 {} 或 {start: next_start_value}
// 响应结构：{code:0, data:{documents:[...], folders:[...], next_start:"...", root_relation:"..."}}
// 字段映射：id→doc_id, folderId→parent_id, name→title, type=5→doc, updateTime→edit_time
async function _fetchAllDocsViaNodeApi(cookieStr, authToken, capturedHeaders, capturedBody) {
  const allDocs = []
  const seenIds = new Set()
  const MAX_PAGES = 20  // 每页 ~966 篇，2 页就够
  const MAX_DOCS = 5000

  // 构建额外 headers：优先用捕获的 SPA headers，再补充 Jwt-Token（从 cookie 提取）
  const extraHeaders = {}
  if (capturedHeaders && typeof capturedHeaders === 'object') {
    Object.assign(extraHeaders, capturedHeaders)
  }
  // 从 cookie 中提取 Jwt-Token 作为 header（关键：v3 API 必须有 Jwt-Token header）
  if (cookieStr) {
    const m = cookieStr.match(/(?:^|;\s*)Jwt-Token=([^;]+)/)
    if (m && m[1] && !extraHeaders['Jwt-Token'] && !extraHeaders['jwt-token']) {
      extraHeaders['Jwt-Token'] = m[1]
    }
    const cm = cookieStr.match(/(?:^|;\s*)csrf_token=([^;]+)/)
    if (cm && cm[1]) {
      if (!extraHeaders['x-csrf-token']) extraHeaders['x-csrf-token'] = cm[1]
      if (!extraHeaders['x-mubu-csrf-token']) extraHeaders['x-mubu-csrf-token'] = cm[1]
    }
  }
  if (authToken) {
    if (!extraHeaders['Authorization']) extraHeaders['Authorization'] = 'Bearer ' + authToken
    if (!extraHeaders['Jwt-Token']) extraHeaders['Jwt-Token'] = authToken
  }

  // 提取文档（v3 API 字段：id, folderId, name, type, updateTime, itemCount）
  function extractDoc(d) {
    const docId = String(d.id || d.doc_id || d._id || '')
    if (!docId) return null
    const rawType = d.type
    // 幕布 type: 5=doc, 其他可能是 folder/特殊类型
    const isFolder = rawType !== undefined && rawType !== 5 && rawType !== '5' && rawType !== 'doc'
    return {
      doc_id: docId,
      title: String(d.name || d.title || d.fileName || ''),
      parent_id: String(d.folderId || d.parent_id || d.parentId || ''),
      type: isFolder ? 'folder' : 'doc',
      edit_time: Number(d.updateTime || d.edit_time || d.updated_at || 0),
      url: d.url || '',
      item_count: Number(d.itemCount || 0),
    }
  }

  // 翻页：第 1 页用空 body，后续用 {start: next_start}
  let nextStart = null
  let debugLogged = false
  for (let page = 1; page <= MAX_PAGES && allDocs.length < MAX_DOCS; page++) {
    const bodyObj = nextStart ? { start: nextStart } : {}
    const r = await _mubuApiPost('/v3/api/list/get_all_documents_page', bodyObj, cookieStr, extraHeaders)

    if (!debugLogged) {
      debugLogged = true
      try {
        const dataKeys = r.data?.data ? Object.keys(r.data.data) : []
        const docCount = Array.isArray(r.data?.data?.documents) ? r.data.data.documents.length : 0
        console.log('[MubuSync] list API page1: ok=' + r.ok + ' httpCode=' + r.code + ' dataCode=' + (r.data?.code) + ' msg=' + (r.data?.msg || '') + ' dataKeys=' + dataKeys.join(',') + ' docs=' + docCount)
      } catch (e) {}
    }

    if (!r.ok || !r.data || (r.data.code !== undefined && r.data.code !== 0)) {
      console.log('[MubuSync] list API page=' + page + ' failed: ok=' + r.ok + ' code=' + r.code + ' dataCode=' + (r.data?.code) + ' msg=' + (r.data?.msg || ''))
      break
    }

    const data = r.data.data || {}
    const docs = Array.isArray(data.documents) ? data.documents : []
    if (docs.length === 0) {
      console.log('[MubuSync] page=' + page + ' no documents, stop')
      break
    }

    let newCount = 0
    for (const d of docs) {
      if (allDocs.length >= MAX_DOCS) break
      const doc = extractDoc(d)
      if (!doc || seenIds.has(doc.doc_id)) continue
      seenIds.add(doc.doc_id)
      allDocs.push(doc)
      newCount++
    }
    console.log('[MubuSync] page=' + page + ' got ' + docs.length + ' docs (new=' + newCount + ', total=' + allDocs.length + ')')

    // 翻页 cursor：data.next_start 是字符串如 '{"index":1000,"seq":"..."}'
    nextStart = data.next_start || null
    if (!nextStart) {
      console.log('[MubuSync] no next_start, pagination done. total=' + allDocs.length)
      break
    }
  }

  return { ok: allDocs.length > 0, docs: allDocs, folderIds: [] }
}

// ─── HTTP POST 到本地 Flask ────────────────────────
function _postToBackend(apiPath, body) {
  return new Promise((resolve, reject) => {
    const token = _backendToken || _readTokenFromDisk()
    const bodyStr = JSON.stringify(body)
    const req = http.request({
      hostname: BACKEND_HOST,
      port: BACKEND_PORT,
      path: apiPath,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Token': token,
        'Content-Length': Buffer.byteLength(bodyStr),
      },
    }, (res) => {
      let data = ''
      res.on('data', (chunk) => { data += chunk })
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) })
        } catch (e) {
          resolve({ status: res.statusCode, body: data })
        }
      })
    })
    req.on('error', reject)
    req.write(bodyStr)
    req.end()
  })
}

function _getFromBackend(apiPath) {
  return new Promise((resolve, reject) => {
    const token = _backendToken || _readTokenFromDisk()
    const req = http.request({
      hostname: BACKEND_HOST,
      port: BACKEND_PORT,
      path: apiPath,
      method: 'GET',
      headers: { 'X-API-Token': token },
    }, (res) => {
      let data = ''
      res.on('data', (chunk) => { data += chunk })
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data) })
        } catch (e) {
          resolve({ status: res.statusCode, body: data })
        }
      })
    })
    req.on('error', reject)
    req.end()
  })
}

// ─── 登录窗口（用户可见）────────────────────────
function showLoginWindow() {
  console.log('[MubuSync] showLoginWindow called')
  if (_loginWindow && !_loginWindow.isDestroyed()) {
    console.log('[MubuSync] login window already exists, focusing')
    _loginWindow.focus()
    return
  }

  try {
    const mubuSession = session.fromPartition(PARTITION)
    _loginWindow = new BrowserWindow({
      width: 1000,
      height: 700,
      parent: null,
      title: '登录幕布 - ChallengeDaily',
      alwaysOnTop: true,
      webPreferences: {
        partition: PARTITION,
        contextIsolation: true,
        nodeIntegration: false,
      },
    })

    console.log('[MubuSync] login window created, loading', MUBU_LOGIN_URL)
    _loginWindow.show()
    _loginWindow.focus()
    _loginWindow.loadURL(MUBU_LOGIN_URL)
    _loginWindow.on('closed', () => { _loginWindow = null })

    _loginWindow.webContents.on('did-finish-load', () => {
      console.log('[MubuSync] login window finished loading, url:', _loginWindow?.webContents?.getURL?.())
    })
    _loginWindow.webContents.on('did-fail-load', (_e, code, desc) => {
      console.error('[MubuSync] login window failed to load:', code, desc)
    })

    // 监听 URL 变化，登录成功后自动关闭并触发首次同步
    _loginWindow.webContents.on('did-navigate', (event, url) => {
      console.log('[MubuSync] login window navigated to:', url)
      // 登录成功后通常会跳到 /list 或 /
      if (url.includes('mubu.com') && !url.includes('login')) {
        setTimeout(() => {
          if (_loginWindow && !_loginWindow.isDestroyed()) {
            _loginWindow.close()
          }
          // 触发首次同步
          startSync()
        }, 1500)
      }
    })
  } catch (e) {
    console.error('[MubuSync] showLoginWindow error:', e?.message || String(e), e?.stack || '')
  }
}

// ─── 同步窗口（隐藏，用于执行 JS）────────────────
function _getSyncWindow(reload = false) {
  if (_syncWindow && !_syncWindow.isDestroyed()) {
    if (reload) {
      // 重新加载前先注册拦截器（在 dom-ready 时注入）
      _setupInterceptor(_syncWindow)
      _syncWindow.loadURL(MUBU_LIST_URL)
    }
    return _syncWindow
  }

  _syncWindow = new BrowserWindow({
    show: false,
    width: 1200,
    height: 800,
    webPreferences: {
      partition: PARTITION,
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'mubu_preload.cjs'),
    },
  })

  _setupInterceptor(_syncWindow)
  _syncWindow.loadURL(MUBU_LIST_URL)
  _syncWindow.on('closed', () => { _syncWindow = null })

  return _syncWindow
}

// ─── 检查 cookie 是否有效 ────────────────────────
async function checkCookieValid(reload = false) {
  try {
    const win = _getSyncWindow(reload)
    // 等待页面加载完成
    await _waitForLoad(win)
    // 注入 JS：检查是否已登录（未登录会跳转到 /login）
    const result = await win.webContents.executeJavaScript(`
      (async () => {
        // mubu 未登录会跳转到 /login，登录后停在 /list
        const url = window.location.href
        if (url.includes('/login') || url.includes('/loginByPhone')) {
          return { valid: false, reason: 'redirected to login', url }
        }
        // 尝试调一次列表 API 验证 cookie
        try {
          const resp = await fetch('/api/document/list', {
            method: 'GET',
            credentials: 'include',
          })
          if (resp.ok) {
            return { valid: true, url }
          }
          return { valid: false, reason: 'api returned ' + resp.status, url }
        } catch (e) {
          return { valid: false, reason: e.message, url }
        }
      })()
    `, true)
    return result
  } catch (e) {
    return { valid: false, reason: 'executeJavaScript failed: ' + e.message }
  }
}

function _waitForLoad(win) {
  return new Promise((resolve) => {
    if (win.webContents.isLoading() === false) {
      resolve()
      return
    }
    win.webContents.once('did-finish-load', () => resolve())
    // 超时兜底
    setTimeout(resolve, 8000)
  })
}

// ─── 拉取文档列表 ────────────────────────────────

// 拦截器注入脚本（在 dom-ready 时注入，确保在 SPA JS 之前执行）
const _INTERCEPTOR_SCRIPT = `
  (function() {
    if (window.__mubuInterceptor) return;
    window.__mubuInterceptor = { responses: [], requestInfo: [] };
    const origFetch = window.fetch;
    window.fetch = async function(...args) {
      try {
        const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
        const reqInit = args[1] || {};
        // 记录所有 mubu 相关 API 请求（不限于 v3 API）
        if (url.includes('mubu.com') || url.includes('/api/') || url.includes('/v3/api/')) {
          // 序列化 headers（可能是对象或 Headers 实例）
          let hdrs = {};
          try {
            const h = reqInit.headers;
            if (h) {
              if (typeof h.forEach === 'function') {
                h.forEach((v, k) => { hdrs[k] = v; });
              } else if (h instanceof Object) {
                hdrs = Object.assign({}, h);
              }
            }
          } catch (e) {}
          window.__mubuInterceptor.requestInfo.push({
            url, method: reqInit.method || 'GET',
            headers: hdrs,
            body: (reqInit.body || '').toString().slice(0, 500),
            credentials: reqInit.credentials || '',
          });
        }
      } catch (e) {}
      const resp = await origFetch.apply(this, args);
      try {
        const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
        if (url.includes('/api/') || url.includes('document') || url.includes('file') || url.includes('note') || url.includes('list')) {
          const clone = resp.clone();
          const ct = clone.headers.get('content-type') || '';
          if (ct.includes('json')) {
            const data = await clone.json();
            window.__mubuInterceptor.responses.push({ url, data, time: Date.now() });
          }
        }
      } catch (e) {}
      return resp;
    };
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url) {
      this.__mubuUrl = url;
      this.__mubuMethod = method;
      this.__mubuReqHeaders = {};
      // 拦截 setRequestHeader 记录自定义 header
      const origSetHeader = this.setRequestHeader.bind(this);
      this.setRequestHeader = function(k, v) {
        try { this.__mubuReqHeaders[k] = v; } catch (e) {}
        return origSetHeader(k, v);
      };
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(body) {
      try {
        if (this.__mubuUrl && (this.__mubuUrl.includes('mubu.com') || this.__mubuUrl.includes('/api/') || this.__mubuUrl.includes('/v3/api/'))) {
          window.__mubuInterceptor.requestInfo.push({
            url: this.__mubuUrl,
            method: this.__mubuMethod || 'GET',
            headers: Object.assign({}, this.__mubuReqHeaders || {}),
            body: (body || '').toString().slice(0, 500),
            isXHR: true,
          });
        }
      } catch (e) {}
      this.addEventListener('load', function() {
        try {
          if (this.__mubuUrl && (this.__mubuUrl.includes('/api/') || this.__mubuUrl.includes('document') || this.__mubuUrl.includes('list'))) {
            const data = JSON.parse(this.responseText);
            window.__mubuInterceptor.responses.push({ url: this.__mubuUrl, data, time: Date.now() });
          }
        } catch (e) {}
      });
      return origSend.apply(this, arguments);
    };
  })()
`

function _setupInterceptor(win) {
  // 在 dom-ready 时注入拦截器（在 SPA JS 运行之前）
  win.webContents.once('dom-ready', () => {
    win.webContents.executeJavaScript(_INTERCEPTOR_SCRIPT).catch(() => {})
  })
}

// ─── 主进程层网络请求拦截（webRequest API）──
// 在 Electron 主进程层捕获所有发往 mubu 的 HTTP 请求，记录其完整 headers
// 用于解决 SPA 内部认证 token 难以从 JS 上下文提取的问题
let _capturedMubuRequests = []
let _webRequestRegistered = false

function _ensureWebRequestInterceptor() {
  if (_webRequestRegistered) return
  try {
    const ses = session.fromPartition(PARTITION)
    ses.webRequest.onBeforeSendHeaders(
      { urls: ['https://*.mubu.com/*', 'https://mubu.com/*'] },
      (details, callback) => {
        try {
          if (details.url && (details.url.includes('mubu.com/v3/api/') || details.url.includes('/api/'))) {
            _capturedMubuRequests.push({
              url: details.url,
              method: details.method,
              headers: details.requestHeaders || {},
              postData: details.uploadData ? details.uploadData.map(d => d.toString()).join('') : '',
              time: Date.now(),
            })
            // 只保留最近 100 条
            if (_capturedMubuRequests.length > 100) _capturedMubuRequests.shift()
          }
        } catch (e) {}
        callback({ requestHeaders: details.requestHeaders })
      }
    )
    _webRequestRegistered = true
    console.log('[MubuSync] webRequest interceptor registered')
  } catch (e) {
    console.error('[MubuSync] webRequest interceptor setup failed:', e?.message || e)
  }
}

// 从捕获的 mubu 请求中提取认证 headers（返回可直接用的 headers 对象）
function _extractAuthHeadersFromCaptured() {
  if (_capturedMubuRequests.length === 0) return null
  // 所有可能的认证 / 业务 headers 字段名（小写）
  const authKeys = [
    'authorization', 'jwt-token', 'x-mubu-token', 'token',
    'x-csrf-token', 'x-xsrf-token', 'x-mubu-csrf-token',
  ]
  // 标准 headers（浏览器自动加的，不需要复制）
  const stdHeaders = [
    'host', 'connection', 'accept-encoding', 'accept-language', 'accept',
    'user-agent', 'referer', 'origin', 'content-length', 'content-type', 'cookie',
    'sec-fetch-mode', 'sec-fetch-site', 'sec-fetch-dest',
    'sec-ch-ua', 'sec-ch-ua-mobile', 'sec-ch-ua-platform',
    'dnt', 'pragma', 'cache-control',
  ]
  // 优先找 v3 API 的请求（避免误用 v4 agent API 的请求）
  const v3Requests = _capturedMubuRequests.filter(r => r.url && r.url.includes('/v3/api/'))
  const candidates = v3Requests.length > 0 ? v3Requests : _capturedMubuRequests
  for (const req of [...candidates].reverse()) {
    const lowerHeaders = {}
    for (const k of Object.keys(req.headers)) lowerHeaders[k.toLowerCase()] = req.headers[k]
    // 必须有 Jwt-Token 或 Authorization 之一才算认证请求
    const hasAuth = authKeys.some(k => lowerHeaders[k])
    if (!hasAuth) continue
    // 返回所有非标准 headers
    const customHeaders = {}
    for (const k2 of Object.keys(req.headers)) {
      const lk = k2.toLowerCase()
      if (!stdHeaders.includes(lk)) {
        customHeaders[k2] = req.headers[k2]
      }
    }
    return { headers: customHeaders, sourceUrl: req.url, sourceMethod: req.method, body: req.postData }
  }
  return null
}

async function fetchDocList() {
  // 确保 webRequest 拦截器已注册（用于捕获 SPA 的认证 headers）
  _ensureWebRequestInterceptor()
  // 清空之前捕获的请求（避免上次的过期数据污染）
  _capturedMubuRequests = []

  // 先确保 BrowserWindow 已加载（reload = true 触发 SPA 重新加载，会重新发 API 请求）
  const win = _getSyncWindow(true)
  await _waitForLoad(win)
  // 等待 SPA 加载并发出初始 API 请求（让 webRequest 拦截器能捕获到）
  await new Promise(r => setTimeout(r, 8000))

  // 打印捕获到的请求（用于调试）
  console.log('[MubuSync] captured mubu requests count:', _capturedMubuRequests.length)
  if (_capturedMubuRequests.length > 0) {
    const sample = _capturedMubuRequests[0]
    const headerKeys = Object.keys(sample.headers || {}).join(',')
    console.log('[MubuSync] first captured request: url=' + sample.url + ' method=' + sample.method + ' headerKeys=' + headerKeys)
  }

  // 提取 SPA 实际使用的认证 headers
  const capturedAuth = _extractAuthHeadersFromCaptured()
  if (capturedAuth) {
    console.log('[MubuSync] extracted auth headers from captured request:', Object.keys(capturedAuth.headers).join(','), 'sourceUrl=' + capturedAuth.sourceUrl)
  } else {
    console.log('[MubuSync] no auth headers captured, fallback to cookie-only')
  }

  // ========== 方案1（首选）：Node.js 端直接调用 v3 API（带捕获的认证 headers）==========
  try {
    const cookieStr = await _getMubuCookies()
    // 从 localStorage 获取 token
    let authToken = await _getMubuTokenFromStorage()
    if (!authToken) authToken = await _getMubuToken()
    console.log('[MubuSync] cookie len=' + (cookieStr||'').length + ', token=' + (authToken ? authToken.slice(0, 10) + '...(len=' + authToken.length + ')' : 'none'))

    if (cookieStr) {
      // 合并 capturedAuth.headers 作为额外 headers
      const extraHeaders = Object.assign({}, capturedAuth?.headers || {})
      // 同时保留之前的 token headers
      if (authToken) {
        if (!extraHeaders['Authorization']) extraHeaders['Authorization'] = 'Bearer ' + authToken
        if (!extraHeaders['x-mubu-token']) extraHeaders['x-mubu-token'] = authToken
        if (!extraHeaders['token']) extraHeaders['token'] = authToken
      }
      const capturedBody = capturedAuth?.body || ''
      const r = await _fetchAllDocsViaNodeApi(cookieStr, null, extraHeaders, capturedBody)
      console.log('[MubuSync] Node API result: ok=' + r.ok + ' docs=' + r.docs.length + ' folderIds=' + (r.folderIds||[]).join(','))
      if (r.ok && r.docs.length > 0) {
        return { ok: true, endpoint: 'node-v3api', data: { docs: r.docs }, url: 'node', count: r.docs.length, folderIds: r.folderIds }
      }
    }
  } catch (e) {
    console.error('[MubuSync] Node API failed:', e?.message || String(e))
  }

  // 打印 SPA 的请求信息（用于调试 headers）
  try {
    const reqInfo = await win.webContents.executeJavaScript(`
      (function() {
        var info = window.__mubuInterceptor?.requestInfo || [];
        return info.map(function(r) {
          return { url: r.url, method: r.method, headers: r.headers, body: (r.body||'').slice(0,500), credentials: r.credentials };
        });
      })()
    `, true)
    if (reqInfo && reqInfo.length > 0) {
      console.log('[MubuSync] SPA request info:', JSON.stringify(reqInfo[0]))
    } else {
      console.log('[MubuSync] No SPA request info captured (interceptor may not have triggered)')
    }
  } catch (e) {}

  // ========== 方案2（主要）：浏览器内主动 fetch v3 API + 递归遍历 ==========
  // 利用 SPA 完整的认证上下文（cookie + 自定义 headers），递归拉取所有文件夹
  // 把捕获的认证 headers 注入到浏览器 fetch
  const capturedHeadersJson = JSON.stringify(capturedAuth?.headers || {})
  const browserApiResult = await win.webContents.executeJavaScript(`
    (async () => {
      const allDocs = [];
      const seenIds = new Set();
      const visitedFolders = new Set();
      const MAX_PAGES = 50;
      const MAX_DEPTH = 8;
      const MAX_DOCS = 5000;
      const PAGE_SIZE = 50;
      // 把从主进程层捕获的认证 headers 注入到所有 fetch 调用
      const capturedHeaders = ${capturedHeadersJson};

      function buildHeaders() {
        const h = { 'Content-Type': 'application/json' };
        if (capturedHeaders && typeof capturedHeaders === 'object') {
          for (const k of Object.keys(capturedHeaders)) {
            h[k] = capturedHeaders[k];
          }
        }
        return h;
      }

      function extractDocArray(data) {
        if (!data || !data.data) return null;
        const possibleArrays = [
          data.data.list, data.data.docs, data.data.files,
          data.data.notes, data.data.items, data.data.folders,
          data.data.documents, data.data.result,
        ];
        for (const arr of possibleArrays) {
          if (Array.isArray(arr) && arr.length > 0) return arr;
        }
        return null;
      }

      function extractDoc(d) {
        return {
          doc_id: String(d.doc_id || d.id || d._id || d.fileId || d.folderId || ''),
          title: d.title || d.name || d.fileName || d.text || '',
          parent_id: String(d.parent_id || d.parentId || d.folderId || d.pid || ''),
          type: d.type || (d.isFolder ? 'folder' : 'doc'),
          edit_time: d.edit_time || d.updateTime || d.updated_at || d.editTime || 0,
          url: d.url || '',
        };
      }

      let folderIds = [];
      let firstItemCountError = '';
      try {
        const r = await fetch('https://api2.mubu.com/v3/api/list/item_count', {
          method: 'POST',
          headers: buildHeaders(),
          body: JSON.stringify({}),
          credentials: 'include',
        });
        const data = await r.json();
        if (data && (data.code === undefined || data.code === 0) && data.data) {
          const docMap = data.data.doc || {};
          const folderMap = data.data.folder || {};
          folderIds = [...Object.keys(docMap), ...Object.keys(folderMap)];
        } else {
          firstItemCountError = 'code=' + (data && data.code) + ' msg=' + (data && data.msg);
        }
      } catch (e) { firstItemCountError = e.message; }

      let apiWorked = false;
      let firstPageError = '';

      async function fetchPage(folderId, depth) {
        if (depth > MAX_DEPTH) return;
        if (allDocs.length >= MAX_DOCS) return;
        const folderKey = folderId || 'root';
        if (visitedFolders.has(folderKey)) return;
        visitedFolders.add(folderKey);

        let page = 1;
        let firstCall = true;
        while (page <= MAX_PAGES && allDocs.length < MAX_DOCS) {
          const body = { page, size: PAGE_SIZE };
          let result = null;
          let lastErr = '';
          const paramNames = folderId ? ['folderId', 'parentId', 'fid'] : ['folderId', 'parentId'];
          for (const pname of paramNames) {
            if (folderId) body[pname] = folderId;
            try {
              const r = await fetch('https://api2.mubu.com/v3/api/list/get_all_documents_page', {
                method: 'POST',
                headers: buildHeaders(),
                body: JSON.stringify(body),
                credentials: 'include',
              });
              const data = await r.json();
              if (data && (data.code === undefined || data.code === 0)) {
                result = data;
                break;
              }
              lastErr = 'code=' + data.code + ' msg=' + (data.msg || '');
            } catch (e) { lastErr = e.message; }
            if (folderId) delete body[pname];
          }
          if (!result) {
            if (firstCall && folderId === null && !firstPageError) {
              firstPageError = lastErr;
            }
            break;
          }
          const docs = extractDocArray(result);
          if (!docs || docs.length === 0) break;
          apiWorked = true;

          let newCount = 0;
          const foldersToRecurse = [];
          for (const d of docs) {
            if (allDocs.length >= MAX_DOCS) break;
            const doc = extractDoc(d);
            if (!doc.doc_id || seenIds.has(doc.doc_id)) continue;
            seenIds.add(doc.doc_id);
            if (folderId && !doc.parent_id) doc.parent_id = folderId;
            if (doc.type === 5 || doc.type === '5') doc.type = 'doc';
            allDocs.push(doc);
            newCount++;
            const isFolder = doc.type === 'folder' || d.isFolder;
            if (isFolder) foldersToRecurse.push(doc.doc_id);
          }
          for (const fid of foldersToRecurse) {
            await fetchPage(fid, depth + 1);
          }
          if (docs.length < PAGE_SIZE) break;
          if (newCount === 0) break;
          page++;
        }
      }

      await fetchPage(null, 0);
      for (const fid of folderIds) {
        if (allDocs.length >= MAX_DOCS) break;
        await fetchPage(fid, 0);
      }

      return {
        ok: apiWorked,
        endpoint: 'browser-v3api',
        data: { docs: allDocs },
        count: allDocs.length,
        folderIds: folderIds,
        firstItemCountError: firstItemCountError,
        firstPageError: firstPageError,
      };
    })()
  `, true).catch(e => ({ ok: false, error: e.message }))

  console.log('[MubuSync] fetchDocList (browser v3api):', JSON.stringify({
    ok: browserApiResult?.ok, count: browserApiResult?.count,
    folderIds: (browserApiResult?.folderIds || []).slice(0, 10).join(','),
    firstItemCountError: browserApiResult?.firstItemCountError,
    firstPageError: browserApiResult?.firstPageError,
  }))

  if (browserApiResult?.ok && browserApiResult?.count > 0) {
    return browserApiResult
  }

  // ========== 方案3（最终兜底）：从拦截器捕获的响应中提取 ==========
  const result = await win.webContents.executeJavaScript(`
    (async () => {
      const url = window.location.href
      let apiDocs = []
      const intercepted = window.__mubuInterceptor?.responses || []
      for (const resp of intercepted) {
        const data = resp.data
        const possibleArrays = [
          data?.data?.docs, data?.data?.list, data?.data?.files,
          data?.data?.notes, data?.data?.items, data?.data?.folders,
          data?.data?.documents, data?.data?.result,
          data?.docs, data?.list, data?.files, data?.items,
        ]
        for (const docs of possibleArrays) {
          if (Array.isArray(docs) && docs.length > 0) {
            const mapped = docs.map(d => ({
              doc_id: String(d.doc_id || d.id || d._id || d.fileId || d.folderId || ''),
              title: d.title || d.name || d.fileName || d.text || '',
              parent_id: String(d.parent_id || d.parentId || d.folderId || d.pid || ''),
              type: d.type || (d.isFolder ? 'folder' : 'doc'),
              edit_time: d.edit_time || d.updateTime || d.updated_at || d.editTime || 0,
              url: d.url || '',
            })).filter(d => d.doc_id)
            for (const d of mapped) {
              if (!apiDocs.find(x => x.doc_id === d.doc_id)) apiDocs.push(d)
            }
          }
        }
      }
      if (apiDocs.length > 0) {
        return { ok: true, endpoint: 'intercepted', data: { docs: apiDocs }, url, count: apiDocs.length, interceptedCount: intercepted.length }
      }
      // DOM 兜底
      const docLinks = document.querySelectorAll('a[href*="/doc/"], a[href*="/docEdit/"]')
      const docsFromDom = []
      const seen = new Set()
      docLinks.forEach(a => {
        const href = a.getAttribute('href') || ''
        const match = href.match(/\\/doc(?:Edit)?\\/([a-zA-Z0-9]{6,})/)
        if (match && !seen.has(match[1])) {
          seen.add(match[1])
          docsFromDom.push({ doc_id: match[1], title: a.textContent?.trim() || '', type: 'doc' })
        }
      })
      if (docsFromDom.length > 0) {
        return { ok: true, endpoint: 'dom', data: { docs: docsFromDom }, url, count: docsFromDom.length }
      }
      return { ok: false, reason: 'no docs found', url, interceptedCount: intercepted.length }
    })()
  `, true)

  console.log('[MubuSync] fetchDocList (interceptor fallback):', JSON.stringify({
    ok: result?.ok, endpoint: result?.endpoint, count: result?.count,
  }))
  return result
}

// ─── 拉取单篇文档正文 ────────────────────────────
// 优先用 Node.js 直接调用 v3 API（避免浏览器 CORS "Failed to fetch"）
// 需要传入 cookieStr + extraHeaders（含 Jwt-Token）
async function _fetchDocContentViaNodeApi(docId, cookieStr, extraHeaders) {
  const bodyObj = { docId: String(docId) }
  const r = await _mubuApiPost('/v3/api/document/get', bodyObj, cookieStr, extraHeaders)
  if (!r.ok || !r.data || (r.data.code !== undefined && r.data.code !== 0)) {
    return { ok: false, reason: 'api_failed', code: r.data?.code, msg: r.data?.msg }
  }
  return { ok: true, data: r.data.data, endpoint: 'node-v3api' }
}

async function fetchDocContent(docId, cookieStr, extraHeaders) {
  // 方案1（首选）：Node.js 直接调用 v3 API
  if (cookieStr) {
    try {
      const result = await _fetchDocContentViaNodeApi(docId, cookieStr, extraHeaders)
      if (result.ok) {
        return result
      }
      console.log('[MubuSync] doc content node API failed for ' + docId + ': ' + (result.msg || result.reason))
    } catch (e) {
      console.log('[MubuSync] doc content node API error for ' + docId + ': ' + (e?.message || e))
    }
  }

  // 方案2（兜底）：浏览器内 fetch（CORS 可能失败）
  const win = _getSyncWindow()
  await _waitForLoad(win)

  // 注入认证 headers 到浏览器 fetch
  const capturedHeadersJson = JSON.stringify(extraHeaders || {})
  const result = await win.webContents.executeJavaScript(`
    (async () => {
      const docId = ${JSON.stringify(docId)}
      const extraHeaders = ${capturedHeadersJson}
      function buildHeaders() {
        const h = { 'Content-Type': 'application/json' }
        if (extraHeaders && typeof extraHeaders === 'object') {
          for (const k of Object.keys(extraHeaders)) {
            h[k] = extraHeaders[k]
          }
        }
        return h
      }
      try {
        const resp = await fetch('https://api2.mubu.com/v3/api/document/get', {
          method: 'POST',
          headers: buildHeaders(),
          body: JSON.stringify({ docId: docId }),
          credentials: 'include',
        })
        if (resp.ok) {
          const data = await resp.json()
          if (data && (data.code === undefined || data.code === 0)) {
            return { ok: true, endpoint: 'browser-v3api', data: data.data }
          }
          return { ok: false, reason: 'code=' + data.code + ' msg=' + (data.msg || '') }
        }
        return { ok: false, reason: 'http=' + resp.status }
      } catch (e) {
        return { ok: false, reason: e.message }
      }
    })()
  `, true).catch(e => ({ ok: false, reason: e.message }))

  return result
}

// ─── 主同步流程 ──────────────────────────────────
async function startSync() {
  if (_isSyncing) {
    console.log('[MubuSync] already syncing, skip')
    return false
  }
  _isSyncing = true
  _notifyStatusChange('syncing')

  try {
    // 1. 检查 cookie（每次同步都重新加载页面，确保拾取最新 cookie）
    const check = await checkCookieValid(true)
    if (!check.valid) {
      console.log('[MubuSync] cookie invalid:', check.reason)
      // cookie 无效时不推 ingest，只通知前端需要登录
      _notifyStatusChange('cookie_invalid')
      _isSyncing = false
      return false
    }

    // 2. 拉文档列表
    const listResult = await fetchDocList()
    if (!listResult.ok) {
      console.error('[MubuSync] fetch list failed:', listResult.reason)
      _notifyStatusChange('error', listResult.reason)
      _isSyncing = false
      return false
    }

    const docs = listResult.data?.docs || listResult.data?.data?.docs || listResult.data?.list || []
    if (!Array.isArray(docs) || docs.length === 0) {
      console.log('[MubuSync] no docs found')
      _notifyStatusChange('synced', { count: 0 })
      _isSyncing = false
      return true
    }

    console.log(`[MubuSync] got ${docs.length} docs, fetching content...`)

    // 准备文档正文 API 所需的认证信息（cookie + Jwt-Token header）
    const cookieStrForContent = await _getMubuCookies()
    const extraHeadersForContent = {}
    const capturedAuth = _extractAuthHeadersFromCaptured()
    if (capturedAuth?.headers) Object.assign(extraHeadersForContent, capturedAuth.headers)
    // 从 cookie 中提取 Jwt-Token（备用，防止 webRequest 未捕获）
    if (cookieStrForContent) {
      const m = cookieStrForContent.match(/(?:^|;\s*)Jwt-Token=([^;]+)/)
      if (m && m[1] && !extraHeadersForContent['Jwt-Token']) {
        extraHeadersForContent['Jwt-Token'] = m[1]
      }
      const cm = cookieStrForContent.match(/(?:^|;\s*)csrf_token=([^;]+)/)
      if (cm && cm[1]) {
        if (!extraHeadersForContent['x-csrf-token']) extraHeadersForContent['x-csrf-token'] = cm[1]
      }
    }

    // 通知前端开始拉取正文
    _notifyStatusChange('syncing', { progress: '0/' + docs.length })

    // 3. 拉正文（限制并发，避免压垮 mubu）
    const CONCURRENCY = 5
    const enrichedDocs = []
    let firstContentStructLogged = false
    let firstFetchErrLogged = false
    let contentOkCount = 0
    let contentFailCount = 0
    for (let i = 0; i < docs.length; i += CONCURRENCY) {
      const batch = docs.slice(i, i + CONCURRENCY)
      const results = await Promise.allSettled(
        batch.map(async (doc) => {
          const docId = doc.doc_id || doc.id || doc._id || ''
          if (!docId) return null
          const title = doc.title || doc.name || ''
          const editTime = doc.edit_time || doc.updateTime || doc.updated_at || 0
          const parentId = doc.parent_id || doc.parentId || doc.folderId || ''

          // 只拉取文档（跳过文件夹）
          const docType = doc.type || (doc.isFolder ? 'folder' : 'doc')
          if (docType === 'folder') {
            return {
              doc_id: String(docId),
              title,
              parent_id: String(parentId),
              type: 'folder',
              content_md: '',
              edit_time: Number(editTime) || 0,
            }
          }

          const contentResult = await fetchDocContent(String(docId), cookieStrForContent, extraHeadersForContent)
          let contentMd = ''
          let contentJson = ''
          let firstError = ''
          if (contentResult.ok) {
            // 尝试从返回数据中提取正文
            const data = contentResult.data
            if (typeof data === 'string') {
              contentMd = data
            } else {
              // 多路径递归查找 content / tree / nodes 字段
              const found = _extractContentFromAny(data)
              if (found.contentMd) contentMd = found.contentMd
              if (found.contentJson) contentJson = found.contentJson
              if (!contentMd && !contentJson) {
                // 记录第一篇失败文档的数据结构（供调试）
                if (!firstContentStructLogged) {
                  firstContentStructLogged = true
                  try {
                    const sample = JSON.stringify(data).slice(0, 800)
                    console.log('[MubuSync] first doc content structure (endpoint=' + contentResult.endpoint + ', docId=' + docId + '): ' + sample)
                  } catch (e) {}
                }
              }
            }
            if (contentMd) contentOkCount++
          } else {
            contentFailCount++
            if (!firstFetchErrLogged) {
              firstFetchErrLogged = true
              console.log('[MubuSync] first doc fetch failed: docId=' + docId + ' reason=' + contentResult.reason + ' msg=' + (contentResult.msg || ''))
            }
            firstError = contentResult.reason || ''
          }

          return {
            doc_id: String(docId),
            title,
            parent_id: String(parentId),
            type: 'doc',
            content_md: contentMd,
            content_json: contentJson,
            edit_time: Number(editTime) || 0,
            fetch_error: firstError,
          }
        })
      )
      for (const r of results) {
        if (r.status === 'fulfilled' && r.value) {
          enrichedDocs.push(r.value)
        }
      }
      // 通知前端拉取进度
      _notifyStatusChange('syncing', { progress: enrichedDocs.length + '/' + docs.length })
      // 每批之间间隔 200ms，避免压垮
      await new Promise(r => setTimeout(r, 200))
    }

    // 4. 推给 Flask 入库
    const ingestResult = await _postToBackend('/api/mubu/ingest', { docs: enrichedDocs })
    console.log(`[MubuSync] ingested ${enrichedDocs.length} docs (content_ok=${contentOkCount}, content_fail=${contentFailCount}), backend response:`, ingestResult.body)

    _notifyStatusChange('synced', { count: enrichedDocs.length })
    _isSyncing = false
    return true
  } catch (e) {
    console.error('[MubuSync] sync failed:', e)
    _notifyStatusChange('error', e.message)
    _isSyncing = false
    return false
  }
}

// ─── HTML 标签清理 ────────────────────────────────
function _stripHtmlTags(text) {
  if (!text || typeof text !== 'string') return ''
  // 把 HTML 实体先解码（常见幕布 inline 标签）
  let s = text
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n')
    .replace(/<\/div>/gi, '\n')
    .replace(/<[^>]+>/g, '')  // 移除所有 HTML 标签
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/  +/g, ' ')
    .trim()
  return s
}

// ─── 幕布 definition 树 → Markdown ──────────────────
// 幕布 nodes 结构：{nodes: [{heading:1, text:"...", children:[{heading:2, text:"..."}, ...]}]}
// heading 表示层级（1=顶级, 2=二级, 3=三级...）
function _treeToMarkdown(node, depth = 0) {
  if (!node) return ''
  // 数组：每个元素作为同级节点
  if (Array.isArray(node)) {
    let md = ''
    for (const item of node) {
      md += _treeToMarkdown(item, depth)
    }
    return md
  }
  if (typeof node !== 'object') return ''
  let md = ''
  // 幕布节点用 heading 字段表示层级，忽略 depth 参数，直接用 heading
  const heading = node.heading
  const level = (typeof heading === 'number' && heading > 0) ? heading : (depth + 1)
  const indent = '  '.repeat(Math.max(0, level - 1))
  // 幕布节点的文本字段：text（可能含 HTML）
  let text = node.text || node.title || node.content || node.note || ''
  if (text) {
    text = _stripHtmlTags(text)
    if (text) {
      md += `${indent}- ${text}\n`
    }
  }
  // 递归子节点
  const children = node.children || node.sub_nodes || node.subNodes || node.nodes || node.child || []
  if (Array.isArray(children)) {
    for (const child of children) {
      md += _treeToMarkdown(child, level)
    }
  }
  // 兼容：可能直接有 inline 子节点
  if (node.lines && Array.isArray(node.lines)) {
    for (const line of node.lines) {
      if (typeof line === 'string') {
        md += `${indent}  ${line}\n`
      } else if (line && line.text) {
        md += `${indent}  ${_stripHtmlTags(line.text)}\n`
      }
    }
  }
  return md
}

// 从任意 JSON 结构中尝试提取正文（content/Markdown 形式）
// 专门处理幕布 v3 API 的 definition 字段（JSON 字符串）
// 返回 { contentMd, contentJson }
function _extractContentFromAny(data) {
  if (!data) return { contentMd: '', contentJson: '' }
  // 字符串：可能是 definition JSON 字符串，也可能是纯文本
  if (typeof data === 'string') {
    const trimmed = data.trim()
    if (!trimmed) return { contentMd: '', contentJson: '' }
    // 尝试解析为 JSON（幕布 definition 是 JSON 字符串）
    if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed)
        const result = _extractContentFromAny(parsed)
        if (result.contentMd) return result
      } catch (e) {
        // 不是 JSON，当作纯文本
      }
    }
    return { contentMd: data, contentJson: '' }
  }
  if (typeof data !== 'object') return { contentMd: '', contentJson: '' }

  // 幕布 v3 API document/get 返回：{role, baseVersion, author, name, definition, directory}
  // definition 是 JSON 字符串，含 nodes 树
  if (data.definition && typeof data.definition === 'string') {
    try {
      const def = JSON.parse(data.definition)
      // 幕布 definition 结构：{nodes: [...], ...}
      const nodes = def.nodes || def.tree || def.root
      if (nodes) {
        const md = _treeToMarkdown(nodes)
        if (md && md.trim()) {
          return { contentMd: md, contentJson: data.definition }
        }
      }
      // 也尝试直接转换 def
      const md2 = _treeToMarkdown(def)
      if (md2 && md2.trim()) {
        return { contentMd: md2, contentJson: data.definition }
      }
    } catch (e) {
      // definition 不是 JSON，当作纯文本
      if (data.definition.trim()) {
        return { contentMd: _stripHtmlTags(data.definition), contentJson: '' }
      }
    }
  }

  // 候选路径：可能包含正文字段（注意去掉 'data' 避免把 API 包装层当正文）
  const candidateKeys = ['content', 'tree', 'nodes', 'outline', 'document', 'lines', 'root']
  // 常见 v3 API 嵌套：data.data.xxx
  const rootCandidates = [data, data.data, data.data?.document, data.data?.content, data.result]
  for (const root of rootCandidates) {
    if (!root || typeof root !== 'object') continue
    // 直接是字符串
    if (typeof root === 'string') {
      return { contentMd: root, contentJson: '' }
    }
    // 1) Markdown 字符串字段（注意：不要把 name/title 当正文，避免 "- 标题\n" 假正文）
    for (const k of ['content_md', 'content', 'markdown', 'md', 'html']) {
      const v = root[k]
      if (typeof v === 'string' && v.trim()) {
        return { contentMd: v, contentJson: '' }
      }
    }
    // 2) 树形结构字段
    for (const k of candidateKeys) {
      const v = root[k]
      if (v && typeof v === 'object') {
        const md = _treeToMarkdown(v)
        if (md && md.trim()) {
          return { contentMd: md, contentJson: JSON.stringify(v) }
        }
      }
    }
    // 3) 数组（直接是节点列表）
    if (Array.isArray(root)) {
      const md = _treeToMarkdown(root)
      if (md && md.trim()) {
        return { contentMd: md, contentJson: JSON.stringify(root) }
      }
    }
  }
  return { contentMd: '', contentJson: '' }
}

// ─── 状态变化通知 ────────────────────────────────
function onStatusChange(callback) {
  _onStatusChange = callback
}

function _notifyStatusChange(status, data) {
  if (_onStatusChange) {
    try {
      _onStatusChange(status, data)
    } catch (e) {
      console.error('[MubuSync] status callback error:', e)
    }
  }
}

// ─── 定时同步 ────────────────────────────────────
function startAutoSync() {
  if (_syncTimer) return
  // 启动后 30 秒做首次同步
  setTimeout(() => {
    startSync()
    // 之后每 30 分钟同步一次
    _syncTimer = setInterval(startSync, SYNC_INTERVAL_MS)
  }, 30 * 1000)
  console.log('[MubuSync] auto sync scheduled (first run in 30s, then every 30min)')
}

function stopAutoSync() {
  if (_syncTimer) {
    clearInterval(_syncTimer)
    _syncTimer = null
  }
}

function isSyncing() {
  return _isSyncing
}

// ─── OPML 导入 ────────────────────────────────────
// 读取 OPML 文件，解析为文档列表，推给后端 /api/mubu/ingest 入库
async function importOpmlFile(opmlPath) {
  const fs = require('fs')

  // 读取 OPML 文件
  let xml
  try {
    xml = fs.readFileSync(opmlPath, 'utf-8')
  } catch (e) {
    console.error('[MubuSync] read OPML failed:', e?.message || e)
    return { ok: false, error: '读取 OPML 文件失败: ' + (e?.message || e) }
  }

  // 解析 OPML 为文档列表
  const docs = _parseOpml(xml)
  if (docs.length === 0) {
    return { ok: false, error: 'OPML 文件中没有找到任何文档' }
  }

  console.log('[MubuSync] OPML parsed: ' + docs.length + ' docs')

  // 推给后端入库
  try {
    const result = await _postToBackend('/api/mubu/ingest', { docs })
    console.log('[MubuSync] OPML ingest result:', result.body)
    _notifyStatusChange('synced', { count: docs.length, source: 'opml' })
    return { ok: true, count: docs.length, response: result.body }
  } catch (e) {
    console.error('[MubuSync] OPML ingest failed:', e)
    _notifyStatusChange('error', 'OPML 导入失败: ' + (e?.message || e))
    return { ok: false, error: '入库失败: ' + (e?.message || e) }
  }
}

// 解析 OPML XML 为文档列表（不依赖外部 XML 库）
// OPML 结构：<outline text="..." title="..." note="..." type="folder/doc"> 可嵌套
function _parseOpml(xml) {
  const docs = []
  const stack = []  // 父节点 ID 栈，用于跟踪嵌套层级
  let counter = 0

  // 提取 body 内容（OPML 的文档树在 <body> 内）
  const bodyMatch = xml.match(/<body[^>]*>([\s\S]*?)<\/body>/i)
  if (!bodyMatch) return docs
  const body = bodyMatch[1]

  // 匹配 outline 标签：自闭合 <outline .../>、开标签 <outline ...>、闭标签 </outline>
  const tokenRegex = /<outline\b([^>]*)\/>|<outline\b([^>]*)>|<\/outline>/gi
  let match
  while ((match = tokenRegex.exec(body)) !== null) {
    if (match[0].startsWith('</')) {
      // 闭标签：弹出栈
      stack.pop()
      continue
    }

    // 解析属性（兼容双引号和单引号）
    const attrsStr = match[1] || match[2] || ''
    const attrs = {}
    const attrRegex = /(\w+)=["']([^"']*)["']/g
    let am
    while ((am = attrRegex.exec(attrsStr)) !== null) {
      attrs[am[1]] = am[2]
    }

    counter++
    const docId = attrs.xmlId || attrs.id || ('opml_' + counter)
    const parentId = stack.length > 0 ? stack[stack.length - 1] : ''
    const text = _decodeEntities(attrs.text || attrs.title || '')
    const note = _decodeEntities(attrs.note || '')
    const type = attrs.type || ''
    const isSelfClosing = match[0].endsWith('/>')

    // 判断是否为文件夹：显式 type=folder，或无 note 内容且有子节点
    const isFolder = type === 'folder' || (!note && !isSelfClosing)

    docs.push({
      doc_id: String(docId),
      title: text,
      parent_id: String(parentId),
      type: isFolder ? 'folder' : 'doc',
      content_md: note,
      content_json: '',
      edit_time: 0,
    })

    // 非自闭合标签压栈，作为后续子节点的 parent
    if (!isSelfClosing) {
      stack.push(docId)
    }
  }

  return docs
}

// HTML 实体解码（OPML 属性值中的 &lt; &gt; &quot; 等）
function _decodeEntities(str) {
  if (!str) return ''
  return str
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&')
}

// ─── 暴露给 main.cjs 的 API ────────────────────────
module.exports = {
  showLoginWindow,
  startSync,
  startAutoSync,
  stopAutoSync,
  checkCookieValid,
  isSyncing,
  onStatusChange,
  setBackendConfig,
  importOpmlFile,
}
