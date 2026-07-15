import { useState, useEffect, useMemo } from 'react'
import {
  ResponsiveContainer, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Legend,
  BarChart, Bar,
  PieChart, Pie, Cell,
} from 'recharts'
import {
  getTodos, getTodayTodos, getWeekPlan, getWeekPlanStats, getMonthPlanStats, getActivities,
  getGoalSummary,
  CATEGORY_COLORS, formatLocalDate, getWeekStart, getWeekDates, getMonthKey,
  type TodoV2, type WeekPlanStats, type MonthPlanStats,
} from '../api/client'
import { Flame, TrendingUp, Calendar, CalendarDays, CalendarRange, Clock, Loader2, LayoutDashboard, Target } from 'lucide-react'
import SankeyChart from '../components/SankeyChart'

/** 简单进度条 */
function ProgressBar({ value, color = 'var(--cd-green)' }: { value: number; color?: string }) {
  const pct = Math.min(100, Math.max(0, value))
  return (
    <div className="w-full h-2 rounded-full bg-cd-bg-input overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-700"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  )
}

/** 圆形进度环 */
function ProgressCircle({ value, size = 64, color = 'var(--cd-green)' }: { value: number; size?: number; color?: string }) {
  const radius = (size - 8) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = Math.min(100, Math.max(0, value))
  const offset = circumference - (clamped / 100) * circumference
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--cd-border)" strokeWidth="5" />
      <circle
        cx={size / 2} cy={size / 2} r={radius}
        fill="none" stroke={color} strokeWidth="5"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        className="transition-all duration-700"
      />
      <text x={size / 2} y={size / 2} textAnchor="middle" dominantBaseline="central" className="text-xs font-bold fill-cd-text">
        {Math.round(clamped)}%
      </text>
    </svg>
  )
}

/** 顶部进度卡片 */
function ProgressCard({
  icon: Icon, label, completed, total, color, variant = 'bar',
}: {
  icon: React.ElementType
  label: string
  completed: number
  total: number
  color: string
  variant?: 'bar' | 'ring'
}) {
  const rate = total > 0 ? (completed / total) * 100 : 0
  return (
    <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2 text-cd-text-secondary">
        <Icon size={15} style={{ color }} />
        <span className="text-xs font-medium">{label}</span>
      </div>
      {variant === 'ring' ? (
        <div className="flex items-center gap-3">
          <ProgressCircle value={rate} size={64} color={color} />
          <div>
            <div className="text-lg font-bold text-cd-text tabular-nums">
              {completed}<span className="text-sm text-cd-text-tertiary">/{total}</span>
            </div>
            <div className="text-[11px] text-cd-text-tertiary">已完成 / 总数</div>
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold text-cd-text tabular-nums">{completed}</span>
            <span className="text-sm text-cd-text-tertiary">/ {total}</span>
            <span className="ml-auto text-xs text-cd-text-tertiary tabular-nums">{rate.toFixed(0)}%</span>
          </div>
          <ProgressBar value={rate} color={color} />
        </>
      )}
    </div>
  )
}

interface BurndownPoint {
  day: string
  理想: number
  实际: number | null
}

interface CategorySlice {
  name: string
  value: number
  color: string
}

interface GoalSummaryItem {
  id: number
  title: string
  category: string
  timeframe: string
  target_date: string
  progress: number
  color: string
  status: string
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [yearStats, setYearStats] = useState({ completed: 0, total: 0 })
  const [monthStats, setMonthStats] = useState<MonthPlanStats | null>(null)
  const [weekStats, setWeekStats] = useState<WeekPlanStats | null>(null)
  const [todayStats, setTodayStats] = useState({ completed: 0, total: 0 })
  const [burndown, setBurndown] = useState<BurndownPoint[]>([])
  const [categoryData, setCategoryData] = useState<CategorySlice[]>([])
  const [deepFocusTrend, setDeepFocusTrend] = useState<Array<{ date: string; min: number }>>([])
  const [goals, setGoals] = useState<GoalSummaryItem[]>([])

