const { contextBridge, ipcRenderer } = require('electron')

// P20-8: 统一 IPC 监听器管理 — 每个注册的 listener 都返回反注册函数
// 防止组件卸载后 ipcRenderer 仍持有回调引用导致内存泄漏与重复触发
function _makeManagedListener(channel) {
  return (cb) => {
    const handler = (_e, data) => cb(data)
    ipcRenderer.on(channel, handler)
    // 返回反注册函数，前端 useEffect cleanup 中调用
    return () => {
      try {
        ipcRenderer.removeListener(channel, handler)
      } catch (_) {
        /* ignore */
      }
    }
  }
}

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
  onUpdateAvailable: _makeManagedListener('update-available'),
  onUpdateProgress: _makeManagedListener('update-progress'),
  onUpdateDownloaded: _makeManagedListener('update-downloaded'),
  onBackendCrash: _makeManagedListener('backend-crash'),

  // 监听来自主进程的消息
  onCollectorAction: _makeManagedListener('collector-action'),
  onGenerateReport: _makeManagedListener('generate-report'),

  // 桌面通知
  showNotification: ({ title, body }) => ipcRenderer.send('show-notification', { title, body }),

  // Windows 系统定位（主进程调用 PowerShell）
  getWindowsLocation: () => ipcRenderer.invoke('get-windows-location'),

  // 番茄钟悬浮窗
  pomodoroWidgetUpdate: (data) => ipcRenderer.send('pomodoro-widget-update', data),
  pomodoroWidgetHide: () => ipcRenderer.send('pomodoro-widget-hide'),
  pomodoroWidgetClick: () => ipcRenderer.send('pomodoro-widget-click'),
  onPomodoroTick: _makeManagedListener('pomodoro-tick'),

  // 分心告警：主窗口 → 主进程 → 宠物窗口
  sendDistractionAlert: (data) => ipcRenderer.send('distraction-alert', data),
  onDistractionAlert: _makeManagedListener('distraction-alert'),

  // 主进程导航指令（悬浮窗点击跳转等）
  onNavigateTo: _makeManagedListener('navigate-to'),

  // P13-4：专注模式切换（全局快捷键 Ctrl+Shift+F 触发）
  onToggleFocusMode: _makeManagedListener('toggle-focus-mode'),

  // 开机自启动
  getAutoStart: () => ipcRenderer.invoke('get-auto-start'),
  setAutoStart: (enabled) => ipcRenderer.invoke('set-auto-start', enabled),

  // Windows Hello 生物识别（应用级隐私锁）
  // 返回 { success: boolean, error?: string }；不可用时返回 success:false
  windowsHello: (reason) => ipcRenderer.invoke('windows-hello', reason),

  // ── 幕布文档接入 ──
  // 通用 invoke（白名单受控，仅允许 mubu 相关通道，防止越权调用其他 IPC）
  invoke: (channel, ...args) => {
    const allowed = new Set(['mubu:login', 'mubu:sync-now', 'mubu:sync-status'])
    if (allowed.has(channel)) {
      return ipcRenderer.invoke(channel, ...args)
    }
    return Promise.reject(new Error('Channel not allowed: ' + channel))
  },
  // 幕布同步状态变化监听
  on: (channel, cb) => {
    if (channel === 'mubu:status-change') {
      const handler = (_e, data) => cb(data)
      ipcRenderer.on(channel, handler)
      return () => {
        try { ipcRenderer.removeListener(channel, handler) } catch (_) {}
      }
    }
    return () => {}
  },
})
