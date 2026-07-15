const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  // 窗口控制
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  show: () => ipcRenderer.send('window-show'),

  // 宠物控制
  togglePet: (show) => ipcRenderer.send('pet-toggle', show),
  getPetVisible: () => ipcRenderer.invoke('pet-get-visible'),
  // 窗口拖拽（宠物窗口专用）
  petWindowDrag: (dx, dy) => ipcRenderer.send('pet-window-drag', { mouseX: dx, mouseY: dy }),

  // 后端端口
  getBackendPort: () => ipcRenderer.invoke('get-backend-port'),

  // API Token（通过 IPC 从主进程读取，兼容 Electron 31 sandbox 模式）
  getApiToken: () => ipcRenderer.invoke('get-api-token'),

  // 自动更新
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  downloadUpdate: () => ipcRenderer.invoke('download-update'),
  installUpdate: () => ipcRenderer.invoke('install-update'),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  onUpdateAvailable: (cb) => ipcRenderer.on('update-available', (_e, data) => cb(data)),
  onUpdateProgress: (cb) => ipcRenderer.on('update-progress', (_e, data) => cb(data)),
  onUpdateDownloaded: (cb) => ipcRenderer.on('update-downloaded', () => cb()),
  onBackendCrash: (cb) => ipcRenderer.on('backend-crash', (_e, data) => cb(data)),

  // 监听来自主进程的消息
  onCollectorAction: (callback) => ipcRenderer.on('collector-action', (_event, data) => callback(data)),
  onGenerateReport: (callback) => ipcRenderer.on('generate-report', (_event, data) => callback(data)),

  // 桌面通知
  showNotification: ({ title, body }) => ipcRenderer.send('show-notification', { title, body }),

  // Windows 系统定位（主进程调用 PowerShell）
  getWindowsLocation: () => ipcRenderer.invoke('get-windows-location'),

  // 番茄钟悬浮窗
  pomodoroWidgetUpdate: (data) => ipcRenderer.send('pomodoro-widget-update', data),
  pomodoroWidgetHide: () => ipcRenderer.send('pomodoro-widget-hide'),
  onPomodoroTick: (cb) => ipcRenderer.on('pomodoro-tick', (_e, data) => cb(data)),

  // 分心告警：主窗口 → 主进程 → 宠物窗口
  sendDistractionAlert: (data) => ipcRenderer.send('distraction-alert', data),
  onDistractionAlert: (cb) => ipcRenderer.on('distraction-alert', (_e, data) => cb(data)),

  // 主进程导航指令（悬浮窗点击跳转等）
  onNavigateTo: (cb) => ipcRenderer.on('navigate-to', (_e, path) => cb(path)),

  // P13-4：专注模式切换（全局快捷键 Ctrl+Shift+F 触发）
  onToggleFocusMode: (cb) => ipcRenderer.on('toggle-focus-mode', () => cb()),

  // 开机自启动
  getAutoStart: () => ipcRenderer.invoke('get-auto-start'),
  setAutoStart: (enabled) => ipcRenderer.invoke('set-auto-start', enabled),

  // Windows Hello 生物识别（应用级隐私锁）
  // 返回 { success: boolean, error?: string }；不可用时返回 success:false
  windowsHello: (reason) => ipcRenderer.invoke('windows-hello', reason),
})
