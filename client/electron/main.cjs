const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage, screen, globalShortcut, Notification, session, dialog, shell } = require('electron')

// ─── ELECTRON_RUN_AS_NODE 防护 ─────────────────
// 如果全局环境变量 ELECTRON_RUN_AS_NODE=1 被设置，require('electron') 返回空对象，app 为 undefined
// 必须在此立即退出，否则后续所有 app.* 调用都会崩溃
if (!app) {
  console.error('[FATAL] ELECTRON_RUN_AS_NODE=1 detected. Electron is running in Node mode.')
  console.error('Please unset ELECTRON_RUN_AS_NODE before starting the app.')
  process.exit(1)
}

const path = require('path')
const { spawn, exec } = require('child_process')
const http = require('http')
const fs = require('fs')
const crypto = require('crypto')

// 把主进程 console 输出持久化到文件，方便排查无窗口启动问题
// 注意：__dirname 在打包后位于 asar 只读区，必须使用外部可写路径
const _resolveMainLogDir = () => {
  // 优先用 app.getPath('userData')（app ready 后可用）
  try {
    const electron = require('electron')
    if (electron.app && electron.app.getPath) {
      const p = electron.app.getPath('userData')
      if (p) return path.join(p, 'logs')
    }
  } catch (_) {}
  // 兜底：Windows APPDATA 或用户主目录
  if (process.env.APPDATA) return path.join(process.env.APPDATA, 'challenge-daily', 'logs')
  if (process.env.HOME) return path.join(process.env.HOME, '.challenge-daily', 'logs')
  // 最终兜底：临时目录
  const os = require('os')
  return path.join(os.tmpdir(), 'challenge-daily-logs')
}
const mainLogDir = _resolveMainLogDir()
try { fs.mkdirSync(mainLogDir, { recursive: true }) } catch (_) {}
const mainLogFile = path.join(mainLogDir, 'electron-main.log')
const mainLogStream = fs.createWriteStream(mainLogFile, { flags: 'a' })
const _origLog = console.log
const _origErr = console.error
const _writeLog = (tag, args) => {
  const line = `[${new Date().toISOString()}] [${tag}] ${args.map(a => typeof a === 'string' ? a : JSON.stringify(a)).join(' ')}`
  if (tag === 'ERR') _origErr(line)
  else _origLog(line)
  try { mainLogStream.write(line + '\n') } catch (_) {}
}
console.log = (...args) => _writeLog('LOG', args)
console.error = (...args) => _writeLog('ERR', args)
console.log('[Main] main.cjs loaded, log file:', mainLogFile)

// 保持全局引用，防止垃圾回收
let mainWindow = null
let petWindow = null
let pomodoroWidget = null
let tray = null
let backendProcess = null
let _backendDir = null        // 后端工作目录，供 readApiToken 使用
let _backendStarting = false  // 防止并发启动多个后端实例

const BACKEND_PORT = 58888
// isDev 判断优先级：
// 1. ELECTRON_IS_DEV=0 → 强制生产模式（start.bat/start.vbs 使用）
// 2. app.isPackaged → 真正打包后始终生产模式
// 3. dist/index.html 存在 → 源码运行但有构建产物，用生产模式
// 这样无论通过快捷方式、npx electron .、还是 start.bat 启动都能正确判断
const _distExists = fs.existsSync(path.join(__dirname, '..', 'dist', 'index.html'))
const isDev = process.env.ELECTRON_IS_DEV === '0' ? false
  : app.isPackaged ? false
  : !_distExists

// Windows 任务栏图标关键：设置 AppUserModelId（必须在 app ready 之前）
app.setAppUserModelId('com.challenge.daily')

// V8 内存优化：限制渲染进程内存上限，防止长期运行内存膨胀
// 必须在 app ready 之前设置，否则 V8 flags 不会生效
// 参考 Electron 性能指南：https://www.electronjs.org/docs/latest/api/web-preferences
app.commandLine.appendSwitch('js-flags', '--max-old-space-size=256 --gc-interval=100')

// ─── 关键：在 requestSingleInstanceLock() 之前显式设置 userData 路径 ───
// Electron 单实例锁基于 userData 路径生成命名管道名。
// 如果不显式设置，开发模式下（electron.exe .）可能与其他使用相同 Electron 二进制的
// 应用共享命名管道，导致误判"已有实例在运行"从而拒绝启动。
// 必须在 requestSingleInstanceLock() 之前调用。
// 使用 package.json name 作为目录名，与之前保持一致以复用配置。
const _userDataPath = path.join(app.getPath('appData'), 'challenge-daily')
try {
  fs.mkdirSync(_userDataPath, { recursive: true })
} catch (_) {}
app.setPath('userData', _userDataPath)
console.log('[Main] userData path:', _userDataPath)

// ─── 单实例锁：禁止打开多个窗口 ────────────────────
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  // 已有实例在运行，直接退出
  // 注意：必须用 app.exit() 而非 app.quit()，因为 app.quit() 是异步的，
  // app.ready 事件可能在 quit 生效前触发，导致 startBackend() 被错误调用。
  console.log('[Main] Another instance is already running, exiting...')
  app.exit(0)
} else {
  app.on('second-instance', () => {
    // 有人试图打开第二个实例，聚焦到已有窗口
    console.log('[Main] Second instance attempted, focusing main window')
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      if (!mainWindow.isVisible()) mainWindow.show()
      mainWindow.focus()
    }
  })
}

// 获取图标路径：按实际文件存在性查找，兼容源码运行、打包运行、开发模式
function getIconPath() {
  const possiblePaths = [
    path.join(__dirname, '..', 'public', 'icon.png'),
    path.join(__dirname, '..', 'public', 'icon.ico'),
    path.join(__dirname, '..', 'dist', 'icon.png'),
    path.join(__dirname, '..', 'dist', 'icon.ico'),
    path.join(process.resourcesPath, 'icon.png'),
    path.join(process.resourcesPath, 'icon.ico'),
  ]

  for (const p of possiblePaths) {
    try {
      if (fs.existsSync(p)) {
        console.log('[Main] Icon path found:', p)
        return p
      }
    } catch (_) {}
  }
  console.warn('[Main] Icon not found in paths:', possiblePaths)
  return possiblePaths[0]
}

