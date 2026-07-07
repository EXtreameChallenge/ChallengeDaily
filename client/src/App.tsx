import { useState, useEffect, useRef, lazy, Suspense } from 'react'
import { HashRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import TitleBar from './components/TitleBar'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastProvider } from './components/Toast'
import { ThemeProvider } from './components/ThemeContext'
import { BackendStatusBar } from './components/shared'
import Pet from './components/Pet'
import { healthCheck, getNotifications } from './api/client'

// 懒加载页面组件 — 减少首屏加载体积
const Overview = lazy(() => import('./pages/Overview'))
const Timeline = lazy(() => import('./pages/Timeline'))
const Report = lazy(() => import('./pages/Report'))
const Heatmap = lazy(() => import('./pages/Heatmap'))
const AppRecords = lazy(() => import('./pages/AppRecords'))
const HistoryReports = lazy(() => import('./pages/HistoryReports'))
const Settings = lazy(() => import('./pages/Settings'))
const AgentPage = lazy(() => import('./pages/Agent'))
const AppTags = lazy(() => import('./pages/AppTags'))
const Onboarding = lazy(() => import('./pages/Onboarding'))
const Legal = lazy(() => import('./pages/Legal'))
const Profile = lazy(() => import('./pages/Profile'))
const Health = lazy(() => import('./pages/Health'))
const DeepInsightPage = lazy(() => import('./pages/DeepInsight'))
const Focus = lazy(() => import('./pages/Focus'))
const Todos = lazy(() => import('./pages/Todos'))
const Diary = lazy(() => import('./pages/Diary'))
const Achievements = lazy(() => import('./pages/Achievements'))
const Countdowns = lazy(() => import('./pages/Countdowns'))
const AIChat = lazy(() => import('./pages/AIChat'))
const Habits = lazy(() => import('./pages/Habits'))

// 首次启动流程：法律协议 → 新手引导 → 主界面
type FirstLaunchPhase = 'legal' | 'onboarding' | 'done'

