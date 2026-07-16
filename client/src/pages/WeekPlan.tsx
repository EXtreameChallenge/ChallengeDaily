import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Calendar, CalendarDays, ChevronLeft, ChevronRight, Plus, GripVertical, Play, X, Target,
  Search, Flame, Clock, ChevronDown, ChevronUp, ExternalLink, Layers,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, Cell as RechartsCell, ResponsiveContainer, Tooltip,
} from 'recharts'
import {
  getWeekPlan, getUnassignedTodos, getWeekPlanStats, getMonthPlan, getMonthPlanStats,
  assignTodo, unassignTodo, createTodo, request, updatePlanMeta,
  getWeekStart, getWeekDates, getMonthKey,
  CATEGORY_COLORS, POMODORO_SIZES,
  type TodoV2, type WeekPlanData, type WeekPlanStats, type MonthPlanData, type MonthPlanStats,
} from '../api/client'
import { useToast } from '../components/Toast'
import TaskDetailModal from '../components/TaskDetailModal'
import TaskCreateModal from '../components/TaskCreateModal'

// AI 拆解草案任务类型
interface SplitDraftTask {
  title: string
  target_min: number
  category: string
  day?: number
  _checked?: boolean
}

// ── 常量 ──
const PRIORITY_COLORS = ['#ef4444', '#f59e0b', '#F0C040', '#10b981', '#6b7280']
const MODE_LABELS: Record<string, string> = { timer: '计时', goal: '目标', habit: '习惯' }
const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const DAILY_LIMIT = 180 // 负载警示阈值（分钟）
// GitHub 风格热力色阶（5 级）
const HEAT_COLORS = ['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353']
// 月历完成率热力色（0% 灰，分级绿）
function monthHeatColor(rate: number): string {
  if (rate <= 0) return 'var(--cd-bg-tertiary)'
  if (rate <= 0.3) return '#0e4429'
  if (rate <= 0.6) return '#006d32'
  if (rate <= 0.9) return '#26a641'
  return '#39d353'
}
function heatColor(min: number): string {
  if (min <= 0) return HEAT_COLORS[0]
  if (min < 60) return HEAT_COLORS[1]
  if (min < 120) return HEAT_COLORS[2]
  if (min < 200) return HEAT_COLORS[3]
  return HEAT_COLORS[4]
}

type ViewMode = 'year' | 'month' | 'week' | 'day'
const VIEW_TABS: { key: ViewMode; emoji: string; label: string }[] = [
  { key: 'year', emoji: '📅', label: '年计划' },
  { key: 'month', emoji: '📆', label: '月计划' },
  { key: 'week', emoji: '📋', label: '周计划' },
  { key: 'day', emoji: '✅', label: '日计划' },
]