// 托盘图标统一使用项目图标（resize 到 16x16 保证托盘清晰）
function getTrayIcon() {
  const iconPath = getIconPath()
  let image = nativeImage.createFromPath(iconPath)
  if (image.isEmpty()) {
    // fallback: 16x16 紫色方块
    return nativeImage.createFromBuffer(
      Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABGdBTUEAALGPC/xhBQAAAAlwSFlzAAAOwQAADsEBuJFr7QAAABl0RVh0U29mdHdhcmUAcGFpbnQubmV0IDQuMC4xNkRpr/UAAAB5SURBVDhPxZDRDYAgDERxBEdxFEdxFEdxFEdwBL2GEmhiNP7wkl5K7y4NAPwMQsJ3MfEbxpiZmWYi0mM8wPZAxcwklJaJNWYi0mM8QBlppjFmJtJjJiI9xgOUkWaaMWYm0mMmIj3G8wBlpJlmjJmJ9BgDUIaaZaaxpiZSYw5iMsZjNMAaaZYxZyYSDWbj2v4n5h9c2w8tljJ+7AAAAABJRU5ErkJggg==', 'base64')
    )
  }
  return image.resize({ width: 16, height: 16, quality: 'best' })
}

function getNotificationIcon() {
  const iconPath = getIconPath()
  const image = nativeImage.createFromPath(iconPath)
  if (image.isEmpty()) {
    return nativeImage.createFromBuffer(
      Buffer.from('iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAAXNSR0IArs4c6QAAAEJJREFUOE9jZKAQMGL4z8AAxP8RMQxiDEQxGYwYoxjEGKMYxRijGMUYoxjFGKMYxRijGMUYoxjFGOMYAABkwAj0E5/3IQAAAABJRU5ErkJggg==', 'base64')
    )
  }
  return image
}

// ─── 检测后端是否已在运行 ────────────────────────────
// 使用 keepAlive Agent 复用 TCP 连接，减少心跳检测的 TCP 握手开销
const _healthAgent = new http.Agent({ keepAlive: true, maxSockets: 2 })

function isBackendRunning() {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health?quick=1`, { agent: _healthAgent }, (res) => {
      // 消费响应体，避免连接泄漏
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(2000, () => { req.destroy(); resolve(false) })
  })
}

// 检测后端不仅存活，而且 token 匹配（避免连到旧实例/不同安装）
function isBackendTokenValid() {
  return new Promise((resolve) => {
    const token = readApiToken()
    const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/status`, {
      agent: _healthAgent,
      headers: { 'X-API-Token': token },
    }, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(2000, () => { req.destroy(); resolve(false) })
  })
}

// 异步等待 token 文件出现（后端启动时写入 .api_token 可能有毫秒级延迟）
async function _waitForTokenFile(timeoutMs = 10000) {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (readApiToken(1)) return true
    // 用 Promise 延迟替代 CPU 忙等，避免阻塞主进程
    await new Promise(r => setTimeout(r, 200))
  }
  return false
}

let _backendStartPromise = null

// ─── 启动 Python 后端 ────────────────────────────
async function startBackend() {
  console.log('[Main] startBackend() called')
  // 并发调用合并为同一个启动流程，避免 health check 重启与 app ready 同时 spawn
  if (_backendStartPromise) {
    console.log('[Main] Backend start already in progress, waiting...')
    return _backendStartPromise
  }
  _backendStartPromise = _doStartBackend().finally(() => { _backendStartPromise = null })
  return _backendStartPromise
}

