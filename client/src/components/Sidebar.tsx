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
  Cat,
  Loader2,
  Sun,
  Moon,
} from 'lucide-react'
import { useState, useEffect } from 'react'
import { getStatus, pauseCollector, resumeCollector, getTodayStats, type CollectorStatus, type TodayStats } from '../api/client'
import { useTheme } from './ThemeContext'

const CORE_NAV = [
  { to: '/',          icon: LayoutDashboard, label: '今日工作' },
  { to: '/report',    icon: FileText,        label: '生成报告' },
  { to: '/timeline',  icon: Clock,           label: '工作时间线' },
  { to: '/heatmap',   icon: Grid3X3,         label: '时段热力图' },
  { to: '/apps',      icon: AppWindow,       label: '应用记录' },
  { to: '/app-tags',  icon: Tags,            label: '应用标签' },
  { to: '/history',   icon: History,         label: '历史报告' },
  { to: '/agent',     icon: Bot,             label: '接入Agent' },
]

const MORE_NAV = [
  { to: '#subscribe', icon: CreditCard,  label: '订阅',     disabled: true },
  { to: '#invite',    icon: Users,       label: '邀请激励', disabled: true },
  { to: '#privacy',   icon: Shield,      label: '隐私保护', disabled: true },
  { to: '/settings',  icon: SettingsIcon, label: '设置' },
  { to: '#help',      icon: HelpCircle,  label: '帮助',     disabled: true },
]

export default function Sidebar() {
  const [status, setStatus] = useState<CollectorStatus | null>(null)
  const [todayStats, setTodayStats] = useState<TodayStats | null>(null)
  const { theme, toggleTheme } = useTheme()

  useEffect(() => {
    const refresh = () => {
      getStatus().then(setStatus).catch(() => setStatus(null))
      getTodayStats().then(setTodayStats).catch(() => setTodayStats(null))
    }
    refresh()
    const interval = setInterval(refresh, 10000)
    return () => clearInterval(interval)
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
    <nav className="w-56 bg-cd-sidebar border-r border-cd-border flex flex-col shrink-0 select-none">
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
        <div className="space-y-0.5">
          {CORE_NAV.map(({ to, icon: Icon, label }) => (
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

        {/* 宠物开关 */}
        <button
          onClick={() => {
            const show = !window._petVisible
            window._petVisible = show
            window.electronAPI?.togglePet(show)
          }}
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] text-cd-text-secondary hover:bg-cd-hover hover:text-cd-text transition-colors w-full"
        >
          <Cat size={16} />
          桌面宠物
        </button>

        {/* 深色模式切换 */}
        <button
          onClick={toggleTheme}
          className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] text-cd-text-secondary hover:bg-cd-hover hover:text-cd-text transition-colors w-full"
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          {theme === 'dark' ? '浅色模式' : '深色模式'}
        </button>
      </div>

      {/* ─── 底部用户信息 ─────────────────────── */}
      <div className="px-4 py-3 border-t border-cd-border">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-full bg-cd-green-light flex items-center justify-center text-cd-green text-[10px] font-bold">
            U
          </div>
          <div>
            <div className="text-xs text-cd-text font-medium leading-tight">用户</div>
            <div className="text-[10px] text-cd-text-tertiary leading-tight">免费版</div>
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
