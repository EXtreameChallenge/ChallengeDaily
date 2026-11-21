import { useState, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ResponsiveContainer, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import dayjs from 'dayjs'
import {
  getTodayStats,
  getStatus,
  getActivities,
  getTodayTodos,
  updateTodo,
  startPomodoro,
  getPomodoroSessions,
  getMorningInsights,
  pauseCollector,
  resumeCollector,
  getTrendStats,
  getRhythmStats,
  getAppIconUrl,
  getRecentHeatmap,
  CATEGORY_COLORS,
  type TodayStats,
  type CollectorStatus,
  type Activity,
  type Todo,
  type MorningInsight,
  type RecentHeatmapDay,
} from '../../api/client'
import TodayTimeline from './TodayTimeline'
import { getTodaySummary, type TodaySummary } from '../../api/todaySummary'
import { useRelayEngine } from '../../components/relay/RelayEngine'
import HeroInfo from '../../components/HeroInfo'
import EmotionalCare from '../../components/EmotionalCare'
import SmartCoachPanel from '../../components/SmartCoachPanel'
import BenchmarkPanel from '../../components/BenchmarkPanel'
import MorningRitual from '../../components/MorningRitual'
import EveningRitual from '../../components/EveningRitual'
import DistractionHeatmap from '../../components/DistractionHeatmap'
import InfoTooltip from '../../components/InfoTooltip'
import { useGrowthStore } from '../../stores/growthStore'
import {
  Play, Pause, Sun, Moon, Sunrise, Sunset, Coffee,
  TrendingUp, Clock, Zap, CheckCircle2, Sparkles, RefreshCw,
  ChevronRight, Calendar, Target, Flame, ArrowRight,
  Trophy, Focus, CalendarDays, Activity as ActivityIcon,
} from 'lucide-react'

/** 卡片标题栏：标题在左，"更多" 在右 */
function CardHeader({ title, subtitle, linkTo, onNavigate }: {
  title: string
  subtitle?: string
  linkTo: string
  onNavigate: (path: string) => void
}) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-sm font-semibold text-cd-text">
        {title}
        {subtitle && <span className="text-cd-text-tertiary font-normal ml-1.5">{subtitle}</span>}
      </h3>
      <button
        onClick={() => onNavigate(linkTo)}
        className="flex items-center gap-1 text-xs text-cd-text-tertiary hover:text-cd-green transition-colors group"
      >
        更多
        <ArrowRight size={12} className="opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
      </button>
    </div>
  )
}

function getDisplayAppName(appName: string): string {
  const lower = appName.toLowerCase()
  const map: Record<string, string> = {
    'trae.exe': 'TRAE SOLO CN',
    'trae solo cn.exe': 'TRAE SOLO CN',
    'trae-solo-cn.exe': 'TRAE SOLO CN',
  }
  if (map[lower]) return map[lower]
  return appName.replace(/\.exe$/i, '')
}

const formatDur = (m: number) => m >= 60 ? `${(m / 60).toFixed(1)}h` : `${Math.round(m)}min`

const rhythmIcons: Record<string, string> = {
  '凌晨 (0-6)': '🌑', '早晨 (6-8)': '🌅', '上午 (8-11)': '🌞',
  '中午 (11-14)': '🍜', '下午 (14-19)': '☀️', '晚间 (19-22)': '🌆', '夜间 (22-24)': '🌙',
}
const rhythmShort: Record<string, string> = {
  '凌晨 (0-6)': '凌晨', '早晨 (6-8)': '早晨', '上午 (8-11)': '上午',
  '中午 (11-14)': '中午', '下午 (14-19)': '下午', '晚间 (19-22)': '晚间', '夜间 (22-24)': '夜间',
}