async function _doStartBackend() {
  // 1. 如果后端已存活且 token 有效，直接复用（支持 start.bat 先启动后端的情况）
  if (await isBackendRunning()) {
    if (await isBackendTokenValid()) {
      console.log('[Main] Backend already running with valid token, skip spawning')
      return
    }
    console.error('[Main] WARNING: Port 58888 is occupied by another backend with mismatched token.')
    console.error('[Main] If the app shows 401 errors, kill any stale python.exe processes and restart.')
  }

  return new Promise((resolve, reject) => {
    let pythonExe = 'python'
    let mainScript
    let backendDir

    // 优先判断是否存在打包后的 backend 资源；否则按源码/开发模式处理
    const packagedMain = path.join(process.resourcesPath, 'backend', 'main.py')
    if (!isDev && fs.existsSync(packagedMain)) {
      // 真正的打包后环境
      mainScript = packagedMain
      backendDir = path.dirname(mainScript)
      const embeddedPython = path.join(process.resourcesPath, 'python', 'python.exe')
      if (fs.existsSync(embeddedPython)) {
        pythonExe = embeddedPython
      }
    } else {
      // 开发模式 或 start.vbs/start.bat 从源码启动
      mainScript = path.join(__dirname, '..', '..', 'main.py')
      backendDir = path.join(__dirname, '..', '..')
      // 通用 Python 查找：依次尝试 python / python3 / py launcher
      // 不依赖任何第三方应用专用的运行时路径
      const { execFileSync } = require('child_process')
      for (const candidate of ['python', 'python3', 'py']) {
        try {
          execFileSync(candidate, ['--version'], { stdio: 'ignore', windowsHide: true, timeout: 5000 })
          pythonExe = candidate
          break
        } catch (_) {}
      }
    }

    _backendDir = backendDir
    console.log('[Main] Starting backend:', pythonExe, mainScript)

    // 启动日志写入文件，方便排查启动失败问题
    const logDir = path.join(backendDir, 'data', 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    const logFile = path.join(logDir, 'electron-backend.log')
    const logStream = fs.createWriteStream(logFile, { flags: 'a' })
    const log = (tag, msg) => {
      const line = `[${new Date().toISOString()}] [${tag}] ${msg}`
      try { console.log(line) } catch (_) {}
      try { logStream.write(line + '\n') } catch (_) {}
    }
    log('Main', `Starting backend: ${pythonExe} ${mainScript} cwd=${backendDir}`)

    // Clean PYTHONHOME/PYTHONPATH - they may point to broken paths with Chinese chars
    // 安全：仅向子进程传递白名单环境变量，避免泄露主进程潜在的敏感信息
    const allowedEnvKeys = ['PORT', 'PYTHONIOENCODING', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'SystemRoot', 'TEMP', 'PATH', 'ELECTRON_IS_DEV', 'CHALLENGE_DAILY_DATA_DIR']
    const cleanEnv = {}
    for (const key of allowedEnvKeys) {
      if (process.env[key]) cleanEnv[key] = process.env[key]
    }
    delete cleanEnv.PYTHONHOME
    delete cleanEnv.PYTHONPATH
    cleanEnv.PORT = String(BACKEND_PORT)
    cleanEnv.PYTHONIOENCODING = 'utf-8'
    // 关键修复：把数据目录固定到 Electron userData，避免每次重新构建 dist-electron-tmp 后数据丢失
    const persistentDataDir = path.join(app.getPath('userData'), 'backend-data')
    fs.mkdirSync(persistentDataDir, { recursive: true })
    cleanEnv.CHALLENGE_DAILY_DATA_DIR = persistentDataDir
    // 关键修复：PYTHONUNBUFFERED=1 强制 Python stdout/stderr 不缓冲
    // 没有这个变量，Python 输出到 pipe 时自动切换为块缓冲（4-8KB），
    // 导致 "HTTP API 已启动" 消息无法及时到达 Node.js 'data' 事件，
    // 20秒超时后 Electron 误以为后端启动失败
    cleanEnv.PYTHONUNBUFFERED = '1'

    // 关键修复：-u 标志强制 Python 完全无缓冲模式（stdin/stdout/stderr）
    // 配合 PYTHONUNBUFFERED=1 双保险，确保启动消息能实时被捕获
    backendProcess = spawn(pythonExe, ['-u', mainScript], {
      cwd: backendDir,
      env: cleanEnv,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })

    let resolved = false
    const resolveOnce = (reason) => {
      if (!resolved) {
        resolved = true
        log('Main', `Backend start resolved: ${reason}`)
        resolve()
      }
    }

    // 用缓冲区累积 stdout 数据，防止消息被分包导致匹配失败
    let _stdoutBuf = ''
    let _stderrBuf = ''
    const _startupPatterns = ['Running on', 'Serving on', 'Press CTRL+C', `:${BACKEND_PORT}`]
    const _checkStartup = (buf) => {
      for (const p of _startupPatterns) {
        if (buf.includes(p)) return true
      }
      return false
    }

    backendProcess.stdout?.on('data', (data) => {
      const chunk = data.toString()
      _stdoutBuf += chunk
      log('Backend', chunk.trim())
      if (_checkStartup(_stdoutBuf)) resolveOnce('stdout startup pattern')
    })

    backendProcess.stderr?.on('data', (data) => {
      const chunk = data.toString()
      _stderrBuf += chunk
      log('BackendErr', chunk.trim())
      if (_checkStartup(_stderrBuf)) resolveOnce('stderr startup pattern')
    })

    backendProcess.on('error', (err) => {
      log('BackendFail', err.message)
      if (!resolved) { resolved = true; reject(err) }
    })

    backendProcess.on('exit', (code) => {
      log('BackendExit', `Exited with code: ${code}`)
      backendProcess = null
    })

    // 增强修复：除了 stdout 匹配外，同时轮询健康检查端口 + token 文件作为兜底
    // 5 秒后开始，每 1 秒探测一次 /api/health，最多探测 20 次
    // 这样即使 stdout 缓冲导致消息丢失，也能通过 HTTP 探活确认后端就绪
    const _healthProbeStart = setTimeout(() => {
      let probeCount = 0
      const probeInterval = setInterval(async () => {
        if (resolved) { clearInterval(probeInterval); return }
        probeCount++
        if (probeCount > 20) { clearInterval(probeInterval); return }
        const running = await isBackendRunning()
        if (running) {
          const tokenReady = await _waitForTokenFile(5000)
          if (tokenReady) {
            log('Main', `Backend confirmed via health probe (attempt ${probeCount})`)
            clearInterval(probeInterval)
            resolveOnce('health probe + token ready')
          } else {
            log('Main', `Backend health ok but token file not ready yet (attempt ${probeCount})`)
          }
        }
      }, 1000)
    }, 5000)

    // 超时保底：25秒后不管有没有看到成功消息都 resolve
    setTimeout(() => {
      resolveOnce('timeout fallback')
    }, 25000)
  })
}

function stopBackend() {
  if (backendProcess) {
    console.log('[Main] Stopping backend...')
    // 先移除 exit/error 监听器，防止 taskkill /F 触发的非零退出码被
    // watchBackend 误判为崩溃（_crashCount 递增）
    try {
      backendProcess.removeAllListeners('exit')
      backendProcess.removeAllListeners('error')
    } catch (_) {}
    // Windows: SIGTERM does not work for child_process.
    // Use taskkill to forcefully terminate the process tree.
    try {
      const { execSync } = require('child_process')
      const pid = backendProcess.pid
      if (pid) {
        execSync(`taskkill /pid ${pid} /T /F`, { windowsHide: true, stdio: 'ignore' })
      }
    } catch (e) {
      // Fallback: try the Node.js way
      try { backendProcess.kill() } catch (_) {}
    }
    backendProcess = null
  }
}

// ─── 主窗口 ──────────────────────────────────────
function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 680,
    minHeight: 480,
    resizable: true,
    maximizable: true,
    center: true,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#121212',
    icon: getIconPath(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // 关键修复：禁用后台节流，确保健康检查定时器和轮询在窗口最小化时仍正常运行
      // backgroundThrottling: true 会导致 Chromium 将 setInterval/setTimeout 节流到每分钟 1 次，
      // 造成前端误报"后端服务断开"（参考 Electron issue #21419）
      backgroundThrottling: false,
    },
    show: false,
  })

  // Content Security Policy：限制资源加载来源，防止 XSS 等注入攻击
  // 生产环境移除 script-src 'unsafe-inline'，仅开发模式（Vite HMR）保留
  const _cspScriptSrc = isDev
    ? "script-src 'self' 'unsafe-inline'; "
    : "script-src 'self'; "
  mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    // 每次响应生成一次性 nonce，供未来 style-src 收紧使用
    const _styleNonce = crypto.randomBytes(16).toString('base64')
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self'; " +
          _cspScriptSrc +
          // TODO(P0-02): style-src 仍保留 'unsafe-inline'，存在 CSS data exfiltration 风险。
          // 未直接改用 'nonce-${_styleNonce}' 的原因：React 内联样式（style={{...}}）会生成
          // style 属性，CSP3 规定当 style-src 含 nonce 时 'unsafe-inline' 会被忽略，导致所有
          // 内联 style 属性被拦截、UI 渲染崩溃。要彻底移除 'unsafe-inline'，需先将所有内联
          // 样式迁移到 CSS 类，再启用 style-src-elem 'nonce-...' + style-src-attr。
          "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
          "img-src 'self' data: blob: http: https:; " +
          "font-src 'self' data: https://fonts.gstatic.com; " +
          "connect-src 'self' http://127.0.0.1:58888 http://localhost:5173 http://localhost:58888 " +
            "https://wttr.in https://api.open-meteo.com https://geocoding-api.open-meteo.com " +
            "https://api.bigdatacloud.net https://qifu-api.baidubce.com https://pv.sohu.com " +
            "https://int.dpool.sina.com.cn https://nominatim.openstreetmap.org " +
            "https://ipapi.co https://ipinfo.io https://ip-api.com " +
            "https://open.bigmodel.cn; " +
          "media-src 'none'; " +
          "object-src 'none'; " +
          "frame-src 'none';"
        ]
      }
    })
  })

  // 最小化/恢复事件：不再手动切换 backgroundThrottling
  // backgroundThrottling 已在 webPreferences 中设为 false，
  // 确保健康检查定时器在后台不被节流，避免窗口恢复后误报"后端断开"
  mainWindow.on('minimize', () => {
    // 保持定时器运行，不启用节流
  })
  mainWindow.on('restore', () => {
    // useAsyncData 的 visibilitychange 处理器会自动在恢复时刷新数据
  })

  // 自定义标题栏拖拽区域
  mainWindow.once('ready-to-show', () => {
    mainWindow.show()
  })

  // 保底：3秒后强制显示（防止 ready-to-show 未触发）
  setTimeout(() => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show()
    }
  }, 3000)

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }

  // 限制导航：仅允许本地开发服务器或 file:// 资源
  mainWindow.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('http://localhost:5173') && !url.startsWith('file://')) {
      e.preventDefault()
    }
  })

  // 新窗口一律转交系统浏览器打开，禁止 Electron 内部创建新窗口
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('close', (e) => {
    e.preventDefault()
    mainWindow.hide()
  })
}