// ── 本地日期工具（不受时区影响，每次调用动态计算）──
function getTodayStr(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function formatLocalDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function formatLocalMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
function fmtDate(d: string) {
  const dt = new Date(d + 'T00:00:00')
  return `${dt.getMonth() + 1}/${dt.getDate()}`
}
function isWeekend(d: string) {
  const day = new Date(d + 'T00:00:00').getDay()
  return day === 0 || day === 6
}
function dayMin(todos: TodoV2[]) {
  return todos.reduce((s, t) => s + (t.target_min || 0), 0)
}
// ISO 周序号
function getISOWeek(dateStr: string): number {
  const d = new Date(dateStr + 'T00:00:00')
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = (t.getUTCDay() + 6) % 7
  t.setUTCDate(t.getUTCDate() - dayNum + 3)
  const firstThursday = new Date(Date.UTC(t.getUTCFullYear(), 0, 4))
  return 1 + Math.round(((t.getTime() - firstThursday.getTime()) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7)
}
// 生成某年的 53 个周一日期（覆盖整年）
function getYearWeekStarts(year: number): string[] {
  const weeks: string[] = []
  let cur = getWeekStart(new Date(year, 0, 1))
  for (let i = 0; i < 53; i++) {
    weeks.push(cur)
    const d = new Date(cur + 'T00:00:00')
    d.setDate(d.getDate() + 7)
    cur = formatLocalDate(d)
  }
  return weeks
}
// HH:MM 格式
function fmtHM(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

// ── SVG 环形进度 ──
function ProgressRing({ pct, size = 14, stroke = 2, color = '#10b981' }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const off = c - (Math.min(100, Math.max(0, pct)) / 100) * c
  return (
    <svg width={size} height={size} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--cd-border)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  )
}

// ── 任务卡片（共享组件，含分类色条 + 进度环 + 可展开）──
interface CardProps {
  todo: TodoV2
  compact?: boolean
  onClick?: () => void
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: (e: React.DragEvent) => void
  expanded?: boolean
  onToggleExpand?: () => void
}
function TaskCard({ todo, compact, onClick, onDragStart, onDragEnd, expanded, onToggleExpand }: CardProps) {
  const isDone = todo.status === 'completed'
  const pc = PRIORITY_COLORS[(todo.priority || 3) - 1]
  const catColor = CATEGORY_COLORS[todo.category] || '#9999B0'
  const pct = todo.target_min > 0 ? (todo.progress_min / todo.target_min) * 100 : 0
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className="relative rounded-md cursor-grab active:cursor-grabbing transition hover:brightness-110 overflow-hidden"
      style={{
        background: compact ? 'var(--cd-bg-tertiary)' : 'var(--cd-bg-secondary)',
        borderLeft: `3px solid ${pc}`,
        padding: '6px 8px 6px 10px',
      }}
    >
      {/* 分类色条（顶部 2px） */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: catColor }} />
      <GripVertical size={8} className="absolute top-1 right-1 opacity-30" style={{ color: 'var(--cd-text-tertiary)' }} />
      {onToggleExpand && (
        <button
          onClick={(e) => { e.stopPropagation(); onToggleExpand() }}
          className="absolute top-1 right-3 opacity-50 hover:opacity-100"
          style={{ color: 'var(--cd-text-tertiary)' }}
          title={expanded ? '收起' : '展开'}
        >
          {expanded ? <ChevronUp size={9} /> : <ChevronDown size={9} />}
        </button>
      )}
      <div className="text-cd-text leading-tight pr-6" style={{ fontSize: 9, textDecoration: isDone ? 'line-through' : 'none', opacity: isDone ? 0.6 : 1 }}>
        {todo.title}
      </div>
      <div className="flex items-center justify-between mt-1" style={{ fontSize: 7, opacity: isDone ? 0.6 : 1 }}>
        <span className="text-cd-text-tertiary truncate max-w-[60%]">
          <span style={{ color: catColor }}>●</span> {todo.category} · {MODE_LABELS[todo.mode] || todo.mode}
        </span>
        <span className="text-cd-text-tertiary tabular-nums flex items-center gap-1">
          <ProgressRing pct={pct} size={10} stroke={1.5} color={isDone ? '#10b981' : catColor} />
          {todo.progress_min}/{todo.target_min}m
        </span>
      </div>
      {!todo.assigned_date && (
        <div style={{ fontSize: 9, color: '#F0C040' }} className="mt-0.5">⬚ 未安排</div>
      )}
      {/* 展开详情 */}
      {expanded && (
        <div className="mt-1.5 pt-1.5 border-t border-cd-border flex flex-col gap-0.5" style={{ fontSize: 8 }}>
          <div className="flex justify-between text-cd-text-tertiary">
            <span>预估番茄</span>
            <span className="tabular-nums">{todo.estimated_pomodoros || 0} 个（{todo.pomodoro_size === 'small' ? '小' : '大'}）</span>
          </div>
          <div className="flex justify-between text-cd-text-tertiary">
            <span>已完成</span>
            <span className="tabular-nums">{todo.progress_min}m / {todo.target_min}m</span>
          </div>
          {todo.due_date && (
            <div className="flex justify-between text-cd-text-tertiary">
              <span>截止</span><span className="tabular-nums">{todo.due_date}</span>
            </div>
          )}
          <div className="flex justify-between text-cd-text-tertiary">
            <span>优先级</span><span>P{todo.priority || 3}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 底部统计块 ──
function StatBlock({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-xs font-semibold tabular-nums" style={{ color }}>{value}</span>
      <span className="text-[9px] text-cd-text-tertiary">{label}</span>
    </div>
  )
}

// ── 月度进度条（年视图用）──
function MonthProgressBar({ month, rate, total, completed }: { month: string; rate: number; total: number; completed: number }) {
  const pct = Math.round(rate * 100)
  return (
    <div className="flex items-center gap-2" style={{ fontSize: 11 }}>
      <span className="text-cd-text-tertiary w-10 shrink-0">{month}</span>
      <div className="flex-1 h-3 rounded-full overflow-hidden" style={{ background: 'var(--cd-bg-tertiary)' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: pct > 0 ? 'var(--cd-green)' : 'transparent', transition: 'width 0.5s' }} />
      </div>
      <span className="w-16 text-right tabular-nums text-cd-text-secondary">{completed}/{total}</span>
      <span className="w-10 text-right tabular-nums" style={{ color: pct >= 60 ? '#10b981' : pct >= 30 ? '#F0C040' : 'var(--cd-text-tertiary)' }}>{pct}%</span>
    </div>
  )
}

export default function WeekPlan() {
  const { success, error } = useToast()
  const [viewMode, setViewMode] = useState<ViewMode>('week')
  const [weekStart, setWeekStart] = useState(getWeekStart())
  const [monthKey, setMonthKey] = useState(getMonthKey())
  const [yearKey, setYearKey] = useState(new Date().getFullYear())
  const [selectedDate, setSelectedDate] = useState(getTodayStr())
  const [weekPlan, setWeekPlan] = useState<WeekPlanData | null>(null)
  const [unassigned, setUnassigned] = useState<TodoV2[]>([])
  const [weekStats, setWeekStats] = useState<WeekPlanStats | null>(null)
  const [monthPlan, setMonthPlan] = useState<MonthPlanData | null>(null)
  const [monthStats, setMonthStats] = useState<MonthPlanStats | null>(null)
  const [yearMonthStats, setYearMonthStats] = useState<(MonthPlanStats | null)[]>([])
  const [yearWeekStats, setYearWeekStats] = useState<Map<string, WeekPlanStats>>(new Map())
  const [yearLoading, setYearLoading] = useState(false)
  const [yearGoal, setYearGoal] = useState('') // 年度目标（本地状态：API 暂无 year 级 meta）
  const [monthGoalDraft, setMonthGoalDraft] = useState('')
  const [dragId, setDragId] = useState<number | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [modalTodo, setModalTodo] = useState<TodoV2 | null>(null)
  const [splitDraft, setSplitDraft] = useState<SplitDraftTask[] | null>(null)
  const [splitLoading, setSplitLoading] = useState(false)
  const [splitGoalTitle, setSplitGoalTitle] = useState('')
  const [splitGoalDesc, setSplitGoalDesc] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedTaskId, setExpandedTaskId] = useState<number | null>(null)

  const loadWeek = useCallback(async (ws: string) => {
    try {
      const [wp, un, st] = await Promise.all([getWeekPlan(ws), getUnassignedTodos(), getWeekPlanStats(ws)])
      setWeekPlan(wp)
      setUnassigned(un.todos)
      setWeekStats(st)
    } catch {
      error('加载周计划失败')
    }
  }, [error])

  const loadMonth = useCallback(async (mk: string) => {
    try {
      const [mp, st] = await Promise.all([getMonthPlan(mk), getMonthPlanStats(mk)])
      setMonthPlan(mp)
      setMonthStats(st)
      setMonthGoalDraft(mp.goal || '')
    } catch {
      error('加载月计划失败')
    }
  }, [error])

  const loadYear = useCallback(async (year: number) => {
    setYearLoading(true)
    try {
      const monthKeys = Array.from({ length: 12 }, (_, i) => `${year}-${String(i + 1).padStart(2, '0')}`)
      const weekStarts = getYearWeekStarts(year)
      const [mStats, wStats] = await Promise.all([
        Promise.all(monthKeys.map(mk => getMonthPlanStats(mk).catch(() => null))),
        Promise.all(weekStarts.map(ws => getWeekPlanStats(ws).catch(() => null))),
      ])
      setYearMonthStats(mStats as (MonthPlanStats | null)[])
      const wMap = new Map<string, WeekPlanStats>()
      weekStarts.forEach((ws, i) => {
        const s = wStats[i]
        if (s) wMap.set(ws, s)
      })
      setYearWeekStats(wMap)
    } catch {
      error('加载年计划失败')
    } finally {
      setYearLoading(false)
    }
  }, [error])

  useEffect(() => {
    if (viewMode === 'month') loadMonth(monthKey)
    else if (viewMode === 'year') loadYear(yearKey)
    else loadWeek(weekStart)
  }, [viewMode, weekStart, monthKey, yearKey, loadWeek, loadMonth, loadYear])

  // ── 导航 ──
  const shiftWeek = (delta: number) => {
    const d = new Date(weekStart + 'T00:00:00')
    d.setDate(d.getDate() + delta * 7)
    setWeekStart(formatLocalDate(d))
  }
  const shiftMonth = (delta: number) => {
    const [y, m] = monthKey.split('-').map(Number)
    setMonthKey(formatLocalMonth(new Date(y, m - 1 + delta, 1)))
  }
  const shiftYear = (delta: number) => setYearKey(y => y + delta)
  const goToday = () => {
    const today = getTodayStr()
    setWeekStart(getWeekStart())
    setMonthKey(getMonthKey())
    setYearKey(new Date().getFullYear())
    setSelectedDate(today)
  }

  // ── 拖拽处理 ──
  const handleDragStart = (todo: TodoV2) => (e: React.DragEvent) => {
    setDragId(todo.id)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(todo.id))
  }
  const handleDragEnd = () => { setDragId(null); setDragOverCol(null) }
  const handleDragOver = (col: string) => (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragOverCol !== col) setDragOverCol(col)
  }
  const handleDragLeave = (col: string) => () => { if (dragOverCol === col) setDragOverCol(null) }
  const handleDropDay = (date: string) => async (e: React.DragEvent) => {
    e.preventDefault()
    setDragOverCol(null)
    const todoId = Number(e.dataTransfer.getData('text/plain'))
    if (!todoId || dragId !== todoId) { setDragId(null); return }
    const existingTasks = weekPlan?.day_tasks?.[date] || []
    const draggedTodo = [...(weekPlan?.day_tasks?.[date] || []), ...unassigned].find(t => t.id === todoId)
    const currentLoad = dayMin(existingTasks)
    const newTaskMin = draggedTodo?.target_min || 25
    if (currentLoad + newTaskMin > DAILY_LIMIT) {
      error(`${fmtDate(date)} 已达 ${currentLoad}分钟负载（上限 ${DAILY_LIMIT}分钟），无法继续分配`)
      setDragId(null)
      return
    }
    try {
      await assignTodo({ todo_id: todoId, assigned_date: date })
      success(`已分配至 ${fmtDate(date)}`)
      loadWeek(weekStart)
    } catch { error('分配失败') }
    setDragId(null)
  }
  const handleDropUnassigned = async (e: React.DragEvent) => {
    e.preventDefault()
    setDragOverCol(null)
    const todoId = Number(e.dataTransfer.getData('text/plain'))
    if (!todoId || dragId !== todoId) { setDragId(null); return }
    try {
      await unassignTodo(todoId)
      success('已移回待分配')
      loadWeek(weekStart)
    } catch { error('取消分配失败') }
    setDragId(null)
  }

  // ── 新建任务 ──
  const handleTaskCreated = (_id: number) => {
    success('任务已创建')
    if (viewMode === 'month') loadMonth(monthKey)
    else if (viewMode === 'year') loadYear(yearKey)
    else loadWeek(weekStart)
  }

  const openDetail = (todo: TodoV2) => setModalTodo(todo)
  const refreshAfterModal = () => {
    if (viewMode === 'month') loadMonth(monthKey)
    else if (viewMode === 'year') loadYear(yearKey)
    else loadWeek(weekStart)
  }
  const startFocus = (id: number) => { window.location.hash = '#/focus?todo_id=' + id }
  const dates = weekPlan?.dates || getWeekDates(weekStart)

  const toggleExpand = (id: number) => setExpandedTaskId(prev => prev === id ? null : id)

  // 月目标保存
  const saveMonthGoal = async () => {
    if (!monthPlan) return
    if ((monthPlan.goal || '') === monthGoalDraft) return
    try {
      await updatePlanMeta({ plan_type: 'month', plan_key: monthKey, goal: monthGoalDraft })
      success('月目标已更新')
      loadMonth(monthKey)
    } catch { error('保存月目标失败') }
  }

  // ── AI 拆解目标 ──
  const handleAutoSplit = async () => {
    if (!splitGoalTitle.trim()) { error('请先输入目标标题'); return }
    setSplitLoading(true)
    try {
      const res = await request('/api/week-plan/auto-split', {
        method: 'POST',
        body: JSON.stringify({ goal_title: splitGoalTitle, goal_description: splitGoalDesc, week_start: weekStart }),
      }, 30000) as { draft_tasks?: SplitDraftTask[]; error?: string }
      if (res.error) { error(res.error); return }
      setSplitDraft((res.draft_tasks || []).map(t => ({ ...t, _checked: true })))
    } catch (e) {
      error(e instanceof Error ? e.message : 'AI 拆解失败')
    } finally {
      setSplitLoading(false)
    }
  }
  const removeSplitTask = (idx: number) => setSplitDraft(prev => prev ? prev.filter((_, i) => i !== idx) : null)
  const toggleSplitTask = (idx: number) => setSplitDraft(prev => prev ? prev.map((t, i) => i === idx ? { ...t, _checked: !t._checked } : t) : null)
  const updateSplitTask = (idx: number, field: keyof SplitDraftTask, value: string | number) => setSplitDraft(prev => prev ? prev.map((t, i) => i === idx ? { ...t, [field]: value } : t) : null)
  const confirmSplit = async () => {
    if (!splitDraft) return
    const checked = splitDraft.filter(t => t._checked)
    if (checked.length === 0) { error('请至少选择一个任务'); return }
    const weekDates = getWeekDates(weekStart)
    let created = 0
    try {
      // 1. 先创建父任务（周级），形成真实父子关系（修复原本创建平级 day 任务的 bug）
      const totalMin = checked.reduce((s, t) => s + (Number(t.target_min) || 25), 0)
      const parent = await createTodo({
        title: splitGoalTitle.trim(), category: checked[0]?.category || '开发',
        target_min: totalMin, task_level: 'week', week_start: weekStart,
      })
      // 2. 创建子任务时设置 parent_id，task_level='day'
      for (const t of checked) {
        try {
          const dayIdx = (t.day || 1) - 1
          const assignedDate = dayIdx >= 0 && dayIdx < 5 ? weekDates[dayIdx] : ''
          await createTodo({
            title: t.title, category: t.category || '开发', target_min: Number(t.target_min) || 25,
            task_level: 'day', assigned_date: assignedDate || undefined, week_start: weekStart,
            parent_id: parent.id,
          })
          created++
        } catch { /* 单条失败继续 */ }
      }
      success(`已创建 1 个父任务 + ${created} 个子任务`)
    } catch (e) {
      // 父任务创建失败则回退为原逻辑（平级创建）
      for (const t of checked) {
        try {
          const dayIdx = (t.day || 1) - 1
          const assignedDate = dayIdx >= 0 && dayIdx < 5 ? weekDates[dayIdx] : ''
          await createTodo({
            title: t.title, category: t.category || '开发', target_min: Number(t.target_min) || 25,
            task_level: 'day', assigned_date: assignedDate || undefined, week_start: weekStart,
          })
          created++
        } catch { /* 单条失败继续 */ }
      }
      success(`已创建 ${created} 个任务（父子关系未建立）`)
    }
    setSplitDraft(null); setSplitGoalTitle(''); setSplitGoalDesc('')
    if (viewMode === 'month') loadMonth(monthKey); else loadWeek(weekStart)
  }

  // ── 当前视图时间范围标签 ──
  const rangeLabel = useMemo(() => {
    if (viewMode === 'year') return `${yearKey}年`
    if (viewMode === 'month') {
      const [y, m] = monthKey.split('-').map(Number)
      return `${y}年${m}月`
    }
    if (viewMode === 'week') {
      const [y, m] = weekStart.split('-').map(Number)
      const wk = getISOWeek(weekStart)
      const end = dates[6] || weekStart
      return `${y}年${m}月 第${wk}周 · ${fmtDate(weekStart)}-${fmtDate(end)}`
    }
    // day
    const d = new Date(selectedDate + 'T00:00:00')
    const wd = (d.getDay() + 6) % 7
    return `${fmtDate(selectedDate)} ${WEEKDAY_LABELS[wd]}`
  }, [viewMode, yearKey, monthKey, weekStart, selectedDate, dates])

  // ── 底部数据条（Recharts 柱状图 + 统计）──
  function renderBottomBar() {
    if (!weekStats) return null
    const chartData = weekStats.daily_focus.map(d => ({ date: d.date, focus: d.focus_min, label: fmtDate(d.date).split('/')[1] }))
    return (
      <div className="flex items-center gap-4 px-4 border-t border-cd-border" style={{ height: 56, background: 'var(--cd-card)' }}>
        <div style={{ width: 120, height: 40 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <XAxis dataKey="label" hide />
              <Tooltip
                cursor={{ fill: 'transparent' }}
                contentStyle={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderRadius: 6, fontSize: 11, color: 'var(--cd-text)' }}
                labelFormatter={(_, p) => p && p[0] ? fmtDate((p[0].payload as { date: string }).date) : ''}
                formatter={(v: number) => [`${v}min`, '专注']}
              />
              <Bar dataKey="focus" radius={[2, 2, 0, 0]}>
                {chartData.map(d => (
                  <RechartsCell key={d.date} fill={d.date === getTodayStr() ? '#7B68EE' : '#7B68EE66'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1" />
        <StatBlock label="完成率" value={`${Math.round(weekStats.completion_rate * 100)}%`} color="#10b981" />
        <StatBlock label="深度工作" value={`${Math.round(weekStats.deep_focus_min)}m`} color="#7B68EE" />
        <StatBlock label="中断次数" value={weekStats.interrupt_count} color="#ef4444" />
        <StatBlock label="连续天数" value={`${weekStats.streak_days}d`} color="#F0C040" />
      </div>
    )
  }

  // ── 年视图 ──
  function renderYearView() {
    const monthLabels = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
    // 构建日期→专注分钟 映射
    const dateFocusMap = new Map<string, number>()
    yearWeekStats.forEach((st, _ws) => {
      st.daily_focus.forEach(d => dateFocusMap.set(d.date, d.focus_min))
    })
    const weekStarts = getYearWeekStarts(yearKey)
    // 年度汇总
    const yearTotal = yearMonthStats.reduce((s, m) => s + (m?.total_focus_min || 0), 0)
    const yearCompleted = yearMonthStats.reduce((s, m) => s + (m?.completed_tasks || 0), 0)
    const yearTotalTasks = yearMonthStats.reduce((s, m) => s + (m?.total_tasks || 0), 0)
    const yearRate = yearTotalTasks > 0 ? yearCompleted / yearTotalTasks : 0

    return (
      <div className="p-4 overflow-auto h-full">
        {/* 年度目标卡片 */}
        <div className="mb-4 rounded-lg p-4" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
          <div className="flex items-center gap-2 mb-2">
            <Target size={16} className="text-cd-green" />
            <h2 className="text-sm font-semibold text-cd-text">{yearKey} 年度目标</h2>
            <span className="text-[10px] text-cd-text-tertiary ml-auto">本地存储（API 暂无 year 级 meta）</span>
          </div>
          <textarea
            value={yearGoal}
            onChange={e => setYearGoal(e.target.value)}
            placeholder="设定本年度核心目标，例如：完成产品 3.0 大版本发布、阅读 24 本书、累计专注 1000 小时..."
            rows={2}
            className="w-full px-3 py-2 rounded text-sm border border-cd-border resize-none"
            style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
          />
          <div className="flex gap-4 mt-3 text-xs">
            <span className="text-cd-text-secondary">累计专注 <span className="text-cd-green font-semibold tabular-nums">{Math.round(yearTotal)}m</span></span>
            <span className="text-cd-text-secondary">完成任务 <span className="text-cd-accent font-semibold tabular-nums">{yearCompleted}/{yearTotalTasks}</span></span>
            <span className="text-cd-text-secondary">完成率 <span style={{ color: '#10b981' }} className="font-semibold tabular-nums">{Math.round(yearRate * 100)}%</span></span>
          </div>
        </div>

        {/* 12 个月度进度条 */}
        <div className="mb-4 rounded-lg p-4" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
          <div className="flex items-center gap-2 mb-3">
            <Layers size={14} className="text-cd-accent" />
            <h3 className="text-sm font-semibold text-cd-text">月度完成率</h3>
          </div>
          {yearLoading ? (
            <div className="text-center text-cd-text-tertiary text-xs py-4">加载中...</div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {monthLabels.map((ml, i) => {
                const st = yearMonthStats[i]
                return (
                  <MonthProgressBar
                    key={ml}
                    month={ml}
                    rate={st?.completion_rate || 0}
                    total={st?.total_tasks || 0}
                    completed={st?.completed_tasks || 0}
                  />
                )
              })}
            </div>
          )}
        </div>

        {/* 全年热力图（GitHub 风格 53×7） */}
        <div className="rounded-lg p-4" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
          <div className="flex items-center gap-2 mb-3">
            <Flame size={14} className="text-cd-green" />
            <h3 className="text-sm font-semibold text-cd-text">全年专注热力图</h3>
            <div className="flex items-center gap-1 ml-auto" style={{ fontSize: 9 }}>
              <span className="text-cd-text-tertiary">少</span>
              {HEAT_COLORS.map(c => <span key={c} style={{ width: 10, height: 10, background: c, borderRadius: 2, display: 'inline-block' }} />)}
              <span className="text-cd-text-tertiary">多</span>
            </div>
          </div>
          <div className="flex gap-[2px] overflow-x-auto scrollbar-thin pb-1">
            {weekStarts.map((ws, col) => (
              <div key={col} className="flex flex-col gap-[2px]">
                {Array.from({ length: 7 }).map((_, row) => {
                  const d = new Date(ws + 'T00:00:00')
                  d.setDate(d.getDate() + row)
                  const ds = formatLocalDate(d)
                  const inYear = d.getFullYear() === yearKey
                  const min = dateFocusMap.get(ds) || 0
                  return (
                    <div
                      key={row}
                      title={`${ds}${min > 0 ? ` · ${min}min` : ''}`}
                      style={{
                        width: 10, height: 10, borderRadius: 2,
                        background: inYear ? heatColor(min) : 'transparent',
                        border: ds === getTodayStr() ? '1px solid #7B68EE' : 'none',
                      }}
                    />
                  )
                })}
              </div>
            ))}
          </div>
          <div className="flex gap-3 mt-2 text-[9px] text-cd-text-tertiary">
            <span>周一</span><span>·</span><span>每格 = 一天专注分钟数</span>
          </div>
        </div>
      </div>
    )
  }

  // ── 月视图（增强：月历热力 + 右侧环 + 月目标）──
  function renderMonthView() {
    if (!monthPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    const [y, m] = monthKey.split('-').map(Number)
    const firstDay = new Date(y, m - 1, 1)
    const startWeekday = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1
    const daysInMonth = new Date(y, m, 0).getDate()
    const totalCells = Math.ceil((startWeekday + daysInMonth) / 7) * 7
    // 扁平化所有任务
    const allTasks: TodoV2[] = []
    monthPlan.month_tasks.forEach(mt => { allTasks.push(mt, ...mt.children) })
    // 月完成率（环形）
    const mRate = monthStats?.completion_rate || 0
    const ringR = 34, ringC = 2 * Math.PI * ringR
    const ringOff = ringC - mRate * ringC

    return (
      <div className="flex h-full overflow-hidden">
        {/* 月历主区 */}
        <div className="flex-1 p-4 overflow-auto">
          <div className="mb-3 flex items-center gap-3">
            <CalendarDays size={16} className="text-cd-accent" />
            <h2 className="text-sm font-semibold text-cd-text">{monthPlan.title || `${monthKey} 月计划`}</h2>
            {monthPlan.goal && <span className="text-xs text-cd-text-tertiary truncate">🎯 {monthPlan.goal}</span>}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {WEEKDAY_LABELS.map(w => (
              <div key={w} className="text-center text-[10px] text-cd-text-tertiary py-1">{w}</div>
            ))}
            {Array.from({ length: totalCells }).map((_, i) => {
              const dayNum = i - startWeekday + 1
              if (dayNum < 1 || dayNum > daysInMonth) {
                return <div key={i} style={{ background: 'var(--cd-bg-tertiary)', borderRadius: 4, minHeight: 64 }} />
              }
              const date = `${monthKey}-${String(dayNum).padStart(2, '0')}`
              const dayTasks = allTasks.filter(t => t.assigned_date === date)
              const doneCnt = dayTasks.filter(t => t.status === 'completed').length
              const rate = dayTasks.length > 0 ? doneCnt / dayTasks.length : 0
              const isTodayCell = date === getTodayStr()
              return (
                <div key={i}
                  onClick={() => { setSelectedDate(date); setViewMode('day'); setWeekStart(getWeekStart(new Date(date + 'T00:00:00'))) }}
                  className="rounded p-1 cursor-pointer hover:brightness-125 transition flex flex-col"
                  style={{
                    background: monthHeatColor(rate),
                    border: `1px solid ${isTodayCell ? '#7B68EE' : 'var(--cd-border)'}`,
                    minHeight: 64,
                    opacity: dayTasks.length === 0 ? 0.7 : 1,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px]" style={{ color: isTodayCell ? '#937CFF' : 'var(--cd-text-secondary)', fontWeight: isTodayCell ? 700 : 400 }}>{dayNum}</span>
                    {dayTasks.length > 0 && (
                      <span className="text-[8px] tabular-nums text-cd-text">{doneCnt}/{dayTasks.length}</span>
                    )}
                  </div>
                  <div className="flex flex-col gap-0.5 mt-0.5 overflow-hidden">
                    {dayTasks.slice(0, 2).map(t => (
                      <div key={t.id} className="text-[8px] truncate rounded px-1"
                        style={{ background: 'rgba(0,0,0,0.25)', borderLeft: `2px solid ${CATEGORY_COLORS[t.category] || '#9999B0'}`, color: 'var(--cd-text)', textDecoration: t.status === 'completed' ? 'line-through' : 'none' }}>
                        {t.title}
                      </div>
                    ))}
                    {dayTasks.length > 2 && <span className="text-[8px] text-cd-text-tertiary">+{dayTasks.length - 2}</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* 右侧侧栏：月目标进度环 + 统计 */}
        <div className="overflow-y-auto scrollbar-thin p-4 flex flex-col gap-3" style={{ width: 240, background: 'var(--cd-bg-secondary)', borderLeft: '1px solid var(--cd-border)' }}>
          <h3 className="text-xs font-semibold text-cd-text">月度概览</h3>
          {/* 环形进度 */}
          <div className="flex flex-col items-center py-2">
            <svg width={84} height={84}>
              <circle cx={42} cy={42} r={ringR} fill="none" stroke="var(--cd-bg-tertiary)" strokeWidth={7} />
              <circle cx={42} cy={42} r={ringR} fill="none" stroke="var(--cd-green)" strokeWidth={7}
                strokeDasharray={ringC} strokeDashoffset={ringOff} strokeLinecap="round"
                transform="rotate(-90 42 42)" style={{ transition: 'stroke-dashoffset 0.6s' }} />
              <text x={42} y={40} textAnchor="middle" style={{ fontSize: 16, fontWeight: 700, fill: 'var(--cd-text)' }}>
                {Math.round(mRate * 100)}%
              </text>
              <text x={42} y={54} textAnchor="middle" style={{ fontSize: 8, fill: 'var(--cd-text-tertiary)' }}>完成率</text>
            </svg>
          </div>
          {/* 统计 */}
          {monthStats && (
            <div className="flex flex-col gap-1.5 text-xs">
              <div className="flex justify-between"><span className="text-cd-text-tertiary">任务总数</span><span className="tabular-nums text-cd-text">{monthStats.total_tasks}</span></div>
              <div className="flex justify-between"><span className="text-cd-text-tertiary">已完成</span><span className="tabular-nums text-green-400">{monthStats.completed_tasks}</span></div>
              <div className="flex justify-between"><span className="text-cd-text-tertiary">深度专注</span><span className="tabular-nums text-cd-accent">{Math.round(monthStats.deep_focus_min)}m</span></div>
              <div className="flex justify-between"><span className="text-cd-text-tertiary">中断次数</span><span className="tabular-nums text-red-400">{monthStats.interrupt_count}</span></div>
              <div className="flex justify-between"><span className="text-cd-text-tertiary">总专注</span><span className="tabular-nums text-cd-text">{Math.round(monthStats.total_focus_min)}m</span></div>
            </div>
          )}
          {/* 月目标编辑 */}
          <div className="mt-2">
            <label className="text-[10px] text-cd-text-tertiary block mb-1">月目标（可编辑，存 plan_meta）</label>
            <textarea
              value={monthGoalDraft}
              onChange={e => setMonthGoalDraft(e.target.value)}
              onBlur={saveMonthGoal}
              placeholder="本月要达成的核心目标..."
              rows={3}
              className="w-full px-2 py-1.5 rounded text-xs border border-cd-border resize-none"
              style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
            />
          </div>
        </div>
      </div>
    )
  }

  // ── 周视图（GoalDay 式：左 280 待分配 + 右 7 列）──
  function renderWeekView() {
    if (!weekPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    const filteredUnassigned = searchQuery.trim()
      ? unassigned.filter(t => t.title.toLowerCase().includes(searchQuery.toLowerCase()) || t.category.includes(searchQuery))
      : unassigned
    return (
      <div className="flex h-full">
        {/* 左侧：待分配清单（280px） */}
        <div
          onDragOver={handleDragOver('unassigned')}
          onDragLeave={handleDragLeave('unassigned')}
          onDrop={handleDropUnassigned}
          className="flex flex-col overflow-hidden"
          style={{
            width: 280, background: 'var(--cd-bg-tertiary)',
            border: '1.5px dashed',
            borderColor: dragOverCol === 'unassigned' ? '#7B68EE' : '#F0C04066',
            transition: 'border-color 0.15s',
          }}
        >
          <div className="px-3 py-2 sticky top-0 z-10" style={{ background: 'var(--cd-bg-tertiary)', borderBottom: '1px solid var(--cd-border)' }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold" style={{ color: '#F0C040' }}>待分配清单</span>
                <span className="text-[10px] px-1.5 rounded-full tabular-nums" style={{ background: '#F0C04022', color: '#F0C040' }}>{unassigned.length}</span>
              </div>
            </div>
            {/* 搜索过滤 */}
            <div className="relative mt-2">
              <Search size={11} className="absolute left-2 top-1/2 -translate-y-1/2 text-cd-text-tertiary" />
              <input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="搜索任务..."
                className="w-full pl-6 pr-2 py-1 rounded text-[11px] border border-cd-border"
                style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto scrollbar-thin flex flex-col gap-1.5 px-2 py-2">
            {filteredUnassigned.length === 0 && (
              <div className="text-[10px] text-cd-text-tertiary text-center py-4 opacity-60">
                {unassigned.length === 0 ? '无待分配任务' : '无匹配任务'}
              </div>
            )}
            {filteredUnassigned.map(t => (
              <TaskCard key={t.id} todo={t}
                expanded={expandedTaskId === t.id}
                onToggleExpand={() => toggleExpand(t.id)}
                onClick={() => openDetail(t)}
                onDragStart={handleDragStart(t)} onDragEnd={handleDragEnd} />
            ))}
          </div>
          {/* 新建任务按钮 */}
          <div className="p-2 border-t border-cd-border">
            <button
              onClick={() => setShowCreateModal(true)}
              className="w-full flex items-center justify-center gap-1 py-1.5 text-xs rounded-md transition hover:brightness-125"
              style={{ background: 'var(--cd-green)', color: '#fff' }}
            >
              <Plus size={12} /> 新建任务
            </button>
          </div>
        </div>

        {/* 右侧：7 天周计划拖拽区 */}
        <div className="flex-1 flex overflow-hidden">
          {dates.map((date, idx) => {
            const tasks = weekPlan.day_tasks[date] || []
            const totalMin = dayMin(tasks)
            const full = totalMin >= DAILY_LIMIT
            const overLimit = totalMin > DAILY_LIMIT
            const isTodayCol = date === getTodayStr()
            const weekend = isWeekend(date)
            return (
              <div key={date}
                onDragOver={full ? undefined : handleDragOver(date)}
                onDragLeave={handleDragLeave(date)}
                onDrop={full ? undefined : handleDropDay(date)}
                className="flex-1 flex flex-col overflow-hidden"
                style={{
                  background: 'var(--cd-card)',
                  border: `1px solid ${isTodayCol ? '#7B68EE' : dragOverCol === date ? '#7B68EE' : 'var(--cd-border)'}`,
                  opacity: weekend ? 0.7 : full ? 0.5 : 1,
                  minWidth: 0,
                  transition: 'border-color 0.15s, opacity 0.15s',
                }}
              >
                {/* 日期头 */}
                <div className="px-2 py-1.5 flex items-center justify-between" style={{ borderBottom: '1px solid var(--cd-border)' }}>
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-medium text-cd-text">{WEEKDAY_LABELS[idx]}</span>
                    {weekend && <span style={{ fontSize: 11 }}>😴</span>}
                    {isTodayCol && <span className="text-[9px] px-1 rounded" style={{ background: '#7B68EE33', color: '#937CFF' }}>今日</span>}
                    {full && <span className="text-[9px] px-1 rounded" style={{ background: '#ef444422', color: '#ef4444' }} title="满负荷">满</span>}
                  </div>
                  <span className="text-[9px] text-cd-text-tertiary tabular-nums">{fmtDate(date)}</span>
                </div>
                {/* 今日进度条 */}
                {isTodayCol && weekStats && (() => {
                  const todayFocus = weekStats.daily_focus.find(d => d.date === date)?.focus_min || 0
                  const pct = Math.min(100, (todayFocus / 240) * 100)
                  return (
                    <div className="h-1 mx-2 rounded-full overflow-hidden" style={{ background: 'var(--cd-bg-tertiary)' }}>
                      <div style={{ width: `${pct}%`, height: '100%', background: '#7B68EE', transition: 'width 0.5s' }} />
                    </div>
                  )
                })()}
                {/* 任务列表 */}
                <div className="flex-1 overflow-y-auto scrollbar-thin px-1.5 py-1.5 flex flex-col gap-1">
                  {tasks.length === 0 && <div className="text-[9px] text-cd-text-tertiary text-center py-2 opacity-50">{full ? '已满' : '空'}</div>}
                  {tasks.map(t => (
                    <div key={t.id} style={{ opacity: dragId === t.id ? 0.5 : 1, transition: 'opacity 0.15s' }}>
                      <TaskCard todo={t} compact
                        expanded={expandedTaskId === t.id}
                        onToggleExpand={() => toggleExpand(t.id)}
                        onClick={() => openDetail(t)}
                        onDragStart={handleDragStart(t)} onDragEnd={handleDragEnd} />
                    </div>
                  ))}
                </div>
                {/* 当日负载 + 开始专注 */}
                <div className="px-2 py-1.5 border-t border-cd-border flex flex-col gap-1">
                  <div className="flex items-center justify-between text-[9px]">
                    <span className="text-cd-text-tertiary">当日负载</span>
                    <span className="tabular-nums" style={{ color: overLimit ? '#ef4444' : full ? '#F0C040' : 'var(--cd-text-secondary)' }}>
                      {totalMin}/{DAILY_LIMIT}m
                      {overLimit && <span title={`${totalMin}min 超载`}> ⚠</span>}
                    </span>
                  </div>
                  {tasks.some(t => t.status !== 'completed') && (
                    <button
                      onClick={() => { const t = tasks.find(t => t.status !== 'completed'); if (t) startFocus(t.id) }}
                      className="flex items-center justify-center gap-1 py-1 text-[10px] rounded transition hover:brightness-125"
                      style={{ background: '#7B68EE22', color: '#937CFF', border: '1px solid #7B68EE55' }}
                    >
                      <Play size={9} /> 开始专注
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // ── 日视图（时间轴样式）──
  function renderDayView() {
    if (!weekPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    const tasks = (weekPlan.day_tasks[selectedDate] || []).slice().sort((a, b) => (a.priority || 3) - (b.priority || 3) || a.id - b.id)
    const isToday = selectedDate === getTodayStr()
    const shiftDay = (delta: number) => {
      const d = new Date(selectedDate + 'T00:00:00')
      d.setDate(d.getDate() + delta)
      const ns = formatLocalDate(d)
      setSelectedDate(ns)
      const ws = getWeekStart(new Date(ns + 'T00:00:00'))
      if (ws !== weekStart) setWeekStart(ws)
    }
    // 计算建议时段（从 09:00 累计，每番茄 = work 分钟）
    let acc = 9 * 60
    const slots = tasks.map(t => {
      const work = POMODORO_SIZES[t.pomodoro_size]?.work || 25
      const dur = (t.estimated_pomodoros || 1) * work
      const start = acc
      const end = acc + dur
      acc = end
      return { t, start, end }
    })
    const d = new Date(selectedDate + 'T00:00:00')
    const wd = (d.getDay() + 6) % 7
    return (
      <div className="p-4 overflow-auto h-full">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-cd-text">{fmtDate(selectedDate)} {WEEKDAY_LABELS[wd]}</h2>
            <span className="text-xs text-cd-text-tertiary">{tasks.length} 个任务 · 总计 {dayMin(tasks)}m</span>
          </div>
          {isToday && tasks.some(t => t.status !== 'completed') && (
            <button
              onClick={() => { const t = tasks.find(t => t.status !== 'completed'); if (t) startFocus(t.id) }}
              className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition"
            >
              <Play size={12} /> 开始专注
            </button>
          )}
        </div>
        {/* 日期导航 */}
        <div className="flex items-center gap-2 mb-4">
          <button onClick={() => shiftDay(-1)} className="p-1 rounded hover:bg-cd-hover text-cd-text-secondary"><ChevronLeft size={14} /></button>
          <input type="date" value={selectedDate} onChange={e => { setSelectedDate(e.target.value); const ws = getWeekStart(new Date(e.target.value)); if (ws !== weekStart) setWeekStart(ws) }}
            className="bg-cd-bg-input border border-cd-border rounded px-2 py-1 text-xs text-cd-text" />
          <button onClick={() => shiftDay(1)} className="p-1 rounded hover:bg-cd-hover text-cd-text-secondary"><ChevronRight size={14} /></button>
          <button onClick={goToday} className="px-2 py-1 text-xs rounded-lg bg-cd-bg-input text-cd-text-secondary hover:bg-cd-hover transition ml-1">今天</button>
        </div>
        {/* 时间轴任务列表 */}
        <div className="space-y-1 max-w-2xl">
          {tasks.length === 0 && (
            <div className="text-center py-8 text-cd-text-tertiary text-sm">
              <Target size={32} className="mx-auto mb-2 opacity-30" />
              当日无任务
            </div>
          )}
          {slots.map(({ t, start, end }) => {
            const catColor = CATEGORY_COLORS[t.category] || '#9999B0'
            const isDone = t.status === 'completed'
            const pct = t.target_min > 0 ? (t.progress_min / t.target_min) * 100 : 0
            const work = POMODORO_SIZES[t.pomodoro_size]?.work || 25
            return (
              <div key={t.id} className="flex items-stretch gap-2 group">
                {/* 时间标记 */}
                <div className="flex flex-col items-end justify-center w-14 shrink-0">
                  <span className="text-[10px] tabular-nums text-cd-text-secondary">{fmtHM(start)}</span>
                  <span className="text-[9px] tabular-nums text-cd-text-tertiary">{fmtHM(end)}</span>
                </div>
                {/* 时间轴线 */}
                <div className="relative flex flex-col items-center">
                  <div className="rounded-full mt-1.5" style={{ width: 8, height: 8, background: catColor, opacity: isDone ? 0.5 : 1 }} />
                  <div className="flex-1 w-px" style={{ background: 'var(--cd-border)' }} />
                </div>
                {/* 任务卡片 */}
                <div
                  draggable
                  onDragStart={handleDragStart(t)}
                  onDragEnd={handleDragEnd}
                  onClick={() => openDetail(t)}
                  className="flex-1 rounded-md cursor-grab active:cursor-grabbing transition hover:brightness-110 mb-1"
                  style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderLeft: `3px solid ${catColor}`, padding: '6px 10px', opacity: dragId === t.id ? 0.5 : 1 }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-cd-text" style={{ textDecoration: isDone ? 'line-through' : 'none', opacity: isDone ? 0.6 : 1 }}>{t.title}</span>
                      {isDone && <span className="text-[9px] text-green-400">✓ 已完成</span>}
                      {t.status === 'in_progress' && <span className="text-[9px] text-cd-accent">进行中</span>}
                    </div>
                    <ExternalLink size={11} className="opacity-0 group-hover:opacity-60 text-cd-text-tertiary" />
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-[10px] text-cd-text-tertiary">
                    <span style={{ color: catColor }}>● {t.category}</span>
                    <span className="flex items-center gap-1"><Clock size={9} /> {t.estimated_pomodoros || 0}番茄 · {work}m</span>
                    <span className="flex items-center gap-1 tabular-nums">
                      <ProgressRing pct={pct} size={11} stroke={1.5} color={isDone ? '#10b981' : catColor} />
                      {t.progress_min}/{t.target_min}m
                    </span>
                    {/* 番茄进度小方块 */}
                    <span className="flex items-center gap-0.5">
                      {Array.from({ length: Math.max(1, t.estimated_pomodoros || 1) }).map((_, i) => (
                        <span key={i} style={{ width: 6, height: 6, borderRadius: 1, background: i < (t.pomodoro_count || 0) ? '#ef4444' : 'var(--cd-bg-tertiary)' }} />
                      ))}
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        {/* 添加任务 */}
        <button
          onClick={() => setShowCreateModal(true)}
          className="mt-4 flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-cd-green/20 text-cd-green border border-cd-green/30 hover:bg-cd-green/30 transition"
        >
          <Plus size={12} /> 添加任务
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* ── 顶部导航栏 ── */}
      <div className="px-4 pt-2.5 border-b border-cd-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Calendar size={18} className="text-cd-accent" />
            {/* 四级视图 Tab */}
            <div className="flex bg-cd-bg-input rounded-lg p-0.5">
              {VIEW_TABS.map(v => (
                <button key={v.key} onClick={() => setViewMode(v.key)}
                  className={`px-2.5 py-1 text-xs rounded-md transition ${viewMode === v.key ? 'bg-cd-accent/20 text-cd-accent' : 'text-cd-text-secondary hover:text-cd-text'}`}>
                  {v.emoji} {v.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => viewMode === 'year' ? shiftYear(-1) : viewMode === 'month' ? shiftMonth(-1) : shiftWeek(-1)}
              className="p-1.5 rounded-lg hover:bg-cd-hover text-cd-text-secondary transition">
              <ChevronLeft size={16} />
            </button>
            <span className="text-xs text-cd-text-secondary min-w-[160px] text-center tabular-nums">{rangeLabel}</span>
            <button onClick={() => viewMode === 'year' ? shiftYear(1) : viewMode === 'month' ? shiftMonth(1) : shiftWeek(1)}
              className="p-1.5 rounded-lg hover:bg-cd-hover text-cd-text-secondary transition">
              <ChevronRight size={16} />
            </button>
            <button onClick={goToday}
              className="px-2 py-1 text-xs rounded-lg bg-cd-bg-input text-cd-text-secondary hover:bg-cd-hover transition">
              今天
            </button>
            <button onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1 px-3 py-1 text-xs rounded-lg bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition">
              <Plus size={12} /> 新建
            </button>
            <button
              onClick={() => setSplitDraft([])}
              className="flex items-center gap-1 px-3 py-1 text-xs rounded-lg bg-cd-purple/20 text-cd-purple border border-cd-purple/30 hover:bg-cd-purple/30 transition"
              title="AI 拆解月目标为周待办草案"
            >
              🤖 AI 拆解
            </button>
          </div>
        </div>
        {/* 当前层级时间范围副标题 */}
        <div className="text-[10px] text-cd-text-tertiary py-1">
          {viewMode === 'year' && `📅 年计划 · ${yearKey} 年度总览`}
          {viewMode === 'month' && `📆 月计划 · ${monthKey} 月历与目标`}
          {viewMode === 'week' && `📋 周计划 · ${rangeLabel}`}
          {viewMode === 'day' && `✅ 日计划 · ${rangeLabel}`}
        </div>
      </div>

      {/* 主视图区 */}
      <div className="flex-1 overflow-hidden">
        {viewMode === 'year' && renderYearView()}
        {viewMode === 'month' && renderMonthView()}
        {viewMode === 'week' && renderWeekView()}
        {viewMode === 'day' && renderDayView()}
      </div>

      {/* 底部数据条（仅周/日视图显示）*/}
      {viewMode !== 'month' && viewMode !== 'year' && renderBottomBar()}

      {/* 任务详情浮层 */}
      <TaskDetailModal todo={modalTodo} onClose={() => setModalTodo(null)} onUpdate={refreshAfterModal} />

      {/* 统一任务创建弹窗 */}
      <TaskCreateModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleTaskCreated}
        defaults={{ week_start: weekStart, assigned_date: viewMode === 'day' ? selectedDate : '' }}
      />

      {/* AI 拆解草案弹窗 */}
      {splitDraft !== null && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="rounded-lg max-w-2xl w-full max-h-[85vh] overflow-auto flex flex-col" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-cd-border">
              <h3 className="text-sm font-semibold text-cd-text">🤖 AI 拆解目标为周待办</h3>
              <button onClick={() => { setSplitDraft(null); setSplitGoalTitle(''); setSplitGoalDesc('') }} className="text-cd-text-tertiary hover:text-cd-text">
                <X size={16} />
              </button>
            </div>

            {/* 目标输入区（草案为空时显示） */}
            {splitDraft.length === 0 && (
              <div className="p-5 space-y-3">
                <div>
                  <label className="text-xs text-cd-text-tertiary block mb-1">目标标题 *</label>
                  <input
                    value={splitGoalTitle}
                    onChange={e => setSplitGoalTitle(e.target.value)}
                    placeholder="例如：完成 v3.1.0 版本开发"
                    className="w-full px-3 py-2 rounded text-sm border border-cd-border"
                    style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                  />
                </div>
                <div>
                  <label className="text-xs text-cd-text-tertiary block mb-1">目标描述（可选）</label>
                  <textarea
                    value={splitGoalDesc}
                    onChange={e => setSplitGoalDesc(e.target.value)}
                    placeholder="补充目标细节、验收标准等"
                    rows={3}
                    className="w-full px-3 py-2 rounded text-sm border border-cd-border resize-none"
                    style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                  />
                </div>
                <div className="text-xs text-cd-text-tertiary">周开始：{weekStart}</div>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => { setSplitDraft(null); setSplitGoalTitle(''); setSplitGoalDesc('') }}
                    className="px-4 py-2 text-xs text-cd-text-tertiary hover:text-cd-text"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleAutoSplit}
                    disabled={splitLoading || !splitGoalTitle.trim()}
                    className="px-4 py-2 text-xs rounded text-white disabled:opacity-50"
                    style={{ background: 'var(--cd-purple)' }}
                  >
                    {splitLoading ? '🤖 拆解中...' : '🤖 开始拆解'}
                  </button>
                </div>
              </div>
            )}

            {/* 草案列表（有任务时显示） */}
            {splitDraft.length > 0 && (
              <>
                <div className="px-5 py-2 text-xs text-cd-text-tertiary border-b border-cd-border">
                  共 {splitDraft.length} 个草案任务，请勾选确认（可编辑标题/分钟数，或删除不需要的项）
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-2">
                  {splitDraft.map((task, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 rounded" style={{ background: 'var(--cd-bg-tertiary)' }}>
                      <input
                        type="checkbox"
                        checked={task._checked !== false}
                        onChange={() => toggleSplitTask(i)}
                        className="rounded"
                      />
                      <input
                        value={task.title}
                        onChange={e => updateSplitTask(i, 'title', e.target.value)}
                        className="flex-1 px-2 py-1 rounded text-sm border border-cd-border"
                        style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                      />
                      <input
                        type="number"
                        value={task.target_min}
                        onChange={e => updateSplitTask(i, 'target_min', Number(e.target.value))}
                        className="w-16 px-2 py-1 rounded text-xs text-center border border-cd-border"
                        style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                        title="预计分钟数"
                      />
                      <span className="text-[10px] text-cd-text-tertiary">min</span>
                      <select
                        value={task.day || 1}
                        onChange={e => updateSplitTask(i, 'day', Number(e.target.value))}
                        className="px-1 py-1 rounded text-[10px] border border-cd-border"
                        style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                      >
                        {[1, 2, 3, 4, 5].map(d => <option key={d} value={d}>周{['一', '二', '三', '四', '五'][d - 1]}</option>)}
                      </select>
                      <button
                        onClick={() => removeSplitTask(i)}
                        className="text-red-400 hover:text-red-300 px-1"
                        title="删除"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="flex justify-end gap-3 px-5 py-3 border-t border-cd-border">
                  <button
                    onClick={() => { setSplitDraft([]); setSplitGoalTitle(''); setSplitGoalDesc('') }}
                    className="px-4 py-2 text-xs text-cd-text-tertiary hover:text-cd-text"
                  >
                    取消
                  </button>
                  <button
                    onClick={confirmSplit}
                    className="px-4 py-2 text-xs rounded text-white"
                    style={{ background: 'var(--cd-green)' }}
                  >
                    确认创建（{splitDraft.filter(t => t._checked !== false).length}）
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
