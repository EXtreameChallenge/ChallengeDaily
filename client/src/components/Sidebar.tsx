import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  FileText,
  Clock,
  Grid3X3,
  AppWindow,
  History,
  Bot,
  Tags,
  CreditCard,
  Users,
  Shield,
  Settings as SettingsIcon,
  HelpCircle,
  Pause,
  Play,
  Loader2,
  Brain,
  Activity,
  Sparkles,
  Timer,
  CheckSquare,
  BookOpen,
  Trophy,
  Calendar,
  CalendarDays,
  CalendarRange,
  Flame,
  Download,
  TrendingUp,
  Zap,
  Target,
} from 'lucide-react'
import { useState, useEffect } from 'react'
import { getStatus, pauseCollector, resumeCollector, getTodayStats, type CollectorStatus, type TodayStats } from '../api/client'
import { useTheme } from './ThemeContext'

const NAV_GROUPS = [
  {
    label: '工作台',
    items: [
      { to: '/', icon: LayoutDashboard, label: '今日总览' },
    ]
  },
  {
    label: '计划与执行',
    items: [
      { to: '/week-plan', icon: CalendarDays, label: '周计划' },
      { to: '/todos', icon: CheckSquare, label: '待办清单' },
      { to: '/focus', icon: Timer, label: '专注番茄' },
    ]
  },
  {
    label: '数据与回顾',
    items: [
      { to: '/dashboard', icon: TrendingUp, label: '进度仪表盘' },
      { to: '/timeline', icon: Clock, label: '工作时间线' },
      { to: '/heatmap', icon: Grid3X3, label: '时段热力图' },
      { to: '/calendar', icon: CalendarRange, label: '日历视图' },
      { to: '/apps', icon: AppWindow, label: '应用记录' },
      { to: '/report', icon: FileText, label: '生成报告' },
      { to: '/history', icon: History, label: '历史报告' },
      { to: '/export', icon: Download, label: '数据导出' },
      { to: '/health', icon: Activity, label: '数据校准' },
    ]
  },
  {
    label: 'AI 与生活',
    items: [
      { to: '/ai-chat', icon: Bot, label: 'AI 对话' },
      { to: '/ai-coach', icon: Sparkles, label: 'AI 教练' },
      { to: '/profile', icon: Brain, label: '深度画像' },
      { to: '/diary', icon: BookOpen, label: '每日日记' },
      { to: '/habits', icon: Flame, label: '习惯追踪' },
      { to: '/countdowns', icon: Calendar, label: '倒数日' },
      { to: '/achievements', icon: Trophy, label: '成就墙' },
      { to: '/study-room', icon: Users, label: '番茄自习室' },
      { to: '/rules-engine', icon: Zap, label: '规则引擎' },
      { to: '/goals', icon: Target, label: '长期目标' },
    ]
  },
]

const MORE_NAV = [
  { to: '/app-tags',  icon: Tags,         label: '应用标签' },
  { to: '#subscribe', icon: CreditCard,   label: '订阅',     disabled: true },
  { to: '#invite',    icon: Users,        label: '邀请激励', disabled: true },
  { to: '#privacy',   icon: Shield,       label: '隐私保护', disabled: true },
  { to: '/settings',  icon: SettingsIcon, label: '设置' },
  { to: '#help',      icon: HelpCircle,   label: '帮助',     disabled: true },
]