// ─── 桌面宠物窗口 ──────────────────────────────
function createPetWindow() {
  const { width } = screen.getPrimaryDisplay().workAreaSize

  petWindow = new BrowserWindow({
    width: 200,
    height: 220,
    x: width - 230,
    y: 100,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,              // 禁用窗口阴影，避免透明区域出现黑边
    backgroundColor: undefined,  // 不设背景色，让透明生效
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
    show: false,
  })

  // 宠物窗口始终置顶但不抢焦点
  petWindow.setAlwaysOnTop(true, 'normal')
  petWindow.setFocusable(false)
  // Windows 透明窗口需要禁用视觉背景效果
  petWindow.setBackgroundColor('#00000000')

  if (isDev) {
    petWindow.loadURL('http://localhost:5173/pet.html')
  } else {
    petWindow.loadFile(path.join(__dirname, '..', 'dist', 'pet.html'))
  }

  // 加载完成后不自动显示，等待渲染进程通过 pet-toggle IPC 同步状态后再决定是否显示
  petWindow.once('ready-to-show', () => {
    console.log('[Main] Pet window ready-to-show, waiting for toggle signal...')
    // 默认隐藏，由 App.tsx 启动时根据 localStorage 的 cd_pet_visible 决定
  })

  petWindow.webContents.on('did-finish-load', () => {
    console.log('[Main] Pet window did-finish-load')
  })

  petWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    console.error('[Main] Pet window did-fail-load:', errorCode, errorDescription)
  })

  petWindow.on('closed', () => {
    console.log('[Main] Pet window closed')
    petWindow = null
  })

  // 窗口级别的拖拽：整个窗口可通过鼠标拖拽移动
  // 监听渲染进程发来的拖拽事件
  ipcMain.on('pet-window-drag', (_event, { mouseX, mouseY }) => {
    if (!petWindow || petWindow.isDestroyed()) return
    const [x, y] = petWindow.getPosition()
    petWindow.setPosition(x + mouseX, y + mouseY)
  })
}

// ─── 番茄钟悬浮计时窗口 ────────────────────────────────
// 类似"番茄土豆"的置顶小窗口，迷你显示倒计时/任务/阶段
// 番茄钟运行时自动弹出，可拖拽，点击跳回主界面
function createPomodoroWidget() {
  if (pomodoroWidget && !pomodoroWidget.isDestroyed()) {
    return pomodoroWidget
  }

  const { width: screenWidth } = screen.getPrimaryDisplay().workAreaSize

  pomodoroWidget = new BrowserWindow({
    width: 200,
    height: 80,
    x: screenWidth - 220,
    y: 60,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    backgroundColor: undefined,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
    show: false,
    focusable: true,  // 需要能接受点击
  })

  pomodoroWidget.setAlwaysOnTop(true, 'floating')
  pomodoroWidget.setBackgroundColor('#00000000')

  if (isDev) {
    pomodoroWidget.loadURL('http://localhost:5173/pomodoro-widget.html')
  } else {
    pomodoroWidget.loadFile(path.join(__dirname, '..', 'dist', 'pomodoro-widget.html'))
  }

  // 点击悬浮窗 → 激活主窗口并跳转到专注页
  pomodoroWidget.on('focus', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show()
      mainWindow.focus()
      mainWindow.webContents.send('navigate-to', '/focus')
    }
  })

  pomodoroWidget.on('closed', () => {
    pomodoroWidget = null
  })

  return pomodoroWidget
}

