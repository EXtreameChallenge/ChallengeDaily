import { useState, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
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
  CATEGORY_COLORS,
  type TodayStats,
  type CollectorStatus,
  type Activity,
  type Todo,
  type MorningInsight,
} from '../../api/client'
import TodayTimeline from './TodayTimeline'
import { useRelayEngine } from '../../components/relay/RelayEngine'
import {
  Play, Pause, Sun, Moon, Sunrise, Sunset, Coffee,
  TrendingUp, Clock, Zap, CheckCircle2, Sparkles,
  ChevronRight, Calendar, Target, Flame,
} from 'lucide-react'

/**
 * 今日主页 — ChallengeDaily 一条龙体验的核心页面
 *
 * 设计理念：
 * - 时间线即界面（Timeline as Interface）：所有功能围绕一天的时间线组织
 * - 下一步永远可见（Next Action Always Visible）：任何时刻都能看到建议的下一步
 * - 数据指向行动（Data Leads to Action）：每个数据点都有对应的行动入口
 *
 * 科学依据：
 * - 认知负荷理论：线性时间线符合人对时间的自然认知图式
 * - 执行意图：系统主动提供"如果现在是X，就做Y"的建议
 * - 决策疲劳：AI 排好优先级，减少"该干什么"的决策消耗
 * - 峰终定律：早晨晨报（峰）+ 晚间日报（终）是关键体验节点
 */

type TimeOfDay = 'morning' | 'forenoon' | 'noon' | 'afternoon' | 'evening' | 'night'

function getTimeOfDay(): TimeOfDay {
  const h = dayjs().hour()
  if (h < 6) return 'night'
  if (h < 9) return 'morning'
  if (h < 12) return 'forenoon'
  if (h < 14) return 'noon'
  if (h < 18) return 'afternoon'
  if (h < 22) return 'evening'
  return 'night'
}

function getGreeting(tod: TimeOfDay): { text: string; icon: typeof Sun } {
  switch (tod) {
    case 'morning': return { text: '早上好', icon: Sunrise }
    case 'forenoon': return { text: '上午好', icon: Sun }
    case 'noon': return { text: '中午好', icon: Coffee }
    case 'afternoon': return { text: '下午好', icon: Sun }
    case 'evening': return { text: '晚上好', icon: Sunset }
    case 'night': return { text: '夜深了', icon: Moon }
  }
}

