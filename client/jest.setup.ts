/** Jest 测试环境初始化 */
import '@testing-library/jest-dom'

// ── Mock Electron API（组件测试中依赖 window.electronAPI）──
const mockElectronAPI = {
  onUpdateAvailable: jest.fn(),
  onUpdateProgress: jest.fn(),
  onUpdateDownloaded: jest.fn(),
  installUpdate: jest.fn(),
  downloadUpdate: jest.fn(),
  togglePet: jest.fn(),
  showNotification: jest.fn(),
  getBackendPort: jest.fn().mockResolvedValue(58888),
  getApiToken: jest.fn().mockResolvedValue(''),
}

;(global as any).electronAPI = mockElectronAPI
;(window as any).electronAPI = mockElectronAPI