function showPomodoroWidget(data) {
  const w = createPomodoroWidget()
  w.webContents.once('did-finish-load', () => {
    w.webContents.send('pomodoro-tick', data)
    w.showInactive()  // 显示但不抢焦点
  })
  if (!w.webContents.isLoading()) {
    w.webContents.send('pomodoro-tick', data)
    if (!w.isVisible()) w.showInactive()
  }
}

function hidePomodoroWidget() {
  if (pomodoroWidget && !pomodoroWidget.isDestroyed()) {
    pomodoroWidget.hide()
  }
}

// ─── 系统托盘 ────────────────────────────────────
function createTray() {
  const icon = getTrayIcon()
  tray = new Tray(icon)
  const contextMenu = Menu.buildFromTemplate([
    { label: '显示主窗口', click: () => { mainWindow?.show(); mainWindow?.focus() } },
    { label: '显示桌面宠物', click: () => { petWindow?.show() } },
    { label: '隐藏桌面宠物', click: () => { petWindow?.hide() } },
    { type: 'separator' },
    { label: '开始记录', click: () => sendToRenderer('collector-action', 'start') },
    { label: '暂停记录', click: () => sendToRenderer('collector-action', 'stop') },
    { type: 'separator' },
    { label: '生成日报', click: () => { sendToRenderer('generate-report', 'daily'); mainWindow?.show() } },
    { label: '生成周报', click: () => { sendToRenderer('generate-report', 'weekly'); mainWindow?.show() } },
    { type: 'separator' },
    { label: '退出', click: () => quitApp() },
  ])

  tray.setToolTip('ChallengeDaily')
  tray.setContextMenu(contextMenu)
  tray.on('double-click', () => { mainWindow?.show(); mainWindow?.focus() })
}

function sendToRenderer(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data)
  }
}

function quitApp() {
  globalShortcut.unregisterAll()
  stopBackend()
  tray?.destroy()
  petWindow?.destroy()
  mainWindow?.destroy()
  app.quit()
}

// ─── IPC 通信 ────────────────────────────────────
// IPC sender 校验：仅允许主窗口来源调用敏感通道
// 安全设计：多层校验，优先 webContents 引用比较，兜底用路径前缀比较（非 origin）
// 注意：file:// 协议下所有页面 origin 都是 "file://"，不能用 origin 比较防外部页面
const isFromMainWindow = (sender) => {
  try {
    // 第一层：webContents 引用比较（最严格，主路径）
    if (mainWindow && sender === mainWindow.webContents) {
      return true
    }
    // 第二层：webContents ID 比较（防止引用未更新）
    if (mainWindow && sender.id === mainWindow.webContents.id) {
      return true
    }
    // 第三层：兜底用 URL 路径前缀比较（非 origin 比较）
    // file:// 协议下 origin 不可靠（所有 file:// 页面 origin 都是 "file://"）
    const senderUrl = sender.getURL()
    if (!senderUrl) return false
    if (senderUrl.startsWith('file://')) {
      // 生产模式：仅允许本应用 dist 目录下的 file:// 资源
      // __dirname = client/electron，dist 在 client/dist
      const appDistPath = path.join(__dirname, '..', 'dist').replace(/\\/g, '/')
      // 规范化为 file:///D:/path 形式
      const appDistUrl = `file:///${appDistPath.replace(/^\//, '')}`
      return senderUrl.startsWith(appDistUrl)
    }
    // 开发模式：仅允许 localhost:5173
    if (isDev) {
      try {
        const origin = new URL(senderUrl).origin
        return origin === 'http://localhost:5173'
      } catch (_) {
        return false
      }
    }
    return false // 生产模式非 file:// 一律拒绝
  } catch (_) {
    return false // 校验失败时默认拒绝，防止未授权渲染进程调用敏感通道
  }
}