export default function App() {
  const [backendReady, setBackendReady] = useState(false)
  const [checking, setChecking] = useState(true)
  const [firstLaunchPhase, setFirstLaunchPhase] = useState<FirstLaunchPhase>('done')

  // 桌面宠物可见性（简化版：主窗口内浮动 div）
  const [petVisible, setPetVisible] = useState(() => localStorage.getItem('cd_pet_visible') !== '0')
  useEffect(() => {
    const sync = () => setPetVisible(localStorage.getItem('cd_pet_visible') !== '0')
    window.addEventListener('cd-pet-visible-change', sync)
    return () => window.removeEventListener('cd-pet-visible-change', sync)
  }, [])
  const handleTogglePet = (show: boolean) => {
    setPetVisible(show)
    localStorage.setItem('cd_pet_visible', show ? '1' : '0')
    window.dispatchEvent(new CustomEvent('cd-pet-visible-change'))
    // 简化版：宠物为主窗口内浮动 div，不调用独立窗口 IPC
  }

  useEffect(() => {
    let attempts = 0
    const interval = setInterval(async () => {
      attempts++
      try {
        await healthCheck()
        setBackendReady(true)
        setChecking(false)
        clearInterval(interval)
      } catch {
        if (attempts >= 120) {  // 2 minutes
          setChecking(false)
          clearInterval(interval)
        }
      }
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (backendReady) {
      const legalDone = localStorage.getItem('cd_legal_accepted')
      const onboardingDone = localStorage.getItem('cd_onboarding_done')
      if (!legalDone) {
        setFirstLaunchPhase('legal')
      } else if (!onboardingDone) {
        setFirstLaunchPhase('onboarding')
      } else {
        setFirstLaunchPhase('done')
      }
    }
  }, [backendReady])

  const handleLegalAccepted = () => {
    localStorage.setItem('cd_legal_accepted', '1')
    const onboardingDone = localStorage.getItem('cd_onboarding_done')
    if (!onboardingDone) {
      setFirstLaunchPhase('onboarding')
    } else {
      setFirstLaunchPhase('done')
    }
  }

  const handleOnboardingComplete = () => {
    localStorage.setItem('cd_onboarding_done', '1')
    setFirstLaunchPhase('done')
  }

  // ── 自动更新状态 ──
  const [updateInfo, setUpdateInfo] = useState<{ version: string; releaseNotes?: string } | null>(null)
  const [updateProgress, setUpdateProgress] = useState<{ percent: number } | null>(null)
  const [updateDownloaded, setUpdateDownloaded] = useState(false)
  const [updateDismissed, setUpdateDismissed] = useState(false)

  useEffect(() => {
    if (!window.electronAPI) return
    window.electronAPI.onUpdateAvailable((info) => {
      setUpdateInfo(info)
      setUpdateDismissed(false)
    })
    window.electronAPI.onUpdateProgress((progress) => {
      setUpdateProgress(progress)
    })
    window.electronAPI.onUpdateDownloaded(() => {
      setUpdateDownloaded(true)
    })
  }, [])

  const handleInstallUpdate = () => {
    window.electronAPI?.installUpdate()
  }

  // ── 桌面通知轮询 ──
  const notifiedIds = useRef(new Set<number>())
  useEffect(() => {
    if (!backendReady) return
    const poll = async () => {
      try {
        const { notifications } = await getNotifications()
        for (const n of notifications) {
          if (!notifiedIds.current.has(n.id)) {
            notifiedIds.current.add(n.id)
            // 通过 Electron 弹出系统通知
            if (window.electronAPI?.showNotification) {
              window.electronAPI.showNotification({ title: n.title, body: n.body })
            }
          }
        }
      } catch {
        // 通知轮询失败不影响主流程
      }
    }
    // 优化：从 30 秒调整为 60 秒，窗口隐藏时暂停轮询
    poll()
    const interval = setInterval(() => {
      if (!document.hidden) poll()
    }, 60000)
    // 窗口恢复可见时立即检查一次
    const onVisible = () => { if (!document.hidden) poll() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [backendReady])

  return (
    <ThemeProvider>
      <ToastProvider>
        <ErrorBoundary>
          <div className="flex flex-col h-screen bg-cd-bg">
            <TitleBar />
          <BackendStatusBar />
          {/* ── 全局更新提示条 ── */}
          {updateInfo && !updateDismissed && !updateDownloaded && (
            <div className="bg-cd-green/10 border-b border-cd-green/20 px-4 py-2 flex items-center justify-between text-sm">
              <span className="text-cd-text-secondary">
                发现新版本 <span className="font-medium text-cd-green">v{updateInfo.version}</span>
                {updateProgress ? (
                  <span className="ml-2 text-cd-text-tertiary">
                    下载中 {updateProgress.percent.toFixed(0)}%
                  </span>
                ) : (
                  <button
                    onClick={() => window.electronAPI?.downloadUpdate()}
                    className="ml-2 text-cd-green hover:underline font-medium"
                  >
                    立即下载
                  </button>
                )}
              </span>
              <button
                onClick={() => setUpdateDismissed(true)}
                className="text-cd-text-tertiary hover:text-cd-text text-xs"
              >
                稍后提醒
              </button>
            </div>
          )}
          {updateDownloaded && (
            <div className="bg-cd-green/10 border-b border-cd-green/20 px-4 py-2 flex items-center justify-between text-sm">
              <span className="text-cd-text-secondary">
                新版本已就绪，重启后即可安装
              </span>
              <button
                onClick={handleInstallUpdate}
                className="bg-cd-green text-white px-3 py-1 rounded-md text-xs font-medium hover:opacity-90"
              >
                立即重启安装
              </button>
            </div>
          )}
          <div className="flex flex-1 overflow-hidden">
            {checking ? (
              <LoadingScreen />
            ) : !backendReady ? (
              <ErrorScreen />
            ) : firstLaunchPhase === 'legal' ? (
              <Suspense fallback={<PageSpinner />}>
                <Legal onAccept={handleLegalAccepted} />
              </Suspense>
            ) : firstLaunchPhase === 'onboarding' ? (
              <Onboarding onComplete={handleOnboardingComplete} />
            ) : (
              <HashRouter>
                <Sidebar />
                <main className="flex-1 overflow-auto bg-cd-bg p-6">
                  <ErrorBoundary>
                    <Suspense fallback={<PageSpinner />}>
                      <Routes>
                        <Route path="/" element={<Overview />} />
                        <Route path="/timeline" element={<Timeline />} />
                        <Route path="/report" element={<Report />} />
                        <Route path="/focus" element={<Focus />} />
                        <Route path="/todos" element={<Todos />} />
                        <Route path="/diary" element={<Diary />} />
                        <Route path="/heatmap" element={<Heatmap />} />
                        <Route path="/apps" element={<AppRecords />} />
                        <Route path="/app-tags" element={<AppTags />} />
                        <Route path="/history" element={<HistoryReports />} />
                        <Route path="/agent" element={<AgentPage />} />
                        <Route path="/settings" element={<Settings />} />
                        <Route path="/profile" element={<Profile />} />
                        <Route path="/deep-insight" element={<DeepInsightPage />} />
                        <Route path="/achievements" element={<Achievements />} />
                        <Route path="/countdowns" element={<Countdowns />} />
                        <Route path="/ai-chat" element={<AIChat />} />
                        <Route path="/habits" element={<Habits />} />
                        <Route path="/health" element={<Health />} />
                        <Route path="*" element={<NotFoundPage />} />
                      </Routes>
                    </Suspense>
                  </ErrorBoundary>
                </main>
              </HashRouter>
            )}
          </div>
        </div>
        {/* 桌面宠物（简化版：主窗口内浮动） */}
        {backendReady && firstLaunchPhase === 'done' && (
          <Pet visible={petVisible} onToggle={handleTogglePet} />
        )}
      </ErrorBoundary>
    </ToastProvider>
  </ThemeProvider>
  )
}

function PageSpinner() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="w-6 h-6 border-3 border-cd-green border-t-transparent rounded-full animate-spin" />
    </div>
  )
}

function LoadingScreen() {
  return (
    <div className="flex-1 flex items-center justify-center bg-cd-bg">
      <div className="text-center">
        <div className="w-10 h-10 border-4 border-cd-green border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-cd-text-tertiary text-sm">正在连接后端服务...</p>
      </div>
    </div>
  )
}

function ErrorScreen() {
  const [retrying, setRetrying] = useState(false)

  const handleRetry = async () => {
    setRetrying(true)
    try {
      await healthCheck()
      window.location.reload()
    } catch {
      setRetrying(false)
    }
  }

  return (
    <div className="flex-1 flex items-center justify-center bg-cd-bg">
      <div className="text-center max-w-md">
        <div className="text-5xl mb-4">⚠️</div>
        <h2 className="text-lg font-semibold text-cd-text mb-2">后端服务未启动</h2>
        <p className="text-cd-text-secondary text-sm mb-4">
          桌面客户端正在自动启动后端，请稍候...
        </p>
        <button
          onClick={handleRetry}
          disabled={retrying}
          className="bg-cd-green text-white px-4 py-2 rounded-lg text-sm hover:opacity-90 disabled:opacity-50"
        >
          {retrying ? '正在重连...' : '重新连接'}
        </button>
      </div>
    </div>
  )
}

function NotFoundPage() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="text-6xl font-bold text-cd-text-tertiary mb-4">404</div>
        <h2 className="text-lg font-semibold text-cd-text mb-2">页面不存在</h2>
        <a href="#/" className="text-cd-green hover:underline text-sm">返回首页</a>
      </div>
    </div>
  )
}