export default function Sidebar() {
  const [status, setStatus] = useState<CollectorStatus | null>(null)
  const [todayStats, setTodayStats] = useState<TodayStats | null>(null)
  const { sidebarTranslucent } = useTheme()

  useEffect(() => {
    let isVisible = !document.hidden
    const refresh = () => {
      // 窗口隐藏时暂停轮询，节省后端资源
      if (!isVisible) return
      getStatus().then(setStatus).catch(() => setStatus(null))
      getTodayStats().then(setTodayStats).catch(() => setTodayStats(null))
    }
    refresh()
    // 30秒轮询（从10秒降低，减少后端压力；状态变更不频繁，30秒足够）
    const interval = setInterval(refresh, 30000)
    // 窗口恢复可见时立即刷新
    const handleVisibility = () => {
      const wasHidden = !isVisible
      isVisible = !document.hidden
      if (wasHidden && isVisible) refresh()
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [])

  const handleToggleCollector = async () => {
    try {
      if (status?.running && !status?.paused) {
        await pauseCollector()
      } else {
        await resumeCollector()
      }
      // 刷新状态
      const newStatus = await getStatus()
      setStatus(newStatus)
    } catch (err) {
      console.error('Toggle collector failed:', err)
    }
  }

  return (
    <nav
      className="w-56 border-r border-cd-border flex flex-col shrink-0 select-none"
      style={{
        background: sidebarTranslucent ? 'var(--cd-sidebar-bg, var(--cd-sidebar))' : 'var(--cd-sidebar)',
        backdropFilter: sidebarTranslucent ? 'var(--cd-sidebar-blur)' : 'none',
        WebkitBackdropFilter: sidebarTranslucent ? 'var(--cd-sidebar-blur)' : 'none',
      }}
    >
      {/* ─── 顶部状态 ───────────────── */}
      <div className="px-5 pt-5 pb-4">
        {/* 记录状态 */}
        <button
          onClick={handleToggleCollector}
          className={`flex items-center gap-2 w-full px-2.5 py-1.5 rounded-lg transition-colors ${
            status !== null && !status?.running
              ? 'bg-cd-red/8 hover:bg-cd-red/15 border border-cd-red/15'
              : 'hover:bg-cd-hover'
          }`}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              status === null ? 'bg-cd-text-tertiary animate-pulse' : (status?.running && !status?.paused) ? 'bg-cd-green animate-pulse-soft' : 'bg-cd-red'
            }`}
          />
          <span className={`text-xs ${status !== null && !(status?.running && !status?.paused) ? 'text-cd-red font-medium' : 'text-cd-text-secondary'}`}>
            {status === null ? '连接中...' : (status?.running && !status?.paused) ? '正在记录' : '已暂停 — 点击开始'}
          </span>
          {status === null ? (
            <Loader2 size={12} className="text-cd-text-tertiary ml-auto animate-spin" />
          ) : (status?.running && !status?.paused) ? (
            <Pause size={12} className="text-cd-text-tertiary ml-auto" />
          ) : (
            <Play size={12} className="text-cd-red ml-auto" />
          )}
        </button>

        {/* 今日工作时长 */}
        <WorkTimeDisplay stats={todayStats} />
      </div>

      {/* ─── 核心导航 ─────────────────────── */}
      <div className="flex-1 overflow-y-auto px-2">
        {NAV_GROUPS.map((group, gi) => (
          <div key={group.label} className={gi === 0 ? '' : 'mt-4 mb-2'}>
            <div className="px-3 text-[10px] font-medium text-cd-text-tertiary uppercase tracking-wider mb-1">
              {group.label}
            </div>
            <div className="space-y-0.5">
              {group.items.map(({ to, icon: Icon, label }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                      isActive
                        ? 'bg-cd-green-light text-cd-green font-medium'
                        : 'text-cd-text-secondary hover:bg-cd-hover hover:text-cd-text'
                    }`
                  }
                >
                  <Icon size={16} />
                  {label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}

        {/* ─── 更多 ──────────────────────── */}
        <div className="mt-4 mb-2">
          <div className="px-3 text-[10px] font-medium text-cd-text-tertiary uppercase tracking-wider mb-1">
            更多
          </div>
          <div className="space-y-0.5">
            {MORE_NAV.map(({ to, icon: Icon, label, disabled }) => (
              <NavLink
                key={to + label}
                to={to}
                onClick={(e) => disabled && e.preventDefault()}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-colors ${
                    disabled
                      ? 'text-cd-text-tertiary cursor-default'
                      : isActive
                        ? 'bg-cd-green-light text-cd-green font-medium'
                        : 'text-cd-text-secondary hover:bg-cd-hover hover:text-cd-text'
                  }`
                }
              >
                <Icon size={16} />
                {label}
                {disabled && (
                  <span className="ml-auto text-[10px] text-cd-text-tertiary bg-cd-bg-secondary px-1.5 py-0.5 rounded">
                    即将推出
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        </div>
      </div>

      {/* ─── 底部用户信息 ─────────────────────── */}
      <div className="px-4 py-3 border-t border-cd-border">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full flex items-center justify-center bg-cd-green/20 shrink-0">
            <svg viewBox="0 0 24 24" className="w-4 h-4 text-cd-green" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
            </svg>
          </div>
          <div>
            <div className="text-xs text-cd-text font-medium leading-tight">橙紫Challenge</div>
            <div className="text-[10px] text-cd-gold leading-tight font-brand">Extreme Preview</div>
          </div>
        </div>
      </div>
    </nav>
  )
}

// 全局宠物可见状态

function WorkTimeDisplay({ stats }: { stats: TodayStats | null }) {
  if (!stats) return null

  const totalMin = stats.total_duration_min
  const hours = Math.floor(totalMin / 60)
  const mins = Math.round(totalMin % 60)
  // 假设 8 小时为满工作日
  const targetMin = 8 * 60
  const pct = Math.min(100, Math.round((totalMin / targetMin) * 100))
  // SVG 进度环参数
  const radius = 18
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (pct / 100) * circumference

  return (
    <div className="flex items-center gap-3 mt-2 px-2.5 py-2 rounded-lg bg-cd-bg-secondary">
      <svg width="44" height="44" viewBox="0 0 44 44" className="shrink-0">
        {/* 背景圆 */}
        <circle
          cx="22" cy="22" r={radius}
          fill="none" stroke="var(--cd-border)" strokeWidth="3"
        />
        {/* 进度圆 */}
        <circle
          cx="22" cy="22" r={radius}
          fill="none" stroke="var(--cd-green)" strokeWidth="3"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 22 22)"
          className="transition-all duration-700"
        />
        {/* 百分比文字 */}
        <text
          x="22" y="22"
          textAnchor="middle" dominantBaseline="central"
          className="text-[9px] font-bold fill-cd-green"
        >
          {pct}%
        </text>
      </svg>
      <div className="min-w-0">
        <div className="text-xs font-semibold text-cd-text">
          {hours > 0 ? `${hours}h ${mins}m` : `${mins}m`}
        </div>
        <div className="text-[10px] text-cd-text-tertiary">
          今日工作时长
        </div>
      </div>
    </div>
  )
}