function setupIPC() {
  // 窗口控制
  ipcMain.on('window-minimize', () => mainWindow?.minimize())
  ipcMain.on('window-maximize', () => {
    if (mainWindow?.isMaximized()) {
      mainWindow.unmaximize()
    } else {
      mainWindow?.maximize()
    }
  })
  ipcMain.on('window-close', () => mainWindow?.hide())
  ipcMain.on('window-show', () => mainWindow?.show())

  // 宠物控制：show 时创建/显示，hide 时销毁（避免透明窗口残留白色方块）
  ipcMain.on('pet-toggle', (_event, show) => {
    if (show) {
      if (!petWindow || petWindow.isDestroyed()) {
        createPetWindow()
      }
      petWindow?.show()
      petWindow?.setAlwaysOnTop(true, 'normal')
      petWindow?.setFocusable(false)
    } else {
      if (petWindow && !petWindow.isDestroyed()) {
        petWindow.destroy()
        petWindow = null
      }
    }
  })
  // renderer 请求当前 pet 可见状态
  ipcMain.handle('pet-get-visible', () => petWindow?.isVisible() ?? false)

  // ── 番茄钟悬浮窗 IPC ──
  // 渲染进程发送计时数据 → 悬浮窗更新显示
  ipcMain.on('pomodoro-widget-update', (_event, data) => {
    if (data.phase === 'idle') {
      hidePomodoroWidget()
    } else {
      showPomodoroWidget(data)
    }
  })
  // 渲染进程请求关闭悬浮窗
  ipcMain.on('pomodoro-widget-hide', () => {
    hidePomodoroWidget()
  })

  // 宠物气泡内容更新 → 中转到主窗口侧边栏状态
  ipcMain.on('pet-activity-update', (_event, data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('pet-activity', data)
    }
  })

  // 分心告警：主窗口 → 宠物窗口（宠物变红提示）
  ipcMain.on('distraction-alert', (_event, data) => {
    if (petWindow && !petWindow.isDestroyed()) {
      petWindow.webContents.send('distraction-alert', data)
    }
  })

  // 后端状态
  ipcMain.handle('get-backend-port', () => BACKEND_PORT)

  // API Token
  ipcMain.handle('get-api-token', (_event) => {
    console.log('[IPC] get-api-token called')
    try {
      const token = readApiToken()
      console.log('[IPC] get-api-token returning, length:', token.length)
      return token
    } catch (e) {
      console.error('[IPC] get-api-token error:', e?.message || e, e?.stack || '')
      return ''
    }
  })

  // 自动更新（敏感通道：校验 sender 来源）
  ipcMain.handle('check-for-updates', (event) => {
    if (!isFromMainWindow(event.sender)) return false
    checkForUpdates()
    return true
  })
  ipcMain.handle('download-update', (event) => {
    if (!isFromMainWindow(event.sender)) return false
    downloadUpdate()
    return true
  })
  ipcMain.handle('install-update', (event) => {
    if (!isFromMainWindow(event.sender)) return false
    installUpdate()
    return true
  })
  ipcMain.handle('get-app-version', () => app.getVersion())

  // 桌面通知
  ipcMain.on('show-notification', (_event, { title, body }) => {
    if (Notification.isSupported()) {
      const notification = new Notification({
        title,
        body,
        icon: getNotificationIcon(),
        silent: false,
      })
      notification.on('click', () => {
        mainWindow?.show()
        mainWindow?.focus()
      })
      notification.show()
    }
  })

  // 开机自启动
  ipcMain.handle('get-auto-start', () => {
    const settings = app.getLoginItemSettings()
    return settings.openAtLogin
  })
  ipcMain.handle('set-auto-start', (_event, enabled) => {
    app.setLoginItemSettings({ openAtLogin: !!enabled, path: app.getPath('exe') })
    console.log('[IPC] auto-start set to:', !!enabled)
    return true
  })

  // Windows 系统定位（通过 WinRT Geolocator API，精度 ~30-500m WiFi 定位）
  // 敏感通道：校验 sender 来源，仅允许主窗口
  ipcMain.handle('get-windows-location', async (event) => {
    if (!isFromMainWindow(event.sender)) return null
    return new Promise((resolve) => {
      // 写临时脚本文件避免 -Command 中 $ 变量被外层 shell 吞掉
      // 使用随机文件名，避免被攻击者预创建同名文件进行劫持/竞争
      const os = require('os')
      const path = require('path')
      const fs = require('fs')
      const tmpScript = path.join(os.tmpdir(), 'cd_geo_' + crypto.randomBytes(8).toString('hex') + '.ps1')
      const scriptContent =
        'Add-Type -AssemblyName System.Runtime.WindowsRuntime\n' +
        '[Windows.Devices.Geolocation.Geolocator, Windows.Devices.Geolocation, ContentType = WindowsRuntime] | Out-Null\n' +
        '[Windows.Devices.Geolocation.Geoposition, Windows.Devices.Geolocation, ContentType = WindowsRuntime] | Out-Null\n' +
        '$asTaskMethod = $null\n' +
        'foreach ($m in [System.WindowsRuntimeSystemExtensions].GetMethods()) {\n' +
        '  if ($m.Name -ne "AsTask") { continue }\n' +
        '  $ps = $m.GetParameters()\n' +
        '  if ($ps.Count -ne 1) { continue }\n' +
        '  $pt = $ps[0].ParameterType\n' +
        "  if ($pt.IsGenericType -and $pt.GetGenericTypeDefinition().Name -like 'IAsyncOperation*') {\n" +
        '    $asTaskMethod = $m\n' +
        '    break\n' +
        '  }\n' +
        '}\n' +
        'if (-not $asTaskMethod) { Write-Output "ERROR:no_asTask_method"; exit }\n' +
        '$locator = New-Object Windows.Devices.Geolocation.Geolocator\n' +
        '$locator.DesiredAccuracy = [Windows.Devices.Geolocation.PositionAccuracy]::High\n' +
        '$locator.DesiredAccuracyInMeters = 50\n' +
        '$asyncOp = $locator.GetGeopositionAsync()\n' +
        '$task = $asTaskMethod.MakeGenericMethod([Windows.Devices.Geolocation.Geoposition]).Invoke($null, @($asyncOp))\n' +
        '[void]$task.Wait(15000)\n' +
        'if ($task.IsCompleted) {\n' +
        '  $pos = $task.Result\n' +
        '  $c = $pos.Coordinate\n' +
        '  Write-Output "$($c.Point.Position.Latitude),$($c.Point.Position.Longitude),$($c.Accuracy)"\n' +
        '} else { Write-Output "TIMEOUT" }\n';
      try { fs.writeFileSync(tmpScript, scriptContent, 'utf8') } catch (e) { return resolve(null) }

      const cmd = `powershell -NoProfile -ExecutionPolicy Bypass -File "${tmpScript}"`
      exec(cmd, { timeout: 20000, windowsHide: true }, (err, stdout, stderr) => {
        try { fs.unlinkSync(tmpScript) } catch {}
        if (err || !stdout || stdout.trim() === 'TIMEOUT') {
          console.error('[GeoLocation] WinRT location failed:', err?.message || stderr || 'timeout')
          return resolve(null)
        }
        const lines = stdout.trim().split('\n')
        const coordLine = lines.find(l => l.match(/^\d/)) || lines[lines.length - 1]
        const parts = coordLine.split(',')
        if (parts.length < 2) return resolve(null)
        const lat = parseFloat(parts[0])
        const lon = parseFloat(parts[1])
        const accuracy = parts[2] ? parseFloat(parts[2]) : null
        if (!isNaN(lat) && !isNaN(lon)) {
          console.log(`[GeoLocation] WinRT OK: lat=${lat}, lon=${lon}, accuracy=${accuracy}m`)
          resolve({ lat, lon, accuracy, status: 'OK' })
        } else {
          resolve(null)
        }
      })
    })
  })
}

// ─── 全局快捷键 ────────────────────────────────────
// 安全调用后端：Token 走 HTTP header（X-API-Token），避免泄露到 URL query / 日志
function backendGet(apiPath, cb) {
  const options = {
    hostname: '127.0.0.1',
    port: BACKEND_PORT,
    path: apiPath,
    method: 'GET',
    headers: { 'X-API-Token': readApiToken() },
  }
  const req = http.request(options, (res) => {
    let body = ''
    res.on('data', (d) => { body += d })
    res.on('end', () => cb(null, body, res))
  })
  req.on('error', (err) => cb(err))
  req.setTimeout(10000, () => { req.destroy() })
  req.end()
}

