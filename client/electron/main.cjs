const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage, screen, globalShortcut, Notification } = require('electron')
const path = require('path')
const { spawn, exec } = require('child_process')
const http = require('http')
const fs = require('fs')

// 把主进程 console 输出持久化到文件，方便排查无窗口启动问题
const mainLogDir = path.join(__dirname, '..', '..', 'data', 'logs')
fs.mkdirSync(mainLogDir, { recursive: true })
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
let tray = null
let backendProcess = null

const BACKEND_PORT = 58888
// isDev: only true for actual development (not start.bat production mode)
// ELECTRON_IS_DEV=0 overrides app.isPackaged for start.bat usage
const isDev = process.env.ELECTRON_IS_DEV === '0' ? false : !app.isPackaged

// Windows 任务栏图标关键：设置 AppUserModelId（必须在 app ready 之前）
app.setAppUserModelId('com.challenge.daily')

// ─── 单实例锁：禁止打开多个窗口 ────────────────────
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  // 已有实例在运行，直接退出
  console.log('[Main] Another instance is already running, quitting...')
  app.quit()
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
function isBackendRunning() {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/health`, (res) => {
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(2000, () => { req.destroy(); resolve(false) })
  })
}

// ─── 启动 Python 后端 ────────────────────────────
async function startBackend() {
  console.log('[Main] startBackend() called')
  // 先检查后端是否已经跑着（比如 start.bat 已启动）
  if (await isBackendRunning()) {
    console.log('[Main] Backend already running, skip spawning')
    return
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
      // 开发模式 或 start.vbs 从源码启动（此时 app.isPackaged 可能误判为 true）
      mainScript = path.join(__dirname, '..', '..', 'main.py')
      backendDir = path.join(__dirname, '..', '..')
      const taPython = path.join(process.env.USERPROFILE || '', '.local', 'share', 'TeleAgent', 'runtimes', 'python', 'python.exe')
      if (fs.existsSync(taPython)) {
        pythonExe = taPython
      }
    }

    console.log('[Main] Starting backend:', pythonExe, mainScript)

    // 启动日志写入文件，方便排查启动失败问题
    const logDir = path.join(backendDir, 'data', 'logs')
    fs.mkdirSync(logDir, { recursive: true })
    const logFile = path.join(logDir, 'electron-backend.log')
    const logStream = fs.createWriteStream(logFile, { flags: 'a' })
    const log = (tag, msg) => {
      const line = `[${new Date().toISOString()}] [${tag}] ${msg}`
      console.log(line)
      logStream.write(line + '\n')
    }
    log('Main', `Starting backend: ${pythonExe} ${mainScript} cwd=${backendDir}`)

    // Clean PYTHONHOME/PYTHONPATH - they may point to broken paths with Chinese chars
    const cleanEnv = { ...process.env }
    delete cleanEnv.PYTHONHOME
    delete cleanEnv.PYTHONPATH
    cleanEnv.PORT = String(BACKEND_PORT)
    cleanEnv.PYTHONIOENCODING = 'utf-8'

    backendProcess = spawn(pythonExe, [mainScript], {
      cwd: backendDir,
      env: cleanEnv,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })

    let resolved = false
    const resolveOnce = () => { if (!resolved) { resolved = true; resolve() } }

    backendProcess.stdout?.on('data', (data) => {
      const msg = data.toString().trim()
      log('Backend', msg)
      if (msg.includes('Running on') || msg.includes('HTTP API 已启动') || msg.includes('Press CTRL+C')) {
        resolveOnce()
      }
    })

    backendProcess.stderr?.on('data', (data) => {
      const msg = data.toString().trim()
      log('BackendErr', msg)
    })

    backendProcess.on('error', (err) => {
      log('BackendFail', err.message)
      if (!resolved) { resolved = true; reject(err) }
    })

    backendProcess.on('exit', (code) => {
      log('BackendExit', `Exited with code: ${code}`)
      backendProcess = null
    })

    // 超时保底：20秒后不管有没有看到成功消息都 resolve
    setTimeout(() => {
      log('Main', 'Backend start timeout, proceeding anyway')
      resolveOnce()
    }, 20000)
  })
}

function stopBackend() {
  if (backendProcess) {
    console.log('[Main] Stopping backend...')
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
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#121212',
    icon: getIconPath(),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
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

  mainWindow.on('close', (e) => {
    e.preventDefault()
    mainWindow.hide()
  })
}

// ─── 桌面宠物窗口 ────────────────────────────────
function createPetWindow() {
  const { width } = screen.getPrimaryDisplay().workAreaSize

  petWindow = new BrowserWindow({
    width: 120,
    height: 120,
    x: width - 150,
    y: 100,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  })

  // 宠物窗口始终置顶但不抢焦点
  petWindow.setAlwaysOnTop(true, 'normal')
  petWindow.setFocusable(false)

  if (isDev) {
    petWindow.loadURL('http://localhost:5173/pet.html')
  } else {
    petWindow.loadFile(path.join(__dirname, '..', 'dist', 'pet.html'))
  }

  // 让宠物可拖拽
  petWindow.on('will-move', () => {})
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

  // 宠物控制
  ipcMain.on('pet-toggle', (_event, show) => {
    if (show) petWindow?.show()
    else petWindow?.hide()
  })

  // 后端状态
  ipcMain.handle('get-backend-port', () => BACKEND_PORT)

  // API Token（sandbox 模式下 renderer 无法直接用 fs，必须通过主进程读取）
  ipcMain.handle('get-api-token', () => readApiToken())

  // 自动更新
  ipcMain.handle('check-for-updates', () => { checkForUpdates(); return true })
  ipcMain.handle('download-update', () => { downloadUpdate(); return true })
  ipcMain.handle('install-update', () => { installUpdate(); return true })
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

  // Windows 系统定位（通过 WinRT Geolocator API，精度 ~30-500m WiFi 定位）
  ipcMain.handle('get-windows-location', async () => {
    return new Promise((resolve) => {
      // 写临时脚本文件避免 -Command 中 $ 变量被外层 shell 吞掉
      const os = require('os')
      const path = require('path')
      const fs = require('fs')
      const tmpScript = path.join(os.tmpdir(), 'cd_geo.ps1')
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
function registerShortcuts() {
  // Ctrl+Shift+S — 手动截图
  const ret1 = globalShortcut.register('CommandOrControl+Shift+S', () => {
    http.get(`http://127.0.0.1:${BACKEND_PORT}/api/capture?token=${readApiToken()}`, (res) => {
      let body = ''
      res.on('data', (d) => body += d)
      res.on('end', () => {
        sendToRenderer('collector-action', 'capture')
      })
    }).on('error', () => {})
  })

  // Ctrl+Shift+P — 暂停/恢复采集
  globalShortcut.register('CommandOrControl+Shift+P', () => {
    http.get(`http://127.0.0.1:${BACKEND_PORT}/api/status?token=${readApiToken()}`, (res) => {
      let body = ''
      res.on('data', (d) => body += d)
      res.on('end', () => {
        try {
          const status = JSON.parse(body)
          const action = status.paused ? 'resume' : 'pause'
          http.get(`http://127.0.0.1:${BACKEND_PORT}/api/collector/${action}?token=${readApiToken()}`, () => {
            sendToRenderer('collector-action', action)
          }).on('error', () => {})
        } catch (_) {}
      })
    }).on('error', () => {})
  })

  // Ctrl+Shift+R — 生成日报
  globalShortcut.register('CommandOrControl+Shift+R', () => {
    http.get(`http://127.0.0.1:${BACKEND_PORT}/api/report/daily?token=${readApiToken()}`, (res) => {
      let body = ''
      res.on('data', (d) => body += d)
      res.on('end', () => {
        sendToRenderer('generate-report', 'daily')
        mainWindow?.show()
      })
    }).on('error', () => {})
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

  // F12 to toggle DevTools (manual, not auto-open)
  mainWindow?.webContents.on('before-input-event', (_event, input) => {
    if (input.key === 'F12') {
      if (mainWindow.webContents.isDevToolsOpened()) {
        mainWindow.webContents.closeDevTools()
      } else {
        mainWindow.webContents.openDevTools({ mode: 'detach' })
      }
    }
  })
}

function readApiToken() {
  try {
    const fs = require('fs')
    const path = require('path')
    // 同时检查多个可能的数据目录，兼容源码运行、start.vbs 启动、打包后运行
    const possibleDirs = [
      path.join(__dirname, '..', '..', 'data'),
      path.join(app.getPath('userData'), 'data'),
      path.join(process.resourcesPath, 'data'),
    ]
    for (const dataDir of possibleDirs) {
      const tokenPath = path.join(dataDir, '.api_token')
      if (fs.existsSync(tokenPath)) {
        return fs.readFileSync(tokenPath, 'utf-8').trim()
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

// ─── 崩溃监控 & Watchdog & 心跳检测 ──────────────────
// 参考 Kubernetes liveness/readiness probe 模式：
//   1. 进程崩溃：指数退避重启（3s → 5s → 10s → 20s → 30s），不放弃
//   2. 心跳检测：每 30 秒探测 /api/health，连续 3 次失败则强制重启后端
//   3. 重启次数上限：设为 999（实际不放弃），避免后端偶尔崩溃后永久无法恢复
let _crashCount = 0
const _CRASH_THRESHOLD = 999      // 不放弃，持续重试
const _CRASH_WINDOW_SEC = 60      // 60秒内崩溃计数窗口

function watchBackend() {
  if (!backendProcess) return
  backendProcess.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      _crashCount++
      console.error(`[Watchdog] Backend crashed (code=${code}), crash count: ${_crashCount}`)

      // 指数退避重启：3s → 5s → 10s → 20s → 30s
      const delay = _crashCount <= 1 ? 3000
        : _crashCount === 2 ? 5000
        : _crashCount === 3 ? 10000
        : _crashCount === 4 ? 20000
        : 30000  // 封顶 30 秒
      console.log(`[Watchdog] Restarting backend in ${delay/1000}s (attempt ${_crashCount})...`)

      setTimeout(async () => {
        try {
          await startBackend()
          watchBackend()  // re-attach watcher
          console.log('[Watchdog] Backend restarted successfully')
        } catch (e) {
          console.error('[Watchdog] Restart failed:', e)
          // 递归重试
          watchBackend()
        }
      }, delay)
    } else {
      _crashCount = 0  // 正常退出则重置计数
    }
  })
}

// ─── 心跳检测（Liveness Probe）──────────────────────
// 每 30 秒探测后端 /api/health，连续 3 次失败则认为后端卡死，强制重启
let _healthFailCount = 0
const _HEALTH_FAIL_THRESHOLD = 3
const _HEALTH_CHECK_INTERVAL_MS = 30000

function startHealthCheck() {
  const checkHealth = async () => {
    try {
      const ok = await isBackendRunning()
      if (ok) {
        _healthFailCount = 0
      } else {
        _healthFailCount++
        console.warn(`[HealthCheck] Backend not responding (${_healthFailCount}/${_HEALTH_FAIL_THRESHOLD})`)

        if (_healthFailCount >= _HEALTH_FAIL_THRESHOLD) {
          console.error('[HealthCheck] Backend unresponsive, forcing restart...')
          _healthFailCount = 0
          // 强制杀掉后端进程并重启
          stopBackend()
          setTimeout(async () => {
            try {
              await startBackend()
              watchBackend()
              console.log('[HealthCheck] Backend restarted after health check failure')
            } catch (e) {
              console.error('[HealthCheck] Restart after health check failed:', e)
            }
          }, 3000)
        }
      }
    } catch (e) {
      // 心跳检测异常不中断循环
      console.error('[HealthCheck] Error:', e.message)
    }
  }

  // 延迟 10 秒后开始心跳检测（给后端启动时间）
  setTimeout(() => {
    setInterval(checkHealth, _HEALTH_CHECK_INTERVAL_MS)
  }, 10000)
}

function _addNotification_dedup(title, body, type) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('backend-crash', { title, body, type })
  }
}

// ─── 应用生命周期 ────────────────────────────────────
app.whenReady().then(async () => {
  console.log('[Main] app ready, starting backend...')
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
  createPetWindow()
  createTray()
  setupIPC()
  registerShortcuts()

  // 启动后10秒检查更新（仅打包版）
  setTimeout(checkForUpdates, 10000)
  // 每4小时检查一次更新
  setInterval(checkForUpdates, 4 * 60 * 60 * 1000)
})

app.on('window-all-closed', () => {
  // 不退出，保持托盘运行
})

app.on('before-quit', () => {
  stopBackend()
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow()
  } else {
    mainWindow?.show()
  }
})
