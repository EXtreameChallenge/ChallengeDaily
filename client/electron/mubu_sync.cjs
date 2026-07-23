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
const SYNC_INTERVAL_MS = 10 * 60 * 1000  // 10 分钟同步一次

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
    window.__mubuInterceptor = { responses: [] };
    const origFetch = window.fetch;
    window.fetch = async function(...args) {
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
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
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

async function fetchDocList() {
  const win = _getSyncWindow(true)  // reload=true，重新加载以触发拦截器
  await _waitForLoad(win)

  // 等待 SPA 完全渲染
  await new Promise(r => setTimeout(r, 8000))

  const result = await win.webContents.executeJavaScript(`
    (async () => {
      const url = window.location.href

      // 方案1：从拦截到的 API 响应中提取文档列表
      let apiDocs = []
      const intercepted = window.__mubuInterceptor?.responses || []
      // 输出所有拦截到的响应结构（调试用）
      const debugIntercepted = intercepted.map(r => ({
        url: r.url,
        dataKeys: typeof r.data === 'object' ? Object.keys(r.data || {}).slice(0, 10) : typeof r.data,
        dataSnippet: JSON.stringify(r.data).slice(0, 300)
      }))
      for (const resp of intercepted) {
        const data = resp.data
        // 幕布 API 返回格式：{ data: { ... } }
        // 尝试多种可能的字段名
        const possibleArrays = [
          data?.data?.docs, data?.data?.list, data?.data?.files,
          data?.data?.notes, data?.data?.items, data?.data?.folders,
          data?.data?.documents, data?.data?.result,
          data?.docs, data?.list, data?.files, data?.items,
          data?.data?.data?.docs, data?.data?.data?.list,
        ]
        for (const docs of possibleArrays) {
          if (Array.isArray(docs) && docs.length > 0) {
            apiDocs = docs.map(d => ({
              doc_id: String(d.doc_id || d.id || d._id || d.fileId || d.folderId || ''),
              title: d.title || d.name || d.fileName || d.text || '',
              parent_id: String(d.parent_id || d.parentId || d.folderId || d.pid || ''),
              type: d.type || (d.isFolder ? 'folder' : 'doc'),
              edit_time: d.edit_time || d.updateTime || d.updated_at || d.editTime || d.editTimeStr || 0,
              url: d.url || '',
            })).filter(d => d.doc_id)
            break
          }
        }
        if (apiDocs.length > 0) break
      }

      // 方案2：从 DOM 抓取文档链接
      const docLinks = document.querySelectorAll('a[href*="/doc/"], a[href*="/docEdit/"]')
      const docsFromDom = []
      const seen = new Set()
      docLinks.forEach(a => {
        const href = a.getAttribute('href') || ''
        const match = href.match(/\\/doc(?:Edit)?\\/([a-zA-Z0-9]{6,})/)
        if (match && !seen.has(match[1])) {
          seen.add(match[1])
          docsFromDom.push({
            doc_id: match[1],
            title: a.textContent?.trim() || '',
            url: href.startsWith('http') ? href : 'https://mubu.com' + href,
            type: 'doc',
          })
        }
      })

      // 方案3：从 DOM HTML 中正则匹配 /doc/xxx
      if (docsFromDom.length === 0) {
        const html = document.body.innerHTML
        const regex = /\\/doc(?:Edit)?\\/([a-zA-Z0-9]{6,})/g
        let m
        while ((m = regex.exec(html)) !== null) {
          if (!seen.has(m[1])) {
            seen.add(m[1])
            docsFromDom.push({ doc_id: m[1], title: '', type: 'doc' })
          }
        }
      }

      const allDocs = apiDocs.length > 0 ? apiDocs : docsFromDom

      if (allDocs.length > 0) {
        return { ok: true, endpoint: apiDocs.length > 0 ? 'intercepted' : 'dom', data: { docs: allDocs }, url, interceptedCount: intercepted.length, interceptedUrls: intercepted.map(r => r.url) }
      }

      const spinnerVisible = !!document.querySelector('[class*="Spin"]')
      const bodyText = document.body.textContent.slice(0, 300)
      return { ok: false, reason: 'no docs found', url, interceptedCount: intercepted.length, interceptedUrls: intercepted.map(r => r.url), spinnerVisible, bodyText, debugIntercepted }
    })()
  `, true)

  console.log('[MubuSync] fetchDocList result:', JSON.stringify(result).slice(0, 1000))
  return result
}

// ─── 拉取单篇文档正文 ────────────────────────────
async function fetchDocContent(docId) {
  const win = _getSyncWindow()
  await _waitForLoad(win)

  const result = await win.webContents.executeJavaScript(`
    (async () => {
      const endpoints = [
        '/api/document/get?docId=' + ${JSON.stringify(docId)},
        '/api/document/' + ${JSON.stringify(docId)},
        '/doc/' + ${JSON.stringify(docId)},
      ]
      for (const ep of endpoints) {
        try {
          const resp = await fetch(ep, { credentials: 'include' })
          if (resp.ok) {
            const ct = resp.headers.get('content-type') || ''
            if (ct.includes('application/json')) {
              const data = await resp.json()
              return { ok: true, endpoint: ep, data }
            }
          }
        } catch (e) {}
      }
      return { ok: false, reason: 'no endpoint worked' }
    })()
  `, true)

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

    // 3. 拉正文（限制并发，避免压垮 mubu）
    const CONCURRENCY = 3
    const enrichedDocs = []
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

          const contentResult = await fetchDocContent(String(docId))
          let contentMd = ''
          let contentJson = ''
          if (contentResult.ok) {
            // 尝试从返回数据中提取正文
            const data = contentResult.data
            if (typeof data === 'string') {
              contentMd = data
            } else if (data?.content || data?.data?.content) {
              const content = data.content || data.data.content
              if (typeof content === 'string') {
                contentMd = content
              } else {
                contentJson = JSON.stringify(content)
                contentMd = _treeToMarkdown(content)
              }
            }
            if (data?.data?.content) {
              contentJson = JSON.stringify(data.data.content)
            }
          }

          return {
            doc_id: String(docId),
            title,
            parent_id: String(parentId),
            type: 'doc',
            content_md: contentMd,
            content_json: contentJson,
            edit_time: Number(editTime) || 0,
          }
        })
      )
      for (const r of results) {
        if (r.status === 'fulfilled' && r.value) {
          enrichedDocs.push(r.value)
        }
      }
      // 每批之间间隔 500ms，避免压垮
      await new Promise(r => setTimeout(r, 500))
    }

    // 4. 推给 Flask 入库
    const ingestResult = await _postToBackend('/api/mubu/ingest', { docs: enrichedDocs })
    console.log(`[MubuSync] ingested ${enrichedDocs.length} docs, backend response:`, ingestResult.body)

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

// ─── 树形结构转 Markdown（幕布大纲格式）────────────
function _treeToMarkdown(node, depth = 0) {
  if (!node) return ''
  let md = ''
  const indent = '  '.repeat(depth)
  if (node.text || node.title) {
    md += `${indent}- ${node.text || node.title}\n`
  }
  const children = node.children || node.sub_nodes || []
  for (const child of children) {
    md += _treeToMarkdown(child, depth + 1)
  }
  return md
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
    // 之后每 10 分钟同步一次
    _syncTimer = setInterval(startSync, SYNC_INTERVAL_MS)
  }, 30 * 1000)
  console.log('[MubuSync] auto sync scheduled (first run in 30s, then every 10min)')
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
}
