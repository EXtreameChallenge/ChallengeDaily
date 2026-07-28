import { useState, useEffect, useRef, lazy, Suspense, type ReactNode } from 'react'
import { HashRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import TitleBar from './components/TitleBar'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastProvider } from './components/Toast'
import { ThemeProvider } from './components/ThemeContext'
import { BackendStatusBar } from './components/shared'
import { getNotifications, startupHealthCheck } from './api/client'
import { useAppLock, LockScreen } from './components/AppLock'
import { CommandPalette, useCommandPaletteShortcut } from './components/CommandPalette'
import { ShortcutHelp, useShortcutHelpShortcut } from './components/ShortcutHelp'

// 懒加载页面组件 — 减少首屏加载体积
const Overview = lazy(() => import('./pages/Overview'))
const Timeline = lazy(() => import('./pages/Timeline'))
const Report = lazy(() => import('./pages/Report'))
const Heatmap = lazy(() => import('./pages/Heatmap'))
const CalendarView = lazy(() => import('./pages/CalendarView'))
const AppRecords = lazy(() => import('./pages/AppRecords'))
const HistoryReports = lazy(() => import('./pages/HistoryReports'))
const Settings = lazy(() => import('./pages/Settings'))
const AgentPage = lazy(() => import('./pages/Agent'))
const AppTags = lazy(() => import('./pages/AppTags'))
const Onboarding = lazy(() => import('./pages/Onboarding'))
const Legal = lazy(() => import('./pages/Legal'))
const DeepProfile = lazy(() => import('./pages/DeepProfile'))
const Health = lazy(() => import('./pages/Health'))
const Focus = lazy(() => import('./pages/Focus'))
const Todos = lazy(() => import('./pages/Todos'))
const Diary = lazy(() => import('./pages/Diary'))
const Achievements = lazy(() => import('./pages/Achievements'))
const Countdowns = lazy(() => import('./pages/Countdowns'))
const AIChat = lazy(() => import('./pages/AIChat'))
const Habits = lazy(() => import('./pages/Habits'))
const WeekPlan = lazy(() => import('./pages/WeekPlan'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const ExportCenter = lazy(() => import('./pages/ExportCenter'))
const AICoach = lazy(() => import('./pages/AICoach'))
const StudyRoom = lazy(() => import('./pages/StudyRoom'))
const RulesEngine = lazy(() => import('./pages/RulesEngine'))
const Goals = lazy(() => import('./pages/Goals'))
const TimelinePlayer = lazy(() => import('./pages/TimelinePlayer'))
const Inspiration = lazy(() => import('./pages/Inspiration'))
const DailyCards = lazy(() => import('./pages/DailyCards'))
const MemoryPage = lazy(() => import('./pages/MemoryPage'))

// 首次启动流程：法律协议 → 新手引导 → 主界面
type FirstLaunchPhase = 'legal' | 'onboarding' | 'done'

export default function App() {
  const [backendReady, setBackendReady] = useState(false)
  const [checking, setChecking] = useState(true)
  const [firstLaunchPhase, setFirstLaunchPhase] = useState<FirstLaunchPhase>('done')
  const { locked, unlock } = useAppLock()
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false)
  useCommandPaletteShortcut(() => setCmdPaletteOpen(true))
  const [shortcutHelpOpen, setShortcutHelpOpen] = useState(false)
  useShortcutHelpShortcut(() => setShortcutHelpOpen(true))

  useEffect(() => {
    let isCancelled = false
    let attempts = 0
    let timerId: ReturnType<typeof setTimeout> | null = null
    // E9: 启动阶段最大重试：30次1秒 + 30次3秒 ≈ 2分钟（从6分钟缩短）
    const PHASE1_ATTEMPTS = 30
    const MAX_ATTEMPTS = 60

    const scheduleNext = (delay: number) => {
      if (isCancelled) return
      if (timerId !== null) clearTimeout(timerId)
      timerId = setTimeout(async () => {
        if (isCancelled) return
        attempts++
        try {
          // 使用 startupHealthCheck（原始 fetch），不经过 request() 状态机
          // 避免启动阶段的正常等待被误判为"后端断开"
          const ok = await startupHealthCheck()
          if (isCancelled) return
          if (ok) {
            setBackendReady(true)
            setChecking(false)
            return
          }
        } catch {
          // startupHealthCheck 内部已 catch，不会到这里
        }
        if (isCancelled) return
        if (attempts === PHASE1_ATTEMPTS) {
          // 1 秒轮询仍失败，切换到 3 秒轮询
          setChecking(false)
          scheduleNext(3000)
          return
        }
        if (attempts >= MAX_ATTEMPTS) {
          // 达到上限，停止轮询，由 ErrorScreen 提供手动重试
          setChecking(false)
          return
        }
        // 根据当前阶段决定延迟
        const currentDelay = attempts < PHASE1_ATTEMPTS ? 1000 : 3000
        scheduleNext(currentDelay)
      }, delay)
    }

    scheduleNext(1000)
    return () => {
      isCancelled = true
      if (timerId !== null) clearTimeout(timerId)
    }
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
    // 用 cancelled 标志避免 StrictMode 重复注册导致的状态污染
    let cancelled = false
    window.electronAPI.onUpdateAvailable((info) => {
      if (cancelled) return
      setUpdateInfo(info)
      setUpdateDismissed(false)
    })
    window.electronAPI.onUpdateProgress((progress) => {
      if (cancelled) return
      setUpdateProgress(progress)
    })
    window.electronAPI.onUpdateDownloaded(() => {
      if (cancelled) return
      setUpdateDownloaded(true)
    })
    // 应用启动时同步宠物窗口可见性：根据 localStorage 恢复宠物窗口状态
    const petVisible = localStorage.getItem('cd_pet_visible') !== '0'
    window.electronAPI.togglePet(petVisible)
    return () => { cancelled = true }
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
          {/* 应用级隐私锁：启动锁 + 闲置锁 */}
          {locked && <LockScreen onUnlock={unlock} />}
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
                className="text-cd-text-tertiary hover:text-cd-text text-sm"
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
                className="bg-cd-green text-white px-3.5 py-1.5 rounded-md text-sm font-medium hover:opacity-90"
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
                <CommandPalette open={cmdPaletteOpen} onClose={() => setCmdPaletteOpen(false)} />
                <ShortcutHelp open={shortcutHelpOpen} onClose={() => setShortcutHelpOpen(false)} />
                <ElectronNavigationBridge />
                <Sidebar />
                <main className="flex-1 overflow-auto bg-cd-bg p-6">
                  <RouteErrorBoundary>
                    <Suspense fallback={<PageSpinner />}>
                      <Routes>
                        <Route path="/" element={<Overview />} />
                        <Route path="/timeline" element={<Timeline />} />
                        <Route path="/report" element={<Report />} />
                        <Route path="/focus" element={<Focus />} />
                        <Route path="/week-plan" element={<WeekPlan />} />
                        <Route path="/todos" element={<Todos />} />
                        <Route path="/diary" element={<Diary />} />
                        <Route path="/heatmap" element={<Heatmap />} />
                        <Route path="/calendar" element={<CalendarView />} />
                        <Route path="/apps" element={<AppRecords />} />
                        <Route path="/app-tags" element={<AppTags />} />
                        <Route path="/history" element={<HistoryReports />} />
                        <Route path="/agent" element={<AgentPage />} />
                        <Route path="/settings" element={<Settings />} />
                        <Route path="/profile" element={<DeepProfile />} />
                        <Route path="/deep-insight" element={<DeepProfile />} />
                        <Route path="/achievements" element={<Achievements />} />
                        <Route path="/countdowns" element={<Countdowns />} />
                        <Route path="/ai-chat" element={<AIChat />} />
                        <Route path="/dashboard" element={<Dashboard />} />
                        <Route path="/ai-coach" element={<AICoach />} />
                        <Route path="/study-room" element={<StudyRoom />} />
                        <Route path="/rules-engine" element={<RulesEngine />} />
                        <Route path="/goals" element={<Goals />} />
                        <Route path="/timeline-player" element={<TimelinePlayer />} />
                        <Route path="/export" element={<ExportCenter />} />
                        <Route path="/habits" element={<Habits />} />
                        <Route path="/health" element={<Health />} />
                        <Route path="/inspiration" element={<Inspiration />} />
                        <Route path="/daily-cards" element={<DailyCards />} />
                        <Route path="/memory" element={<MemoryPage />} />
                        <Route path="*" element={<NotFoundPage />} />
                      </Routes>
                    </Suspense>
                  </RouteErrorBoundary>
                </main>
              </HashRouter>
            )}
          </div>
        </div>
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

/** P13-4：监听来自 Electron 主进程的导航/快捷键事件 */
function ElectronNavigationBridge() {
  const navigate = useNavigate()
  useEffect(() => {
    if (!window.electronAPI) return
    // 监听全局快捷键导航（Ctrl+Shift+Q → 番茄钟 等）
    const onNav = (path: string) => {
      const pathMap: Record<string, string> = {
        focus: '/focus',
        report: '/report',
        overview: '/',
        habits: '/habits',
        achievements: '/achievements',
      }
      const target = pathMap[path] || path
      navigate(target)
    }
    // 使用通用事件监听（onNavigateTo 已在 preload 声明）
    if (window.electronAPI?.onNavigateTo) {
      window.electronAPI.onNavigateTo(onNav)
    }
    // 专注模式切换（Ctrl+Shift+F）
    if (window.electronAPI?.onToggleFocusMode) {
      window.electronAPI.onToggleFocusMode(() => {
        // 通知 Focus 页面切换专注模式（通过自定义事件）
        window.dispatchEvent(new CustomEvent('toggle-focus-mode'))
      })
    }
    return () => { /* IPC 监听器随组件卸载自动清理 */ }
  }, [navigate])
  return null
}

/** 绑定到当前路由的 ErrorBoundary：路由切换时自动清除错误状态 */
function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation()
  return (
    <ErrorBoundary resetKey={location.pathname}>
      {children}
    </ErrorBoundary>
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
  const [autoRetries, setAutoRetries] = useState(0)
  const maxAutoRetries = 20

  // 自动重试：后端可能还在启动中，每3秒自动探测一次
  useEffect(() => {
    if (autoRetries >= maxAutoRetries) return
    const timer = setTimeout(async () => {
      const ok = await startupHealthCheck()
      if (ok) {
        window.location.reload()
      } else {
        setAutoRetries(prev => prev + 1)
      }
    }, 3000)
    return () => clearTimeout(timer)
  }, [autoRetries])

  const handleRetry = async () => {
    setRetrying(true)
    try {
      const ok = await startupHealthCheck()
      if (ok) {
        window.location.reload()
      } else {
        setRetrying(false)
      }
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
          {autoRetries < maxAutoRetries && (
            <span className="block mt-1 text-cd-text-tertiary">
              自动重连中（第 {autoRetries + 1} 次探测）
            </span>
          )}
        </p>
        <button
          onClick={handleRetry}
          disabled={retrying}
          className="bg-cd-green text-white px-4 py-2 rounded-lg text-sm hover:opacity-90 disabled:opacity-50"
        >
          {retrying ? '正在重连...' : '手动重连'}
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