function registerShortcuts() {
  // Ctrl+Shift+S — 手动截图
  const ret1 = globalShortcut.register('CommandOrControl+Shift+S', () => {
    backendGet('/api/capture', () => {
      sendToRenderer('collector-action', 'capture')
    })
  })

  // Ctrl+Shift+P — 暂停/恢复采集
  globalShortcut.register('CommandOrControl+Shift+P', () => {
    backendGet('/api/status', (err, body) => {
      if (err) return
      try {
        const status = JSON.parse(body)
        const action = status.paused ? 'resume' : 'pause'
        backendGet(`/api/collector/${action}`, () => {
          sendToRenderer('collector-action', action)
        })
      } catch (_) {}
    })
  })

  // Ctrl+Shift+R — 生成日报
  globalShortcut.register('CommandOrControl+Shift+R', () => {
    backendGet('/api/report/daily', () => {
      sendToRenderer('generate-report', 'daily')
      mainWindow?.show()
    })
  })

  // Ctrl+Shift+H — 显示/隐藏主窗口
  globalShortcut.register('CommandOrControl+Shift+H', () => {
    if (mainWindow?.isVisible()) {
      mainWindow.hide()
    } else {
      mainWindow?.show()
      mainWindow?.focus()
    }
  })

  console.log('[Main] Global shortcuts registered')

  // F12 to toggle DevTools (manual, not auto-open) — 仅开发环境允许
  mainWindow?.webContents.on('before-input-event', (_event, input) => {
    if (input.key === 'F12') {
      if (!isDev) return  // 生产环境禁用
      if (mainWindow.webContents.isDevToolsOpened()) {
        mainWindow.webContents.closeDevTools()
      } else {
        mainWindow.webContents.openDevTools({ mode: 'detach' })
      }
    }
  })

  // 生产环境：若 DevTools 被以其他方式打开，则强制关闭
  if (!isDev && mainWindow) {
    mainWindow.webContents.on('devtools-opened', () => {
      mainWindow.webContents.closeDevTools()
    })
  }
}

function readApiToken(maxAttempts = 1) {
  try {
    const fs = require('fs')
    const path = require('path')
    // 查找顺序说明：
    // 持久化目录 backend-data 必须排在最前——后端实际通过 CHALLENGE_DAILY_DATA_DIR
    // 环境变量把 .api_token 写入此目录。若把 _backendDir/data 放在前面，
    // 会读到源码目录下残留的旧 token，与后端当前 token 不匹配 → 401 → 断连误判。
    const possibleDirs = []
    possibleDirs.push(path.join(app.getPath('userData'), 'backend-data'))
    if (_backendDir) possibleDirs.push(path.join(_backendDir, 'data'))
    possibleDirs.push(path.join(__dirname, '..', '..', 'data'))
    possibleDirs.push(path.join(app.getPath('userData'), 'data'))
    possibleDirs.push(path.join(process.resourcesPath, 'backend', 'data'))
    possibleDirs.push(path.join(process.resourcesPath, 'data'))

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      for (const dataDir of possibleDirs) {
        const tokenPath = path.join(dataDir, '.api_token')
        try {
          if (fs.existsSync(tokenPath)) {
            return fs.readFileSync(tokenPath, 'utf-8').trim()
          }
        } catch (_) {}
      }
      if (attempt < maxAttempts - 1) {
        // 同步等待 200ms，主进程启动阶段可接受
        const t = Date.now()
        while (Date.now() - t < 200) {}
      }
    }
  } catch (_) {}
  return ''
}

// ─── 自动更新 ────────────────────────────────────
let autoUpdater = null
try {
  autoUpdater = require('electron-updater').autoUpdater
  autoUpdater.autoDownload = false   // 不自动下载，先提示用户
  autoUpdater.autoInstallOnAppQuit = true  // 退出时自动安装
  autoUpdater.setFeedURL({
    provider: 'github',
    owner: 'ChallengeDaily',
    repo: 'ChallengeDaily',
  })
  // P0-11: 禁用更新缓存，避免拿到缓存的旧版本元数据
  autoUpdater.requestHeaders = { 'Cache-Control': 'no-cache' }
  // 签名校验：未来购买代码签名证书后启用
  // autoUpdater.verifyUpdateCodeSignature = true

  autoUpdater.on('update-available', (info) => {
    // 通知渲染进程有新版本
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-available', {
        version: info.version,
        releaseNotes: info.releaseNotes,
      })
    }
  })

  autoUpdater.on('download-progress', (progress) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-progress', {
        percent: progress.percent,
        transferred: progress.transferred,
        total: progress.total,
      })
    }
  })

  autoUpdater.on('update-downloaded', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-downloaded')
    }
  })

  autoUpdater.on('error', (err) => {
    console.error('[Updater] Error:', err.message)
  })
} catch (e) {
  console.warn('[Updater] electron-updater not available:', e.message)
}

function checkForUpdates() {
  if (autoUpdater && app.isPackaged) {
    autoUpdater.checkForUpdates().catch(() => {})
  }
}

function downloadUpdate() {
  if (autoUpdater) {
    autoUpdater.downloadUpdate().catch(() => {})
  }
}

function installUpdate() {
  if (autoUpdater) {
    setImmediate(() => autoUpdater.quitAndInstall())
  }
}

// ─── EPIPE 安全日志 ──────────────────────────────────
// Windows 上后端进程被杀后，stdout/stderr 管道关闭，
// console.log/warn/error 写入会触发 EPIPE 未捕获异常导致弹窗。
// 所有定时器回调中的日志必须使用 safeLog 包装。
function safeLog(fn, ...args) {
  try { fn(...args) } catch (e) { /* EPIPE: pipe closed — ignore */ }
}

// 防止 EPIPE 等管道错误弹窗覆盖应用
process.on('uncaughtException', (err) => {
  if (err.code === 'EPIPE') {
    // 后端进程已退出，管道关闭，忽略即可
    return
  }
  // 其他未捕获异常仍然记录
  safeLog(console.error, '[uncaughtException]', err)
})