export default function TodayPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<TodayStats | null>(null)
  const [status, setStatus] = useState<CollectorStatus | null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [todos, setTodos] = useState<Todo[]>([])
  const [morningInsights, setMorningInsights] = useState<MorningInsight[]>([])
  const [loading, setLoading] = useState(true)
  const [activePomodoro, setActivePomodoro] = useState<{
    taskId?: number
    taskTitle?: string
    startTime: string
    durationMin: number
  } | null>(null)

  const timeOfDay = getTimeOfDay()
  const greeting = getGreeting(timeOfDay)
  const { triggerEvent } = useRelayEngine()

  // 加载数据
  const loadData = useCallback(async () => {
    try {
      const [s, st, acts, tdRes] = await Promise.all([
        getTodayStats(),
        getStatus(),
        getActivities(undefined, 1, 50),
        getTodayTodos(),
      ])
      setStats(s)
      setStatus(st)
      setActivities(acts.activities || [])
      setTodos(tdRes.todos || [])
    } catch (err) {
      console.error('Failed to load today data:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
    // 每 60 秒刷新一次
    const interval = setInterval(() => {
      if (!document.hidden) loadData()
    }, 60000)
    const onVisible = () => { if (!document.hidden) loadData() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [loadData])

  // 加载晨报（早晨）
  useEffect(() => {
    if (timeOfDay === 'morning' || timeOfDay === 'forenoon') {
      getMorningInsights().then(res => setMorningInsights(res.insights || [])).catch(() => {})
      // 触发晨报接力链
      triggerEvent('morning_brief', { timeOfDay })
    }
    // 下午低谷期触发低能量建议
    if (timeOfDay === 'afternoon') {
      const hour = dayjs().hour()
      if (hour >= 14 && hour < 16) {
        triggerEvent('low_energy', { hour })
      }
    }
  }, [timeOfDay, triggerEvent])

  // 检查是否有进行中的番茄钟
  useEffect(() => {
    getPomodoroSessions().then((res) => {
      const latest = res.sessions?.[0]
      if (latest && latest.status === 'running') {
        setActivePomodoro({
          taskId: latest.todo_id ?? undefined,
          taskTitle: latest.task,
          startTime: latest.start_time,
          durationMin: latest.duration_min || 25,
        })
      }
    }).catch(() => {})
  }, [])

  // 结束番茄钟
  const handleEndPomodoro = useCallback(() => {
    setActivePomodoro(null)
    // 触发接力链：番茄钟完成 → 休息或继续
    triggerEvent('pomodoro_completed', {
      durationMin: 25,
      taskTitle: activePomodoro?.taskTitle,
    })
  }, [activePomodoro, triggerEvent])
  const handleStartPomodoro = useCallback(async (todo?: Todo) => {
    try {
      const res = await startPomodoro({
        duration_min: 25,
        todo_id: todo?.id ?? null,
        task: todo?.title,
      })
      if (res) {
        setActivePomodoro({
          taskId: todo?.id,
          taskTitle: todo?.title,
          startTime: res.start_time || dayjs().format('YYYY-MM-DD HH:mm:ss'),
          durationMin: res.duration_min || 25,
        })
      }
    } catch (err) {
      console.error('Failed to start pomodoro:', err)
    }
  }, [])

  // 完成待办
  const handleCompleteTodo = useCallback(async (todo: Todo) => {
    try {
      await updateTodo(todo.id, { status: 'completed' })
      setTodos(prev => prev.map(t => t.id === todo.id ? { ...t, status: 'completed' } : t))
      // 触发接力链：待办完成 → 推荐下一步
      const nextTodo = todos.find(t => t.id !== todo.id && t.status !== 'completed')
      triggerEvent('todo_completed', {
        todoId: todo.id,
        todoTitle: todo.title,
        nextTodoId: nextTodo?.id,
        nextTodoTitle: nextTodo?.title,
        nextTodo: !!nextTodo,
      })
    } catch (err) {
      console.error('Failed to complete todo:', err)
    }
  }, [todos, triggerEvent])

  // 切换采集状态
  const toggleCollector = useCallback(async () => {
    try {
      if (status?.running && !status?.paused) {
        await pauseCollector()
      } else {
        await resumeCollector()
      }
      const newStatus = await getStatus()
      setStatus(newStatus)
    } catch (err) {
      console.error('Failed to toggle collector:', err)
    }
  }, [status])

  // 计算今日评分（0-100）
  const dailyScore = useMemo(() => {
    if (!stats) return null
    const totalMin = stats.total_duration_min || 0
    const focusSessions = stats.focus_sessions || 0
    const completedTodos = todos.filter(t => t.status === 'completed').length
    const totalTodos = todos.length || 1

    // 有效时间 40%，番茄钟 20%，任务完成率 25%，习惯 15%（简化）
    const timeScore = Math.min(100, (totalMin / 480) * 100) * 0.4
    const focusScore = Math.min(100, focusSessions * 12.5) * 0.2
    const todoScore = (completedTodos / totalTodos) * 100 * 0.25
    const habitScore = 70 * 0.15 // 简化，后续接入习惯数据

    return Math.round(timeScore + focusScore + todoScore + habitScore)
  }, [stats, todos])

  const totalMin = stats?.total_duration_min || 0
  const hours = Math.floor(totalMin / 60)
  const mins = Math.round(totalMin % 60)
  const isRecording = status?.running && !status?.paused

  const incompleteTodos = todos.filter(t => t.status !== 'completed')
  const completedTodos = todos.filter(t => t.status === 'completed')

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="w-8 h-8 border-3 border-cd-green border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-cd-text-tertiary text-sm">正在加载今日数据...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto pb-24 animate-fade-in">
      {/* ─── 顶部问候 + 状态 ─── */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-cd-text font-display flex items-center gap-2">
              <greeting.icon size={24} className="text-cd-gold" />
              {greeting.text}
            </h1>
            <p className="text-sm text-cd-text-tertiary mt-1">
              {dayjs().format('M月D日 dddd')} · 今天是新的一天
            </p>
          </div>

          {/* 采集状态按钮 */}
          <button
            onClick={toggleCollector}
            className={`flex items-center gap-2 text-sm px-4 py-2 rounded-lg transition border ${
              isRecording
                ? 'border-cd-green/20 bg-cd-green/5 text-cd-green'
                : 'border-cd-red/20 bg-cd-red/5 text-cd-red'
            }`}
          >
            {isRecording ? (
              <><span className="w-2 h-2 rounded-full bg-cd-green animate-pulse-soft" /> 正在记录</>
            ) : (
              <><Pause size={14} /> 已暂停</>
            )}
          </button>
        </div>

        {/* 核心指标 */}
        <div className="grid grid-cols-4 gap-4 mt-5">
          <MetricCard
            icon={<Clock size={16} />}
            label="有效时间"
            value={hours > 0 ? `${hours}h ${mins}m` : `${mins}m`}
            sub={`${status?.total_captures || 0} 次捕捉`}
          />
          <MetricCard
            icon={<Zap size={16} />}
            label="番茄钟"
            value={`${stats?.focus_sessions || 0} 个`}
            sub={stats?.longest_focus_min ? `最长 ${stats.longest_focus_min}分钟` : '今日暂无'}
          />
          <MetricCard
            icon={<CheckCircle2 size={16} />}
            label="待办完成"
            value={`${completedTodos.length}/${todos.length}`}
            sub={incompleteTodos.length > 0 ? `${incompleteTodos.length} 项待完成` : '全部完成！'}
          />
          <MetricCard
            icon={<TrendingUp size={16} />}
            label="今日评分"
            value={dailyScore !== null ? `${dailyScore}分` : '-'}
            sub={dailyScore !== null ? (dailyScore >= 80 ? '优秀' : dailyScore >= 60 ? '良好' : '继续加油') : '数据积累中'}
            highlight={dailyScore !== null && dailyScore >= 80}
          />
        </div>
      </div>

      {/* ─── 动态卡片区（根据时间显示不同内容）─── */}
      <div className="space-y-4 mb-6">
        {/* 早晨：晨报 + 今日计划 */}
        {(timeOfDay === 'morning' || timeOfDay === 'forenoon') && (
          <>
            {morningInsights.length > 0 && (
              <MorningBriefCard insights={morningInsights} />
            )}
            <TodayPlanCard
              todos={incompleteTodos}
              onStartTodo={handleStartPomodoro}
              onCompleteTodo={handleCompleteTodo}
              onAddTodo={() => navigate('/todos')}
            />
          </>
        )}

        {/* 白天：番茄钟状态 + 接下来 */}
        {(timeOfDay === 'forenoon' || timeOfDay === 'afternoon') && (
          <>
            {activePomodoro ? (
              <ActivePomodoroCard
                pomodoro={activePomodoro}
                onComplete={handleEndPomodoro}
              />
            ) : (
              <StartFocusCard
                nextTodo={incompleteTodos[0]}
                onStart={() => handleStartPomodoro(incompleteTodos[0])}
              />
            )}
            {incompleteTodos.length > 0 && !activePomodoro && (
              <NextActionsCard
                todos={incompleteTodos.slice(0, 3)}
                onStartTodo={handleStartPomodoro}
              />
            )}
          </>
        )}

        {/* 中午：休息提示 */}
        {timeOfDay === 'noon' && (
          <BreakCard />
        )}

        {/* 晚上：日报 + 晚间仪式 */}
        {(timeOfDay === 'evening' || timeOfDay === 'night') && (
          <>
            <DailyReportCard
              stats={stats}
              activities={activities}
              onViewFullReport={() => navigate('/report')}
            />
            <EveningRitualCard
              onWriteDiary={() => navigate('/diary')}
              onPlanTomorrow={() => navigate('/week-plan')}
            />
          </>
        )}
      </div>

      {/* ─── 分隔线 ─── */}
      <div className="border-t border-cd-border mb-4" />

      {/* ─── 今日时间线 ─── */}
      <div className="bg-cd-card border border-cd-border rounded-xl p-5">
        <TodayTimeline
          activities={activities}
          todos={todos}
          currentActivity={activities[0]}
          onStartTodo={handleStartPomodoro}
          onCompleteTodo={handleCompleteTodo}
        />
      </div>

      {/* ─── 快捷入口 ─── */}
      <div className="flex items-center gap-3 mt-6 flex-wrap">
        <QuickLink icon={<Calendar size={14} />} label="周计划" onClick={() => navigate('/week-plan')} />
        <QuickLink icon={<Target size={14} />} label="目标" onClick={() => navigate('/goals')} />
        <QuickLink icon={<Flame size={14} />} label="习惯" onClick={() => navigate('/habits')} />
        <QuickLink icon={<Sparkles size={14} />} label="深度洞察" onClick={() => navigate('/profile')} />
        <QuickLink icon={<TrendingUp size={14} />} label="完整报告" onClick={() => navigate('/report')} />
      </div>
    </div>
  )
}

// ─── 子组件 ──────────────────────────────────────────────

function MetricCard({ icon, label, value, sub, highlight }: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
  highlight?: boolean
}) {
  return (
    <div className={`bg-cd-card border rounded-xl p-4 transition ${
      highlight ? 'border-cd-gold/30 bg-cd-gold/5' : 'border-cd-border'
    }`}>
      <div className="flex items-center gap-1.5 text-cd-text-tertiary mb-2">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <p className={`text-xl font-bold font-brand tracking-tight ${
        highlight ? 'text-cd-gold' : 'text-cd-text'
      }`}>
        {value}
      </p>
      {sub && <p className="text-xs text-cd-text-tertiary mt-0.5">{sub}</p>}
    </div>
  )
}

function MorningBriefCard({ insights }: { insights: MorningInsight[] }) {
  return (
    <div className="bg-gradient-to-br from-cd-gold/5 to-cd-green/5 border border-cd-gold/20 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-3">
        <Sunrise size={18} className="text-cd-gold" />
        <h3 className="text-sm font-semibold text-cd-text">今日晨报</h3>
      </div>
      <div className="space-y-2">
        {insights.slice(0, 3).map((insight, i) => (
          <div key={i} className="flex items-start gap-2 text-sm">
            <span className="text-cd-gold shrink-0">{i + 1}.</span>
            <p className="text-cd-text-secondary">{insight.body || insight.title || '今日建议'}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function TodayPlanCard({ todos, onStartTodo, onCompleteTodo, onAddTodo }: {
  todos: Todo[]
  onStartTodo: (todo: Todo) => void
  onCompleteTodo: (todo: Todo) => void
  onAddTodo: () => void
}) {
  return (
    <div className="bg-cd-card border border-cd-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-cd-text flex items-center gap-2">
          <Target size={16} className="text-cd-green" />
          今日计划
        </h3>
        <button
          onClick={onAddTodo}
          className="text-xs text-cd-green hover:underline flex items-center gap-1"
        >
          管理待办 <ChevronRight size={12} />
        </button>
      </div>

      {todos.length === 0 ? (
        <div className="text-center py-6">
          <p className="text-sm text-cd-text-tertiary mb-3">今天还没有计划任务</p>
          <button
            onClick={onAddTodo}
            className="text-sm bg-cd-green text-white px-4 py-2 rounded-lg hover:opacity-90 transition"
          >
            添加第一个任务
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {todos.map((todo) => (
            <div
              key={todo.id}
              className="flex items-center gap-3 p-3 rounded-lg bg-cd-bg-secondary hover:bg-cd-hover transition group"
            >
              <button
                onClick={() => onCompleteTodo(todo)}
                className="w-5 h-5 rounded-full border-2 border-cd-border flex items-center justify-center shrink-0 hover:border-cd-green transition"
              >
                <CheckCircle2 size={12} className="text-cd-green opacity-0 group-hover:opacity-100 transition" />
              </button>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-cd-text truncate">{todo.title}</p>
                {todo.target_min > 0 && (
                  <p className="text-xs text-cd-text-tertiary mt-0.5">目标 {todo.target_min} 分钟</p>
                )}
              </div>
              <button
                onClick={() => onStartTodo(todo)}
                className="flex items-center gap-1 bg-cd-green/10 text-cd-green px-3 py-1.5 rounded-lg text-xs font-medium hover:bg-cd-green/20 transition opacity-0 group-hover:opacity-100"
              >
                <Play size={12} /> 开始
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ActivePomodoroCard({ pomodoro, onComplete }: {
  pomodoro: { taskTitle?: string; startTime: string; durationMin: number }
  onComplete: () => void
}) {
  const [remaining, setRemaining] = useState(0)

  useEffect(() => {
    const calc = () => {
      const elapsed = dayjs().diff(dayjs(pomodoro.startTime), 'second')
      const rem = Math.max(0, pomodoro.durationMin * 60 - elapsed)
      setRemaining(rem)
    }
    calc()
    const timer = setInterval(calc, 1000)
    return () => clearInterval(timer)
  }, [pomodoro])

  const mins = Math.floor(remaining / 60)
  const secs = remaining % 60
  const progress = ((pomodoro.durationMin * 60 - remaining) / (pomodoro.durationMin * 60)) * 100

  return (
    <div className="bg-gradient-to-br from-cd-green/10 to-cd-purple/5 border border-cd-green/20 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-cd-text flex items-center gap-2">
          <Zap size={16} className="text-cd-green animate-pulse" />
          专注进行中
        </h3>
        <span className="text-2xl font-bold font-brand text-cd-green tabular-nums">
          {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
        </span>
      </div>
      {pomodoro.taskTitle && (
        <p className="text-sm text-cd-text-secondary mb-3">任务：{pomodoro.taskTitle}</p>
      )}
      <div className="h-2 rounded-full bg-cd-bg-secondary overflow-hidden mb-4">
        <div
          className="h-full bg-cd-green rounded-full transition-all duration-1000"
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="flex gap-2">
        <button
          onClick={onComplete}
          className="flex-1 bg-cd-green text-white py-2 rounded-lg text-sm font-medium hover:opacity-90 transition"
        >
          结束专注
        </button>
        <button className="px-4 py-2 border border-cd-border rounded-lg text-sm text-cd-text-secondary hover:bg-cd-hover transition">
          加时5分钟
        </button>
      </div>
    </div>
  )
}

function StartFocusCard({ nextTodo, onStart }: {
  nextTodo?: Todo
  onStart: () => void
}) {
  return (
    <div className="bg-cd-card border border-cd-border rounded-xl p-5 text-center">
      <div className="w-12 h-12 rounded-full bg-cd-green/10 flex items-center justify-center mx-auto mb-3">
        <Zap size={24} className="text-cd-green" />
      </div>
      <h3 className="text-base font-semibold text-cd-text mb-1">准备开始专注？</h3>
      <p className="text-sm text-cd-text-tertiary mb-4">
        {nextTodo ? `下一个任务：${nextTodo.title}` : '选择一个任务开始25分钟专注'}
      </p>
      <button
        onClick={onStart}
        className="bg-cd-green text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:opacity-90 transition inline-flex items-center gap-2"
      >
        <Play size={16} /> 开始25分钟专注
      </button>
    </div>
  )
}

function NextActionsCard({ todos, onStartTodo }: {
  todos: Todo[]
  onStartTodo: (todo: Todo) => void
}) {
  return (
    <div className="bg-cd-card border border-cd-border rounded-xl p-5">
      <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
        <ChevronRight size={16} className="text-cd-green" />
        接下来
      </h3>
      <div className="space-y-2">
        {todos.map((todo, i) => (
          <div key={todo.id} className="flex items-center gap-3">
            <span className="text-xs text-cd-text-tertiary w-4">{i + 1}</span>
            <span className="flex-1 text-sm text-cd-text truncate">{todo.title}</span>
            <button
              onClick={() => onStartTodo(todo)}
              className="text-xs text-cd-green hover:underline"
            >
              开始
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

function BreakCard() {
  return (
    <div className="bg-gradient-to-br from-cd-purple/5 to-cd-gold/5 border border-cd-purple/20 rounded-xl p-5 text-center">
      <Coffee size={28} className="text-cd-purple mx-auto mb-2" />
      <h3 className="text-base font-semibold text-cd-text mb-1">午休时间</h3>
      <p className="text-sm text-cd-text-tertiary">
        站起来走走，喝杯水，让大脑休息一下。下午会更高效。
      </p>
    </div>
  )
}

function DailyReportCard({ stats, activities, onViewFullReport }: {
  stats: TodayStats | null
  activities: Activity[]
  onViewFullReport: () => void
}) {
  const categories = stats?.categories
    ? Object.entries(stats.categories)
        .map(([name, value]) => ({ name, value: Math.round(value as number) }))
        .filter(d => d.value > 0)
        .sort((a, b) => b.value - a.value)
    : []
  const totalMin = categories.reduce((s, d) => s + d.value, 0)

  return (
    <div className="bg-cd-card border border-cd-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-cd-text flex items-center gap-2">
          <TrendingUp size={16} className="text-cd-green" />
          今日日报
        </h3>
        <button
          onClick={onViewFullReport}
          className="text-xs text-cd-green hover:underline flex items-center gap-1"
        >
          查看完整报告 <ChevronRight size={12} />
        </button>
      </div>

      {categories.length > 0 ? (
        <div className="space-y-3">
          {categories.slice(0, 5).map((entry) => {
            const pct = totalMin > 0 ? Math.round((entry.value / totalMin) * 100) : 0
            const color = CATEGORY_COLORS[entry.name] || 'var(--cd-text-tertiary)'
            return (
              <div key={entry.name}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full" style={{ background: color }} />
                    <span className="text-sm text-cd-text">{entry.name}</span>
                  </div>
                  <span className="text-sm text-cd-text-tertiary">
                    {entry.value >= 60 ? `${(entry.value / 60).toFixed(1)}h` : `${entry.value}m`}
                    <span className="text-xs ml-1">{pct}%</span>
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-cd-bg-secondary overflow-hidden">
                  <div className="h-full rounded-full transition-all" style={{ width: `${Math.max(pct, 2)}%`, background: color }} />
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="text-sm text-cd-text-tertiary text-center py-4">今日数据积累中</p>
      )}

      {activities.length > 0 && (
        <div className="mt-4 pt-4 border-t border-cd-border">
          <p className="text-xs text-cd-text-tertiary mb-2">今日共记录 {activities.length} 条活动</p>
        </div>
      )}
    </div>
  )
}

function EveningRitualCard({ onWriteDiary, onPlanTomorrow }: {
  onWriteDiary: () => void
  onPlanTomorrow: () => void
}) {
  return (
    <div className="bg-gradient-to-br from-cd-purple/5 to-cd-green/5 border border-cd-purple/20 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
        <Moon size={16} className="text-cd-purple" />
        晚间仪式
      </h3>
      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={onWriteDiary}
          className="p-4 rounded-lg bg-cd-bg-secondary hover:bg-cd-hover transition text-left"
        >
          <p className="text-sm font-medium text-cd-text mb-1">📝 写日记</p>
          <p className="text-xs text-cd-text-tertiary">AI 已预填今日数据，补充几句感受即可</p>
        </button>
        <button
          onClick={onPlanTomorrow}
          className="p-4 rounded-lg bg-cd-bg-secondary hover:bg-cd-hover transition text-left"
        >
          <p className="text-sm font-medium text-cd-text mb-1">📅 规划明天</p>
          <p className="text-xs text-cd-text-tertiary">AI 根据今日进度建议明日重点</p>
        </button>
      </div>
    </div>
  )
}

function QuickLink({ icon, label, onClick }: {
  icon: React.ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 text-xs text-cd-text-secondary px-3 py-1.5 rounded-lg border border-cd-border hover:border-cd-green/30 hover:text-cd-green transition"
    >
      {icon}
      {label}
    </button>
  )
}
