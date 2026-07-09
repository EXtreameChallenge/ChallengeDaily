/// <reference types="vite/client" />

interface Window {
  electronAPI?: {
    minimize: () => void
    maximize: () => void
    close: () => void
    show: () => void
    togglePet: (show: boolean) => void
    getBackendPort: () => Promise<number>
    getApiToken: () => Promise<string>
    checkForUpdates: () => Promise<boolean>
    downloadUpdate: () => Promise<boolean>
    installUpdate: () => Promise<boolean>
    getAppVersion: () => Promise<string>
    onUpdateAvailable: (cb: (info: { version: string; releaseNotes?: string }) => void) => void
    onUpdateProgress: (cb: (progress: { percent: number; transferred: number; total: number }) => void) => void
    onUpdateDownloaded: (cb: () => void) => void
    onBackendCrash: (cb: (data: { title: string; body: string; type: string }) => void) => void
    onCollectorAction: (cb: (data: string) => void) => void
    onGenerateReport: (cb: (data: string) => void) => void
    showNotification: (opts: { title: string; body: string }) => void
    getWindowsLocation: () => Promise<{ lat: number; lon: number; status?: string } | null>
  }
  _petVisible?: boolean
}

declare module 'lunar-javascript'