// ─── 崩溃监控 & Watchdog & 心跳检测 ──────────────────
// 参考 Kubernetes liveness/readiness probe 模式：
//   1. 进程崩溃：指数退避重启（3s → 5s → 10s → 20s → 30s）
//   2. 心跳检测：每 60 秒探测 /api/health，连续 3 次失败则强制重启后端
//   3. 重启次数上限：10 次，超过后停止自动重启并提示用户
let _crashCount = 0
const _CRASH_THRESHOLD = 10       // 崩溃重启上限
const _CRASH_WINDOW_SEC = 60      // 60秒内崩溃计数窗口

// 全局定时器引用（在 before-quit 中清理，防止退出后定时器继续触发导致异常）
let _healthInterval = null
let _updateInterval = null

// 重启互斥锁：避免心跳重启与崩溃重启同时进行导致重复 spawn
let _restartMutex = false
async function safeRestartBackend() {
  if (_restartMutex) return false
  _restartMutex = true
  try {
    stopBackend()
    await new Promise(r => setTimeout(r, 3000))
    await startBackend()
    watchBackend()  // re-attach watcher
    return true
  } catch (e) {
    safeLog(console.error, '[safeRestartBackend] failed:', e)
    return false
  } finally {
    _restartMutex = false
  }
}

function watchBackend() {
  if (!backendProcess) return
  backendProcess.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      _crashCount++
      safeLog(console.error, `[Watchdog] Backend crashed (code=${code}), crash count: ${_crashCount}/${_CRASH_THRESHOLD}`)

      // 超过崩溃上限：停止自动重启并提示用户
      if (_crashCount >= _CRASH_THRESHOLD) {
        safeLog(console.error, `[Watchdog] Crash threshold (${_CRASH_THRESHOLD}) reached, stopping auto-restart`)
        try {
          dialog.showErrorBox('后端服务异常', '后端服务多次崩溃，已停止自动重启。请检查日志或联系技术支持。')
        } catch (_) {}
        return
      }

      // 指数退避重启：3s → 5s → 10s → 20s → 30s
      const delay = _crashCount <= 1 ? 3000
        : _crashCount === 2 ? 5000
        : _crashCount === 3 ? 10000
        : _crashCount === 4 ? 20000
        : 30000  // 封顶 30 秒
      safeLog(console.log, `[Watchdog] Restarting backend in ${delay/1000}s (attempt ${_crashCount})...`)

      setTimeout(async () => {
        const ok = await safeRestartBackend()
        if (ok) {
          safeLog(console.log, '[Watchdog] Backend restarted successfully')
        } else {
          safeLog(console.error, '[Watchdog] Restart skipped or failed')
        }
      }, delay)
    } else {
      _crashCount = 0  // 正常退出则重置计数
    }
  })
}

// ─── 心跳检测（Liveness Probe）──────────────────────
// 优化：从 30 秒调整为 60 秒，本地服务无需高频探测
// 连续 3 次失败（即 3 分钟无响应）才触发重启
let _healthFailCount = 0
const _HEALTH_FAIL_THRESHOLD = 3
const _HEALTH_CHECK_INTERVAL_MS = 60000

function startHealthCheck() {
  const checkHealth = async () => {
    try {
      const ok = await isBackendRunning()
      if (ok) {
        _healthFailCount = 0
      } else {
        _healthFailCount++
        safeLog(console.warn, `[HealthCheck] Backend not responding (${_healthFailCount}/${_HEALTH_FAIL_THRESHOLD})`)

        if (_healthFailCount >= _HEALTH_FAIL_THRESHOLD) {
          safeLog(console.error, '[HealthCheck] Backend unresponsive, forcing restart...')
          _healthFailCount = 0
          // 通过互斥锁安全重启
          safeRestartBackend().then((ok) => {
            if (ok) safeLog(console.log, '[HealthCheck] Backend restarted after health check failure')
            else safeLog(console.error, '[HealthCheck] Restart skipped or failed')
          })
        }
      }
    } catch (e) {
      // 心跳检测异常不中断循环
      safeLog(console.error, '[HealthCheck] Error:', e.message)
    }
  }

  // 延迟 10 秒后开始心跳检测（给后端启动时间）
  setTimeout(() => {
    _healthInterval = setInterval(checkHealth, _HEALTH_CHECK_INTERVAL_MS)
  }, 10000)
}

function _addNotification_dedup(title, body, type) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend-crash', { title, body, type })
  }
}

// ─── 应用生命周期 ────────────────────────────────────
app.whenReady().then(async () => {
  // 安全守卫：即使 app.exit(0) 的时序出现异常，也不会在未获取锁的情况下启动后端
  if (!gotTheLock) {
    console.log('[Main] app ready but no singleton lock, exiting')
    app.exit(0)
    return
  }
  console.log('[Main] app ready, starting backend...')

  // 权限请求处理器：仅允许 notifications 与 geolocation，其他一律拒绝
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => {
    const allowed = new Set(['notifications', 'geolocation'])
    cb(allowed.has(permission))
  })
  try {
    await startBackend()
    watchBackend()  // 启动崩溃监控
    startHealthCheck()  // 启动心跳检测（Kubernetes liveness probe 模式）
    console.log('[Main] Backend start sequence completed')
  } catch (err) {
    console.error('[Main] Backend start failed, continuing without it:', err)
    console.error('[Main] Error stack:', err.stack)
  }

  createMainWindow()
  // 延迟创建宠物窗口：等主窗口加载完成后由渲染进程根据 localStorage 决定是否创建
  // 这样可以避免用户关闭宠物后仍然出现白色残留窗口
  createTray()
  setupIPC()
  registerShortcuts()

  // 启动后30秒检查更新（仅打包版）
  setTimeout(checkForUpdates, 30000)
  // 每8小时检查一次更新（降低频率，减少网络请求和 CPU 唤醒）
  _updateInterval = setInterval(checkForUpdates, 8 * 60 * 60 * 1000)
})

app.on('window-all-closed', () => {
  // 不退出，保持托盘运行
})

app.on('before-quit', () => {
  // 清理定时器，防止退出后定时器继续触发导致异常
  if (_healthInterval) clearInterval(_healthInterval)
  if (_updateInterval) clearInterval(_updateInterval)
  stopBackend()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow()
  } else {
    mainWindow?.show()
  }
})