  const now = useMemo(() => new Date(), [])
  const weekStart = useMemo(() => getWeekStart(now), [now])
  const weekDates = useMemo(() => getWeekDates(weekStart), [weekStart])
  const monthKey = useMemo(() => getMonthKey(now), [now])
  const yearStr = useMemo(() => String(now.getFullYear()), [now])
  const todayStr = useMemo(() => formatLocalDate(now), [now])

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError('')
      try {
        // 并行拉取主数据
        const [todosRes, todayTodosRes, wkStats, moStats, weekPlan, goalSum] = await Promise.all([
          getTodos(),
          getTodayTodos(),
          getWeekPlanStats(weekStart).catch(() => null),
          getMonthPlanStats(monthKey).catch(() => null),
          getWeekPlan(weekStart).catch(() => null),
          getGoalSummary().catch(() => ({ goals: [] })),
        ])
        setGoals(goalSum.goals || [])

        // 年度统计：按 assigned_date 或 created_at 过滤本年
        const yearTodos = (todosRes.todos as TodoV2[]).filter(t => {
          const d = t.assigned_date || (t.created_at || '').slice(0, 10)
          return d.startsWith(yearStr)
        })
        setYearStats({
          total: yearTodos.length,
          completed: yearTodos.filter(t => t.status === 'completed').length,
        })

        // 今日统计
        setTodayStats({
          total: todayTodosRes.todos.length,
          completed: todayTodosRes.todos.filter(t => t.status === 'completed').length,
        })

        setWeekStats(wkStats)
        setMonthStats(moStats)

        // 燃尽图：基于本周任务的 completed_at 计算每日剩余
        const weekTasks = weekPlan?.week_tasks || []
        const totalTasks = weekTasks.length
        const burndownData: BurndownPoint[] = weekDates.map((d, i) => {
          const dayEnd = d + ' 23:59:59'
          // 理想线：从 total 线性降到 0
          const ideal = Math.max(0, Math.round(totalTasks * (1 - (i + 1) / 7)))
          // 实际线：截至当天已完成的任务数
          const completedByDay = weekTasks.filter(t => {
            if (t.status !== 'completed' || !t.completed_at) return false
            return t.completed_at <= dayEnd
          }).length
          // 未来日期不显示实际线
          const isFuture = d > todayStr
          return {
            day: d.slice(5), // MM-DD
            理想: ideal,
            实际: isFuture ? null : (totalTasks - completedByDay),
          }
        })
        setBurndown(burndownData)

        // 深度工作趋势：来自 weekStats.daily_focus
        if (wkStats?.daily_focus) {
          setDeepFocusTrend(wkStats.daily_focus.map(d => ({ date: d.date, min: d.focus_min })))
        }

        // 分类时间分布：拉取本周 7 天活动，按分类聚合 duration_min
        const actsPerDay = await Promise.all(
          weekDates.map(d => getActivities(d, 1, 300).then(r => r.activities).catch(() => []))
        )
        const allActs = actsPerDay.flat()
        const catAgg: Record<string, number> = {}
        for (const a of allActs) {
          if (!a.category) continue
          catAgg[a.category] = (catAgg[a.category] || 0) + (a.duration_min || 0)
        }
        const slices: CategorySlice[] = Object.entries(catAgg)
          .filter(([, v]) => v > 0)
          .sort((a, b) => b[1] - a[1])
          .map(([name, value]) => ({
            name,
            value: Math.round(value),
            color: CATEGORY_COLORS[name] || '#9999B0',
          }))
        setCategoryData(slices)
      } catch (e) {
        setError('仪表盘数据加载失败')
        console.error(e)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [weekStart, weekDates, monthKey, yearStr, todayStr])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 text-cd-green animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-20 text-cd-red">
        <p>{error}</p>
        <button onClick={() => location.reload()} className="mt-3 text-sm text-cd-green hover:underline">
          重试
        </button>
      </div>
    )
  }

  const streak = weekStats?.streak_days || 0

  return (
    <div className="min-h-screen max-w-6xl mx-auto space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-cd-text">进度仪表盘</h1>
          <p className="text-xs text-cd-text-tertiary mt-1">
            年/月/周/日四级进度穿透 · 燃尽图 · 连续天数 · 分类分布
          </p>
        </div>
        <a href="#/" className="text-sm text-cd-green hover:underline flex items-center gap-1">
          <LayoutDashboard className="w-4 h-4" /> 返回今日总览
        </a>
      </div>

      {/* 顶部：四级进度穿透卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <ProgressCard
          icon={CalendarRange}
          label="年度进度"
          completed={yearStats.completed}
          total={yearStats.total}
          color="#7B68EE"
          variant="bar"
        />
        <ProgressCard
          icon={CalendarDays}
          label="月度进度"
          completed={monthStats?.completed_tasks || 0}
          total={monthStats?.total_tasks || 0}
          color="#F0A030"
          variant="ring"
        />
        <ProgressCard
          icon={Calendar}
          label="周度进度"
          completed={weekStats?.completed_tasks || 0}
          total={weekStats?.total_tasks || 0}
          color="#5B8DEF"
          variant="bar"
        />
        <ProgressCard
          icon={Clock}
          label="今日进度"
          completed={todayStats.completed}
          total={todayStats.total}
          color="#22c55e"
          variant="bar"
        />
      </div>

      {/* 中部：燃尽图 + Streak/深度工作 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 燃尽图 */}
        <div className="lg:col-span-2 bg-cd-bg-card rounded-xl border border-white/5 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-cd-text">本周燃尽图</h3>
            <span className="text-xs text-cd-text-tertiary">剩余任务数</span>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={burndown} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="day" tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 11 }} axisLine={{ stroke: 'var(--cd-border)' }} />
              <YAxis tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 11 }} axisLine={{ stroke: 'var(--cd-border)' }} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  background: 'var(--cd-bg-card)',
                  border: '1px solid var(--cd-border)',
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: 'var(--cd-text)' }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="理想" stroke="#888888" strokeDasharray="5 5" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="实际" stroke="var(--cd-green)" strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Streak + 深度工作趋势 */}
        <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-cd-text">连续专注</h3>
            <Flame size={16} className="text-orange-400" />
          </div>
          {/* Streak 大数字 */}
          <div className="flex items-baseline gap-2 mb-1">
            <span className="text-4xl font-bold text-orange-400 tabular-nums">{streak}</span>
            <span className="text-sm text-cd-text-tertiary">天连续</span>
          </div>
          <p className="text-[11px] text-cd-text-tertiary mb-3">保持每日专注，持续燃烧 🔥</p>

          {/* 7 日深度工作柱状图 */}
          <div className="text-xs text-cd-text-secondary mb-2 flex items-center gap-1">
            <TrendingUp size={12} /> 本周深度工作时长（分钟）
          </div>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={deepFocusTrend} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 10 }} axisLine={{ stroke: 'var(--cd-border)' }} />
              <YAxis tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 10 }} axisLine={{ stroke: 'var(--cd-border)' }} />
              <Tooltip
                contentStyle={{
                  background: 'var(--cd-bg-card)',
                  border: '1px solid var(--cd-border)',
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(v: number) => [`${v} 分钟`, '专注']}
              />
              <Bar dataKey="min" fill="var(--cd-green)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 底部：分类时间分布饼图 */}
      <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-cd-text">本周分类时间分布</h3>
          <span className="text-xs text-cd-text-tertiary">
            共 {categoryData.reduce((s, c) => s + c.value, 0)} 分钟
          </span>
        </div>
        {categoryData.length === 0 ? (
          <div className="text-center py-10 text-cd-text-tertiary text-sm">
            暂无活动数据
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={categoryData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  innerRadius={45}
                  paddingAngle={2}
                >
                  {categoryData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: 'var(--cd-bg-card)',
                    border: '1px solid var(--cd-border)',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(v: number, n: string) => [`${v} 分钟`, n]}
                />
              </PieChart>
            </ResponsiveContainer>
            {/* 图例：分类名 + 时长 */}
            <div className="space-y-1.5 max-h-[260px] overflow-y-auto pr-2">
              {categoryData.map(c => {
                const total = categoryData.reduce((s, x) => s + x.value, 0)
                const pct = total > 0 ? (c.value / total) * 100 : 0
                return (
                  <div key={c.name} className="flex items-center gap-2 text-xs">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: c.color }} />
                    <span className="text-cd-text flex-1 truncate">{c.name}</span>
                    <span className="text-cd-text-secondary tabular-nums">{c.value}m</span>
                    <span className="text-cd-text-tertiary tabular-nums w-10 text-right">{pct.toFixed(0)}%</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* P14-3：今日时间流动桑基图（时段 → 分类，组件自带卡片样式） */}
      <SankeyChart date={todayStr} />

      {/* P5-5：长期目标进度穿透卡片 */}
      <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-cd-text flex items-center gap-1.5">
            <Target size={14} className="text-cd-accent" /> 长期目标进度
          </h3>
          <a href="#/goals" className="text-xs text-cd-green hover:underline">管理目标 →</a>
        </div>
        {goals.length === 0 ? (
          <div className="text-center py-8 text-cd-text-tertiary text-sm">
            <Target size={28} className="mx-auto mb-2 opacity-40" />
            <p>还没有活跃的长期目标</p>
            <a href="#/goals" className="inline-block mt-2 text-xs text-cd-green hover:underline">去创建第一个目标 →</a>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {goals.slice(0, 6).map(g => {
              const daysLeft = g.target_date
                ? Math.ceil((new Date(g.target_date + 'T00:00:00').getTime() - now.getTime()) / 86400000)
                : null
              const isOverdue = daysLeft !== null && daysLeft < 0
              const tfLabel = g.timeframe === 'yearly' ? '年度' : g.timeframe === 'quarterly' ? '季度' : '月度'
              return (
                <a
                  key={g.id}
                  href="#/goals"
                  className="block bg-cd-bg-input/50 rounded-lg border border-cd-border p-3 hover:border-cd-accent/40 transition group"
                >
                  <div className="flex items-start gap-2 mb-2">
                    <span
                      className="w-2 h-2 rounded-full mt-1.5 shrink-0"
                      style={{ background: g.color || '#7B68EE' }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-cd-text truncate group-hover:text-cd-accent transition">
                        {g.title}
                      </div>
                      <div className="text-[10px] text-cd-text-tertiary mt-0.5 flex items-center gap-1.5">
                        <span>{tfLabel}</span>
                        <span>·</span>
                        <span>{g.category}</span>
                        {daysLeft !== null && (
                          <>
                            <span>·</span>
                            <span className={isOverdue ? 'text-cd-red' : daysLeft <= 7 ? 'text-orange-400' : ''}>
                              {isOverdue ? `逾期 ${-daysLeft} 天` : `剩 ${daysLeft} 天`}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <ProgressBar value={g.progress} color={g.color || '#7B68EE'} />
                    <span className="text-xs font-bold tabular-nums text-cd-text shrink-0 w-9 text-right">
                      {g.progress}%
                    </span>
                  </div>
                </a>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