export default function TodayPage() {
  const navigate = useNavigate()
  const { triggerEvent } = useRelayEngine()

  // 核心数据
  const [stats, setStats] = useState<TodayStats | null>(null)
  const [status, setStatus] = useState<CollectorStatus | null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [morningInsights, setMorningInsights] = useState<MorningInsight[]>([])
  const [pomodoroSessions, setPomodoroSessions] = useState<any[]>([])

  // 丰富可视化数据
  const [heatmapData, setHeatmapData] = useState<RecentHeatmapDay[]>([])
  const [trendData, setTrendData] = useState<Array<{ date: string; count: number; category_count: number; duration_min: number }>>([])
  const [rhythmData, setRhythmData] = useState<Array<{ period: string; count: number; percentage: number; duration_min: number }>>([])
  const [peakPeriod, setPeakPeriod] = useState('')
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})

  // UI 状态
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [activePomodoro, setActivePomodoro] = useState<{ taskTitle: string; startMin: number } | null>(null)

  // P0-4: 今日一句话 AI 摘要
  const [todaySummary, setTodaySummary] = useState<TodaySummary | null>(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [summaryRefreshing, setSummaryRefreshing] = useState(false)

  const timeOfDay = getTimeOfDay()
  const greeting = getGreeting(timeOfDay)

  // 加载所有数据
  useEffect(() => {
    let isFirst = true
    const refresh = async () => {
      if (!isFirst) setRefreshing(true)
      useGrowthStore.getState().fetchGrowth()
      try {
        const [s, st, actsPage, td, ps] = await Promise.all([
          getTodayStats(),
          getStatus(),
          getActivities(undefined, 1, 8),
          getTodayTodos(),
          getPomodoroSessions(),
        ])
        setStats(s)
        setStatus(st)
        setActivities(actsPage.activities)
        setTodos(td.todos || [])
        setPomodoroSessions(ps.sessions || [])

        // 并行加载非关键数据
        Promise.allSettled([
          getRecentHeatmap(3).then(r => setHeatmapData(r.data)).catch(() => {}),
          getTrendStats(7).then(r => setTrendData(r.trend)).catch(() => {}),
          getRhythmStats().then(r => { setRhythmData(r.periods); setPeakPeriod(r.peak_period) }).catch(() => {}),
        ])
      } catch (err) {
        console.error('Failed to load today data:', err)
      } finally {
        setLoading(false)
        setRefreshing(false)
        isFirst = false
      }
    }
    refresh()
    const interval = setInterval(() => { if (!document.hidden) refresh() }, 60000)
    const onVisible = () => { if (!document.hidden) refresh() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVisible) }
  }, [])

  // 晨报
  useEffect(() => {
    if (timeOfDay === 'morning' || timeOfDay === 'forenoon') {
      getMorningInsights().then(res => setMorningInsights(res.insights || [])).catch(() => {})
      triggerEvent('morning_brief', { timeOfDay })
    }
    if (timeOfDay === 'afternoon') {
      const hour = dayjs().hour()
      if (hour >= 14 && hour < 16) triggerEvent('low_energy', { hour })
    }
  }, [timeOfDay, triggerEvent])

  // P0-4: 加载今日一句话摘要（自动加载 + 手动刷新）
  const loadTodaySummary = useCallback(async (silent = false) => {
    if (!silent) setSummaryRefreshing(true)
    try {
      const res = await getTodaySummary()
      setTodaySummary(res)
    } catch (err) {
      console.error('Failed to load today summary:', err)
    } finally {
      setSummaryLoading(false)
      setSummaryRefreshing(false)
    }
  }, [])
  useEffect(() => { loadTodaySummary() }, [loadTodaySummary])

  // 应用图标
  const topAppsKey = useMemo(() => stats?.top_apps?.map(a => a.app_name).join('|'), [stats?.top_apps])
  useEffect(() => {
    if (!stats?.top_apps?.length) return
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      await Promise.all(stats.top_apps!.map(async (app) => {
        try {
          const iconKey = app.app_name_raw || app.app_name
          map[app.app_name] = await getAppIconUrl(iconKey)
        } catch { map[app.app_name] = '' }
      }))
      if (!cancelled) setIconUrls(map)
    })()
    return () => { cancelled = true }
  }, [topAppsKey])

  // 计算值
  const totalMin = stats?.total_duration_min || 0
  const hours = Math.floor(totalMin / 60)
  const mins = Math.round(totalMin % 60)
  const timeStr = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
  const captureCount = status?.total_captures || 0
  const focusSessions = stats?.focus_sessions || 0
  const longestFocus = stats?.longest_focus_min || 0
  const isRecording = status?.running && !status?.paused
  const isPaused = status !== null && !status.running
  const intervalSec = status?.interval_sec || 60
  const topApps = stats?.top_apps || []
  const maxTopAppMin = Math.max(...topApps.map(a => a.duration_min), 1)

  const categoryBars = stats?.categories
    ? Object.entries(stats.categories).map(([name, value]) => ({ name, value: Math.round(value) })).filter(d => d.value > 0).sort((a, b) => b.value - a.value)
    : []
  const totalCategoryMin = categoryBars.reduce((s, d) => s + d.value, 0)
  const topCategory = categoryBars[0]?.name || '-'

  const heatmapBins = heatmapData.map(day => {
    const cells: number[] = []
    for (let b = 0; b < 12; b++) cells.push((day.hours[2 * b] || 0) + (day.hours[2 * b + 1] || 0))
    return { ...day, cells }
  })
  const maxHeatVal = Math.max(...heatmapBins.flatMap(d => d.cells), 1)
  const validTrend = trendData.filter(d => d.duration_min > 0)
  const recentActivities = activities.slice(0, 8)
  const isEmptyState = !stats?.total_duration_min && activities.length === 0

  // 今日评分
  const todayScore = useMemo(() => {
    if (!stats) return 0
    const timeScore = Math.min(totalMin / 480, 1) * 40
    const pomoScore = Math.min((pomodoroSessions.length || focusSessions) / 8, 1) * 20
    const completed = todos.filter(t => t.status === 'completed').length
    const todoScore = todos.length > 0 ? (completed / todos.length) * 25 : 12
    return Math.round(timeScore + pomoScore + todoScore + 15)
  }, [stats, totalMin, pomodoroSessions, focusSessions, todos])

  // 操作
  const handleResume = async () => { try { await resumeCollector(); const s = await getStatus(); setStatus(s) } catch (e) { console.error(e) } }
  const handlePause = async () => { try { await pauseCollector(); const s = await getStatus(); setStatus(s) } catch (e) { console.error(e) } }

  const handleCompleteTodo = useCallback(async (todo: Todo) => {
    try {
      await updateTodo(todo.id, { status: 'completed' })
      setTodos(prev => prev.map(t => t.id === todo.id ? { ...t, status: 'completed' } : t))
      const nextTodo = todos.find(t => t.id !== todo.id && t.status !== 'completed')
      triggerEvent('todo_completed', { todoId: todo.id, todoTitle: todo.title, nextTodoId: nextTodo?.id, nextTodoTitle: nextTodo?.title, nextTodo: !!nextTodo })
    } catch (err) { console.error('Failed to complete todo:', err) }
  }, [todos, triggerEvent])

  const handleStartPomodoro = useCallback(async (todo?: Todo) => {
    try {
      await startPomodoro({ task_title: todo?.title || '专注工作', duration_min: 25 })
      setActivePomodoro({ taskTitle: todo?.title || '专注工作', startMin: dayjs().hour() * 60 + dayjs().minute() })
    } catch (err) { console.error('Failed to start pomodoro:', err) }
  }, [])

  const handleEndPomodoro = useCallback(() => {
    setActivePomodoro(null)
    triggerEvent('pomodoro_completed', { durationMin: 25, taskTitle: activePomodoro?.taskTitle })
  }, [activePomodoro, triggerEvent])

  if (loading) {
    return <div className="animate-pulse text-cd-text-tertiary text-base p-6">加载中...</div>
  }

  if (isEmptyState) {
    return (
      <div className="animate-fade-in flex items-center justify-center h-full">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 rounded-2xl bg-cd-green/10 flex items-center justify-center mx-auto mb-5">
            <ActivityIcon size={40} className="text-cd-green" />
          </div>
          <h2 className="text-xl font-semibold text-cd-text mb-3 font-display">欢迎使用 <span className="font-brand font-bold">ChallengeDaily</span></h2>
          {isPaused ? (
            <>
              <p className="text-base text-cd-text-secondary mb-6">采集器已暂停，点击开始自动记录。</p>
              <button onClick={handleResume} className="btn-primary">
                <Play size={18} /> 开始记录
              </button>
            </>
          ) : (
            <p className="text-base text-cd-text-secondary">正在自动记录你的活动，稍等片刻即可看到数据。</p>
          )}
        </div>
      </div>
    )
  }

return (
    <div className="animate-fade-in pb-4 relative">
      <div className="bg-glow-top" />
      {(timeOfDay === 'morning' || timeOfDay === 'forenoon') && (
        <div className="mb-3"><MorningRitual /></div>
      )}

      {/* 紧凑状态栏 */}
      <div className="flex items-center justify-between mb-3 px-1 flex-wrap gap-2">
        <div className="flex items-center gap-4 flex-wrap">
          <HeroInfo todayDurationMin={totalMin} />
          <div className="h-4 w-px bg-cd-border" />
          <button onClick={isRecording ? handlePause : handleResume}
            className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full transition ${isRecording ? 'bg-cd-green/10 text-cd-green' : 'bg-cd-red/10 text-cd-red'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isRecording ? 'bg-cd-green animate-pulse' : 'bg-cd-red'}`} />
            {isRecording ? '记录中' : '已暂停'}
          </button>
          <div className="flex items-center gap-4">
            <div className="text-center">
              <p className="font-brand font-bold text-cd-text text-sm leading-tight">{timeStr}</p>
              <p className="text-[10px] text-cd-text-tertiary">工作时长</p>
            </div>
            <div className="text-center">
              <p className="font-brand font-bold text-cd-text text-sm leading-tight">{focusSessions}<span className="text-[10px] text-cd-text-tertiary ml-0.5">次</span></p>
              <p className="text-[10px] text-cd-text-tertiary">深度工作</p>
            </div>
            <div className="text-center">
              <p className="font-brand font-bold text-sm leading-tight" style={{ color: todayScore >= 70 ? 'var(--cd-green)' : todayScore >= 40 ? 'var(--cd-yellow)' : 'var(--cd-red)' }}>{todayScore}</p>
              <p className="text-[10px] text-cd-text-tertiary">今日评分</p>
            </div>
            <div className="text-center">
              <p className="font-brand font-bold text-cd-text text-sm leading-tight">{todos.filter(t => t.status === 'completed').length}/{todos.length}</p>
              <p className="text-[10px] text-cd-text-tertiary">待办完成</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => handleStartPomodoro()} className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full bg-cd-accent text-white hover:opacity-90 transition">
            <Flame size={12} /> 专注
          </button>
          <button onClick={() => navigate('/todos')} className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full border border-cd-border text-cd-text-secondary hover:text-cd-text hover:border-cd-accent/50 transition">
            <Target size={12} /> 待办
          </button>
        </div>
      </div>

      {/* P0-4: 今日一句话 AI 摘要卡片 */}
      <div className="mb-3 card-gradient-border rounded-2xl p-4 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-cd-purple/10 flex items-center justify-center shrink-0">
          <Sparkles size={15} className="text-cd-purple" />
        </div>
        <div className="flex-1 min-w-0">
          {summaryLoading ? (
            <div className="animate-pulse space-y-1.5">
              <div className="h-3.5 bg-cd-bg-secondary rounded-lg w-3/4" />
              <div className="h-2.5 bg-cd-bg-secondary rounded-lg w-1/2" />
            </div>
          ) : (
            <p className="text-sm text-cd-text leading-relaxed">
              {todaySummary?.summary || '暂无今日摘要'}
            </p>
          )}
        </div>
        <button
          onClick={() => loadTodaySummary()}
          disabled={summaryRefreshing}
          title="刷新摘要"
          className="shrink-0 p-1.5 rounded-2xl text-cd-text-tertiary hover:text-cd-green hover:bg-cd-bg-secondary transition disabled:opacity-50"
        >
          <RefreshCw size={13} className={summaryRefreshing ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="mb-3"><EmotionalCare /></div>
      <div className="mb-3"><SmartCoachPanel /></div>

      {/* ── 第一行：时间线(左2) + 快捷面板(右1) ── */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        {/* 今日时间线 */}
        <div className="col-span-2">
          <CardHeader title="今日时间线" linkTo="/timeline" onNavigate={navigate} />
          <div><TodayTimeline activities={activities} todos={todos} onStartPomodoro={handleStartPomodoro} onCompleteTodo={handleCompleteTodo} /></div>
        </div>

        {/* 右侧快捷面板堆叠 */}
        <div className="space-y-2">
          {/* 番茄钟 */}
          {activePomodoro ? (
            <div className="bg-cd-card border border-cd-green/30 rounded-2xl p-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-cd-green/10 flex items-center justify-center">
                    <Flame size={14} className="text-cd-green animate-pulse" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-cd-text truncate">{activePomodoro.taskTitle}</p>
                    <p className="text-[10px] text-cd-text-tertiary">专注中 · 25分钟</p>
                  </div>
                </div>
                <button onClick={handleEndPomodoro} className="px-2.5 py-1 rounded-full text-[11px] bg-cd-red/10 text-cd-red hover:bg-cd-red/20 transition shrink-0">结束</button>
              </div>
            </div>
          ) : (
            <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-cd-purple/10 flex items-center justify-center">
                    <Zap size={14} className="text-cd-purple" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-cd-text">快速专注</p>
                    <p className="text-[10px] text-cd-text-tertiary">今日 {pomodoroSessions.length || focusSessions} 个番茄</p>
                  </div>
                </div>
                <button onClick={() => handleStartPomodoro()} className="px-2.5 py-1 rounded-full text-[11px] bg-cd-accent text-white hover:opacity-90 transition flex items-center gap-1 shrink-0">
                  <Play size={10} /> 开始
                </button>
              </div>
            </div>
          )}

          {/* 待办 */}
          {todos.length > 0 && (
            <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <Target size={11} className="text-cd-green" />
                  <span className="text-xs font-semibold text-cd-text">今日待办</span>
                  <span className="text-[10px] text-cd-text-tertiary">{todos.filter(t => t.status === 'completed').length}/{todos.length}</span>
                </div>
                <button onClick={() => navigate('/todos')} className="text-[10px] text-cd-text-tertiary hover:text-cd-green transition">全部 →</button>
              </div>
              <div className="space-y-1.5">
                {todos.slice(0, 5).map(todo => (
                  <div key={todo.id} className="flex items-center gap-2 group">
                    <button onClick={() => handleCompleteTodo(todo)} className={`w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center shrink-0 transition ${todo.status === 'completed' ? 'bg-cd-green border-cd-green' : 'border-cd-border hover:border-cd-green'}`}>
                      {todo.status === 'completed' && <CheckCircle2 size={9} className="text-white" />}
                    </button>
                    <span className={`flex-1 text-xs truncate ${todo.status === 'completed' ? 'text-cd-text-tertiary line-through' : 'text-cd-text'}`}>{todo.title}</span>
                    {todo.status !== 'completed' && (
                      <button onClick={() => handleStartPomodoro(todo)} className="opacity-0 group-hover:opacity-100 text-[10px] text-cd-green hover:underline transition shrink-0">专注</button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 时间分布 */}
          <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-cd-text">时间都去哪了</span>
              <button onClick={() => navigate('/timeline')} className="text-[10px] text-cd-text-tertiary hover:text-cd-green transition">更多 →</button>
            </div>
            {categoryBars.length > 0 ? (
              <div className="space-y-2">
                {categoryBars.slice(0, 8).map(entry => {
                  const pct = totalCategoryMin > 0 ? Math.round(entry.value / totalCategoryMin * 100) : 0
                  const color = CATEGORY_COLORS[entry.name] || 'var(--cd-text-tertiary)'
                  return (
                    <div key={entry.name}>
                      <div className="flex items-center justify-between mb-0.5">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
                          <span className="text-[11px] text-cd-text truncate">{entry.name}</span>
                        </div>
                        <span className="text-[10px] text-cd-text-tertiary shrink-0 ml-2">
                          <span className="font-brand font-semibold text-cd-text text-[11px]">{formatDur(entry.value)}</span>
                          <span className="ml-1">{pct}%</span>
                        </span>
                      </div>
                      <div className="h-1 rounded-full bg-cd-bg-secondary overflow-hidden">
                        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%`, background: color }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : <p className="text-[11px] text-cd-text-tertiary text-center py-2">暂无数据</p>}
          </div>
        </div>
      </div>

      {/* ── 第二行：应用使用 + 效率趋势 + 个人节奏 ── */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        {/* 应用使用 */}
        <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-cd-text">应用使用 <span className="text-cd-text-tertiary font-normal text-[10px]">今日 · 窗口累计</span></span>
              <InfoTooltip text="今日各应用窗口累计时长。多个窗口同时打开时会重叠，因此合计可能高于顶部工作时长。" size={11} />
            </div>
            <button onClick={() => navigate('/apps')} className="text-[10px] text-cd-text-tertiary hover:text-cd-green transition">更多 →</button>
          </div>
          {topApps.length > 0 ? (
            <div className="space-y-1.5">
              {topApps.slice(0, 5).map(app => {
                const pct = Math.min((app.duration_min / maxTopAppMin) * 100, 100)
                const iconUrl = iconUrls[app.app_name]
                const defaultIcon = import.meta.env.DEV ? '/icon.png' : './icon.png'
                return (
                  <div key={app.app_name} className="flex items-center gap-2">
                    <div className="w-5 h-5 rounded-2xl bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center shrink-0 overflow-hidden">
                      <img src={iconUrl || defaultIcon} alt="" className="w-3.5 h-3.5 object-contain" onError={(e) => { e.currentTarget.src = defaultIcon }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[11px] text-cd-text truncate">{getDisplayAppName(app.app_name)}</span>
                        <span className="text-[11px] font-brand font-semibold text-cd-text shrink-0 ml-2">{formatDur(app.duration_min)}</span>
                      </div>
                      <div className="h-0.5 rounded-full bg-cd-bg-secondary overflow-hidden">
                        <div className="h-full rounded-full bg-cd-green/60 transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%` }} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : <p className="text-[11px] text-cd-text-tertiary text-center py-2">暂无记录</p>}
        </div>

        {/* 效率趋势 */}
        <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-cd-text">效率趋势 <span className="text-cd-text-tertiary font-normal text-[10px]">7d</span></span>
            <button onClick={() => navigate('/timeline')} className="text-[10px] text-cd-text-tertiary hover:text-cd-green transition">更多 →</button>
          </div>
          <div className="h-28">
            {validTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 2, right: 5, left: -15, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--cd-border)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(v: string) => dayjs(v).format('M/D')}
                    tick={{ fontSize: 9, fill: 'var(--cd-text-tertiary)' }} axisLine={{ stroke: 'var(--cd-border)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 9, fill: 'var(--cd-text-tertiary)' }} axisLine={false} tickLine={false}
                    tickFormatter={(v: number) => v <= 0 ? '0h' : v >= 60 ? `${Math.round(v / 60)}h` : `${Math.round(v)}m`} width={32} />
                  <Tooltip formatter={(value: number) => [value >= 60 ? `${(value / 60).toFixed(1)}h` : `${Math.round(value)}min`, '时长']}
                    labelFormatter={(label: string) => dayjs(label).format('YYYY-MM-DD')}
                    contentStyle={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderRadius: 8, fontSize: 11 }} />
                  <Line type="monotone" dataKey="duration_min" stroke="var(--cd-green)" strokeWidth={2}
                    dot={{ r: 2, fill: 'var(--cd-green)' }} activeDot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : <div className="h-full flex items-center justify-center"><p className="text-[11px] text-cd-text-tertiary">数据积累中</p></div>}
          </div>
        </div>

        {/* 个人节奏 */}
        <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-cd-text">个人节奏</span>
            <button onClick={() => navigate('/heatmap')} className="text-[10px] text-cd-text-tertiary hover:text-cd-green transition">更多 →</button>
          </div>
          {rhythmData.length > 0 ? (
            <div className="space-y-1.5">
              {rhythmData.filter(r => r.duration_min > 0).map(item => {
                const maxHours: Record<string, number> = { '凌晨 (0-6)': 6, '早晨 (6-8)': 2, '上午 (8-11)': 3, '中午 (11-14)': 3, '下午 (14-19)': 5, '晚间 (19-22)': 3, '夜间 (22-24)': 2 }
                const maxMin = (maxHours[item.period] || 2) * 60
                const ratio = Math.min(item.duration_min / maxMin, 1)
                return (
                  <div key={item.period}>
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-[11px] text-cd-text flex items-center gap-1">{rhythmIcons[item.period] || '⏰'} {rhythmShort[item.period] || item.period}</span>
                      <span className="text-[11px] font-brand font-semibold text-cd-text">{item.duration_min >= 60 ? `${(item.duration_min / 60).toFixed(1)}h` : `${Math.round(item.duration_min)}m`}</span>
                    </div>
                    <div className="h-1 rounded-full bg-cd-bg-secondary overflow-hidden">
                      <div className="h-full rounded-full bg-cd-purple transition-all duration-500" style={{ width: `${Math.max(ratio * 100, 2)}%`, opacity: 0.4 + ratio * 0.6 }} />
                    </div>
                  </div>
                )
              })}
              {rhythmData.filter(r => r.duration_min === 0).length > 0 && (
                <p className="text-[9px] text-cd-text-tertiary text-center pt-1 border-t border-cd-border/50">其余 {rhythmData.filter(r => r.duration_min === 0).length} 个时段暂无数据</p>
              )}
            </div>
          ) : <p className="text-[11px] text-cd-text-tertiary text-center py-2">暂无数据</p>}
        </div>
      </div>

      {/* ── 第三行：热力图(左2) + 行业基准(右1)；窄窗改为上下堆叠，避免抢宽度 ── */}
      <div className="grid grid-cols-1 gap-3 mb-3 lg:grid-cols-3">
        {/* 近三天热力图 */}
        <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5 lg:col-span-2">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-cd-text">近三天热力图</span>
            <button onClick={() => navigate('/heatmap')} className="text-[10px] text-cd-text-tertiary hover:text-cd-green transition">更多 →</button>
          </div>
          <div className="grid grid-cols-12 gap-1 pl-10 mb-0.5">
            {Array.from({ length: 12 }, (_, b) => (
              <div key={b} className="text-center text-[9px] text-cd-text-tertiary font-brand">{b * 2}</div>
            ))}
          </div>
          {[...heatmapBins].reverse().map((day, di) => {
            const dayLabel = di === 0 ? 'Today' : di === 1 ? 'Yesterday' : dayjs(day.date).format('MM/DD')
            return (
              <div key={day.date} className="mb-0.5">
                <div className="flex items-center gap-1">
                  <span className="text-[9px] text-cd-text-tertiary w-10 text-right shrink-0 mr-1 font-brand">{dayLabel}</span>
                  <div className="flex-1 grid grid-cols-12 gap-1">
                    {day.cells.map((val, b) => {
                      const intensity = maxHeatVal > 0 ? val / maxHeatVal : 0
                      const cellMin = Math.round(val * intervalSec / 60)
                      return (
                        <div key={b} className="h-7 rounded-lg transition-all hover:scale-110 cursor-default"
                          style={{ background: val === 0 ? 'var(--cd-bg-tertiary)' : `rgba(99,91,255,${0.1 + intensity * 0.7})` }}
                          title={`${dayjs(day.date).format('MM/DD')} ${b * 2}:00-${b * 2 + 2}:00 · ${cellMin}分钟 · ${val}次活动`} />
                      )
                    })}
                  </div>
                </div>
              </div>
            )
          })}
          <div className="flex items-center justify-between mt-1.5 pl-10">
            <div className="flex items-center gap-1">
              <span className="text-[9px] text-cd-text-tertiary">Less</span>
              {[0, 0.25, 0.5, 0.75, 1].map((v, i) => (
                <div key={i} className="w-3 h-2 rounded-lg" style={{ background: v === 0 ? 'var(--cd-bg-tertiary)' : `rgba(99,91,255,${0.1 + v * 0.7})` }} />
              ))}
              <span className="text-[9px] text-cd-text-tertiary">More</span>
            </div>
            {(() => {
              const today = heatmapBins[heatmapBins.length - 1]
              if (!today) return null
              const activeSlots = today.cells.filter(v => v > 0).length
              const totalMin = today.cells.reduce((s, v) => s + Math.round(v * intervalSec / 60), 0)
              const maxIdx = today.cells.indexOf(Math.max(...today.cells))
              const peakHour = maxIdx >= 0 ? `${maxIdx * 2}:00-${maxIdx * 2 + 2}:00` : '--'
              return (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px]">
                  <span className="whitespace-nowrap tabular-nums text-cd-text-tertiary">峰值 <span className="text-cd-purple font-semibold">{peakHour}</span></span>
                  <span className="whitespace-nowrap tabular-nums text-cd-text-tertiary">活跃 <span className="text-cd-green font-semibold">{activeSlots}</span> 时段</span>
                  <span className="whitespace-nowrap tabular-nums text-cd-text-tertiary">共 <span className="text-cd-text font-semibold">{totalMin >= 60 ? `${(totalMin/60).toFixed(1)}h` : `${totalMin}m`}</span></span>
                </div>
              )
            })()}
          </div>
          {/* 每日统计行 */}
          <div className="mt-2 pl-10 space-y-1">
            {[...heatmapBins].reverse().map((day, di) => {
              const dayLabel = di === 0 ? '今天' : di === 1 ? '昨天' : dayjs(day.date).format('MM/DD')
              const totalMin = day.cells.reduce((s, v) => s + Math.round(v * intervalSec / 60), 0)
              const activeCount = day.cells.filter(v => v > 0).length
              const maxIdx = day.cells.indexOf(Math.max(...day.cells))
              const peakHour = maxIdx >= 0 && day.cells[maxIdx] > 0 ? `${maxIdx * 2}:00-${maxIdx * 2 + 2}:00` : '--'
              const intensity = maxHeatVal > 0 ? Math.max(...day.cells) / maxHeatVal : 0
              return (
                <div key={day.date} className="flex items-center gap-2 text-[10px] bg-cd-bg-secondary/40 rounded-lg px-2 py-1 overflow-hidden">
                  <span className="text-cd-text-tertiary w-8 shrink-0">{dayLabel}</span>
                  <div className="flex-1 flex items-center gap-1 min-w-0 whitespace-nowrap tabular-nums">
                    <span className="text-cd-text font-semibold">{totalMin >= 60 ? `${(totalMin/60).toFixed(1)}h` : `${totalMin}m`}</span>
                    <span className="text-cd-text-tertiary">· {activeCount}时段活跃</span>
                    <span className="text-cd-text-tertiary">· 峰值</span>
                    <span className="text-cd-purple font-semibold">{peakHour}</span>
                  </div>
                  <div className="w-12 h-1 rounded-full bg-cd-bg overflow-hidden shrink-0">
                    <div className="h-full rounded-full" style={{ width: `${Math.max(intensity * 100, 2)}%`, background: `rgba(99,91,255,${0.3 + intensity * 0.5})` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* 行业基准 */}
        <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5">
          <div className="flex items-center gap-1.5 mb-2">
            <Trophy size={11} className="text-cd-green" />
            <span className="text-xs font-semibold text-cd-text">行业基准</span>
          </div>
          <BenchmarkPanel />
        </div>
      </div>

      {/* 晨报洞察 */}
      {(timeOfDay === 'morning' || timeOfDay === 'forenoon') && morningInsights.length > 0 && (
        <div className="mb-3">
          <CardHeader title="AI 晨报洞察" linkTo="/report" onNavigate={navigate} />
          <div className="bg-cd-card border border-cd-border rounded-2xl p-2.5 space-y-2">
            {morningInsights.slice(0, 3).map((insight, i) => (
              <div key={i} className="flex items-start gap-2">
                <Sparkles size={12} className="text-cd-purple mt-0.5 shrink-0" />
                <p className="text-xs text-cd-text-secondary leading-relaxed">{insight.content || insight.insight || String(insight)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 分心热点图 */}
      <div className="mb-3"><DistractionHeatmap /></div>

      {/* 晚间回顾 */}
      {(timeOfDay === 'evening' || timeOfDay === 'night') && (
        <div className="mt-2"><EveningRitual /></div>
      )}
    </div>
  )
}


function getTimeOfDay(): 'morning' | 'forenoon' | 'noon' | 'afternoon' | 'evening' | 'night' {
  const h = dayjs().hour()
  if (h >= 6 && h < 9) return 'morning'
  if (h >= 9 && h < 12) return 'forenoon'
  if (h >= 12 && h < 14) return 'noon'
  if (h >= 14 && h < 18) return 'afternoon'
  if (h >= 18 && h < 22) return 'evening'
  return 'night'
}

function getGreeting(t: string): string {
  const map: Record<string, string> = {
    morning: '早上好', forenoon: '上午好', noon: '中午好',
    afternoon: '下午好', evening: '晚上好', night: '夜深了',
  }
  return map[t] || '你好'
}
