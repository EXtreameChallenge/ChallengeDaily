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
  assignTodo, unassignTodo, createTodo, request, updatePlanMeta, updateTaskTime,
  getWeekStart, getWeekDates, getMonthKey, getGoals,
  CATEGORY_COLORS, POMODORO_SIZES,
  type TodoV2, type WeekPlanData, type WeekPlanStats, type MonthPlanData, type MonthPlanStats,
} from '../api/client'
import { useToast } from '../components/Toast'
import TaskDetailModal from '../components/TaskDetailModal'
import TaskCreateModal from '../components/TaskCreateModal'
import GanttBar from '../components/GanttBar'
import TimeAxis from '../components/TimeAxis'

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
  const pct = Math.round(rate)
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
  const [yearGoals, setYearGoals] = useState<any[]>([])

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
      const [mStats, wStats, goalsRes] = await Promise.all([
        Promise.all(monthKeys.map(mk => getMonthPlanStats(mk).catch(() => null))),
        Promise.all(weekStarts.map(ws => getWeekPlanStats(ws).catch(() => null))),
        getGoals('active').catch(() => ({ goals: [] })),
      ])
      setYearMonthStats(mStats as (MonthPlanStats | null)[])
      const wMap = new Map<string, WeekPlanStats>()
      weekStarts.forEach((ws, i) => {
        const s = wStats[i]
        if (s) wMap.set(ws, s)
      })
      setYearWeekStats(wMap)
      // 过滤出跨越该年的目标
      setYearGoals((goalsRes.goals || []).filter((g: any) => {
        const sy = g.start_date ? new Date(g.start_date).getFullYear() : year
        const ey = g.target_date ? new Date(g.target_date).getFullYear() : year
        return sy <= year && ey >= year
      }))
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
        <StatBlock label="完成率" value={`${weekStats.completion_rate}%`} color="#10b981" />
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

    // 当前月高亮
    const now = new Date()
    const currentMonthIdx = now.getFullYear() === yearKey ? now.getMonth() : -1
    const MONTH_CELL_W = 72

    return (
      <div className="p-4 overflow-auto h-full">
        {/* 年度目标甘特条（Goals 跨月） */}
        <div className="mb-4 rounded-lg p-4" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
          <div className="flex items-center gap-2 mb-3">
            <Layers size={14} className="text-cd-accent" />
            <h3 className="text-sm font-semibold text-cd-text">年度目标时间线</h3>
          </div>
          {yearGoals.length === 0 ? (
            <div className="text-xs text-cd-text-tertiary py-2">暂无长期目标，去「长期目标」页创建</div>
          ) : (
            <div className="rounded-lg overflow-hidden" style={{ border: '1px solid var(--cd-border)' }}>
              <TimeAxis mode="month" start={1} end={12} cellWidth={MONTH_CELL_W} height={24}
                highlightIndex={currentMonthIdx} />
              <div style={{ position: 'relative', minHeight: yearGoals.length * 36 + 8, padding: '4px 0' }}>
                {/* 月网格竖线 */}
                {Array.from({ length: 13 }, (_, i) => (
                  <div key={i} style={{
                    position: 'absolute', top: 0, bottom: 0, left: i * MONTH_CELL_W,
                    width: 1, background: 'var(--cd-border)', opacity: 0.3,
                  }} />
                ))}
                {/* 当前月高亮 */}
                {currentMonthIdx >= 0 && (
                  <div style={{
                    position: 'absolute', top: 0, bottom: 0,
                    left: currentMonthIdx * MONTH_CELL_W, width: MONTH_CELL_W,
                    background: '#7B68EE08',
                  }} />
                )}
                {/* 目标条 */}
                {yearGoals.map((goal, rowIdx) => {
                  const startMonth = goal.start_date ? new Date(goal.start_date).getMonth() : 0
                  const endMonth = goal.target_date ? new Date(goal.target_date).getMonth() : 11
                  const spanMonths = Math.max(1, endMonth - startMonth + 1)
                  const progress = (goal.progress || 0) / 100
                  const top = rowIdx * 36 + 4
                  const left = startMonth * MONTH_CELL_W + 4
                  const width = spanMonths * MONTH_CELL_W - 8
                  return (
                    <GanttBar
                      key={goal.id}
                      left={left}
                      width={width}
                      top={top}
                      height={28}
                      progress={progress}
                      color={goal.color || '#7B68EE'}
                      label={goal.title}
                      sublabel={`${Math.round(progress * 100)}%`}
                      done={progress >= 1}
                    />
                  )
                })}
              </div>
            </div>
          )}
        </div>

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

  // ── 月视图（甘特横条：周为X轴 + 月任务跨周条）──
  function renderMonthView() {
    if (!monthPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    const [y, m] = monthKey.split('-').map(Number)
    const daysInMonth = new Date(y, m, 0).getDate()
    // 计算该月有几周（ISO周）
    const firstDate = new Date(y, m - 1, 1)
    const lastDate = new Date(y, m - 1, daysInMonth)
    const weekCount = Math.ceil((firstDate.getDay() + daysInMonth) / 7)
    const CELL_W = 100  // 每周格子宽度

    // 当前是第几周（用于高亮）
    const today = new Date()
    const isCurrentMonth = today.getFullYear() === y && today.getMonth() === m - 1
    const currentWeekIdx = isCurrentMonth ? Math.floor((today.getDate() + firstDate.getDay() - 1) / 7) : -1

    // 月完成率（环形）— 后端返回 0-100，转为 0-1 供 SVG 环计算
    const mRate = (monthStats?.completion_rate || 0) / 100
    const ringR = 34, ringC = 2 * Math.PI * ringR
    const ringOff = ringC - mRate * ringC

    // 构建甘特行：每个月任务一行，子任务缩进
    const ganttRows: { task: TodoV2; isChild: boolean; startWeek: number; spanWeeks: number }[] = []
    monthPlan.month_tasks.forEach(mt => {
      // 月任务跨整月（或从创建到 due_date）
      const totalWeeks = weekCount
      ganttRows.push({ task: mt, isChild: false, startWeek: 0, spanWeeks: totalWeeks })
      // 子任务按 week_start 定位
      mt.children.forEach(child => {
        let sw = 0
        if (child.week_start) {
          const wsDate = new Date(child.week_start + 'T00:00:00')
          const dayOfMonth = wsDate.getDate()
          const wsMonth = wsDate.getMonth()
          if (wsMonth === m - 1) {
            sw = Math.floor((dayOfMonth + firstDate.getDay() - 1) / 7)
          }
        } else if (child.assigned_date) {
          const ad = new Date(child.assigned_date + 'T00:00:00')
          sw = Math.floor((ad.getDate() + firstDate.getDay() - 1) / 7)
        }
        sw = Math.max(0, Math.min(sw, totalWeeks - 1))
        ganttRows.push({ task: child, isChild: true, startWeek: sw, spanWeeks: 1 })
      })
    })

    return (
      <div className="flex h-full overflow-hidden">
        {/* 甘特主区 */}
        <div className="flex-1 p-4 overflow-auto">
          <div className="mb-3 flex items-center gap-3">
            <CalendarDays size={16} className="text-cd-accent" />
            <h2 className="text-sm font-semibold text-cd-text">{monthPlan.title || `${monthKey} 月计划`}</h2>
            {monthPlan.goal && <span className="text-xs text-cd-text-tertiary truncate">🎯 {monthPlan.goal}</span>}
          </div>

          {ganttRows.length === 0 ? (
            <div className="text-center py-8 text-cd-text-tertiary text-sm">
              <Target size={32} className="mx-auto mb-2 opacity-30" />
              本月暂无任务
            </div>
          ) : (
            <div className="rounded-lg overflow-hidden" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
              {/* 周刻度 */}
              <TimeAxis mode="week" start={1} end={weekCount} cellWidth={CELL_W} height={26}
                highlightIndex={currentWeekIdx} />
              {/* 甘特行 */}
              <div style={{ position: 'relative', minHeight: ganttRows.length * 36 + 8, padding: '4px 0' }}>
                {/* 周网格竖线 */}
                {Array.from({ length: weekCount + 1 }, (_, i) => (
                  <div key={i} style={{
                    position: 'absolute', top: 0, bottom: 0, left: i * CELL_W,
                    width: 1, background: 'var(--cd-border)', opacity: i === currentWeekIdx + 1 ? 0.8 : 0.3,
                  }} />
                ))}
                {/* 当前周高亮背景 */}
                {currentWeekIdx >= 0 && (
                  <div style={{
                    position: 'absolute', top: 0, bottom: 0,
                    left: currentWeekIdx * CELL_W, width: CELL_W,
                    background: '#7B68EE08',
                  }} />
                )}
                {/* 任务条 */}
                {ganttRows.map(({ task, isChild, startWeek, spanWeeks }, rowIdx) => {
                  const catColor = CATEGORY_COLORS[task.category] || '#9999B0'
                  const isDone = task.status === 'completed'
                  const progress = task.target_min > 0 ? task.progress_min / task.target_min : (task as any).progress_pct ? (task as any).progress_pct / 100 : 0
                  const top = rowIdx * 36 + 4
                  const left = startWeek * CELL_W + 4
                  const width = spanWeeks * CELL_W - 8
                  return (
                    <GanttBar
                      key={task.id}
                      left={left}
                      width={width}
                      top={top}
                      height={isChild ? 22 : 28}
                      progress={progress}
                      category={task.category}
                      label={`${isChild ? '  └ ' : ''}${task.title}`}
                      sublabel={`${task.target_min}m`}
                      compact={isChild}
                      done={isDone}
                      isHabit={task.mode === 'habit'}
                      onClick={() => openDetail(task)}
                    />
                  )
                })}
              </div>
            </div>
          )}

          {/* 点击某周跳转提示 */}
          <div className="mt-2 text-[10px] text-cd-text-tertiary">
            提示：点击任务条查看详情 · 月任务显示为跨周长条，子任务按所属周定位
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

  // ── 周视图（真·横向甘特图：Y=任务行，X=7天时间轴）──
  function renderWeekView() {
    if (!weekPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    const filteredUnassigned = searchQuery.trim()
      ? unassigned.filter(t => t.title.toLowerCase().includes(searchQuery.toLowerCase()) || t.category.includes(searchQuery))
      : unassigned

    // 构建甘特行：按日期→优先级排序
    const ganttRows: { task: TodoV2; date: string }[] = []
    dates.forEach(date => {
      const tasks = [...(weekPlan.day_tasks[date] || [])]
        .sort((a, b) => (a.priority || 3) - (b.priority || 3))
      tasks.forEach(t => ganttRows.push({ task: t, date }))
    })
    const todayStr = getTodayStr()
    const todayTasks = weekPlan.day_tasks[todayStr] || []
    const LABEL_W = 172
    const ROW_H = 42

    return (
      <div className="flex h-full">
        {/* 左侧：待分配清单 */}
        <div
          onDragOver={handleDragOver('unassigned')}
          onDragLeave={handleDragLeave('unassigned')}
          onDrop={handleDropUnassigned}
          className="flex flex-col overflow-hidden shrink-0"
          style={{
            width: 240, background: 'var(--cd-bg-tertiary)',
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

        {/* 右侧：横向甘特图 */}
        <div className="flex-1 flex flex-col overflow-hidden" style={{ background: 'var(--cd-card)' }}>
          {/* 表头：日期列 + 7天负载 */}
          <div className="flex shrink-0" style={{ borderBottom: '1.5px solid var(--cd-border)' }}>
            <div className="flex items-center px-3 shrink-0" style={{ width: LABEL_W, borderRight: '1px solid var(--cd-border)' }}>
              <span className="text-[10px] font-semibold text-cd-text-tertiary">任务 \ 日期</span>
            </div>
            <div className="flex-1 grid grid-cols-7">
              {dates.map((date, idx) => {
                const tasks = weekPlan.day_tasks[date] || []
                const totalMin = dayMin(tasks)
                const overLimit = totalMin > DAILY_LIMIT
                const nearLimit = totalMin >= DAILY_LIMIT * 0.8
                const loadPct = Math.min(100, (totalMin / DAILY_LIMIT) * 100)
                const isTodayCol = date === todayStr
                const weekend = isWeekend(date)
                return (
                  <div key={date} className="px-1.5 py-1.5"
                    style={{
                      borderRight: idx < 6 ? '1px solid var(--cd-border)' : 'none',
                      background: isTodayCol ? '#7B68EE0D' : weekend ? 'var(--cd-bg-tertiary)' : 'transparent',
                    }}>
                    <div className="flex items-center justify-center gap-1">
                      <span className="text-[11px] font-semibold" style={{ color: isTodayCol ? '#937CFF' : 'var(--cd-text)' }}>
                        {WEEKDAY_LABELS[idx]}
                      </span>
                      <span className="text-[9px] text-cd-text-tertiary tabular-nums">{fmtDate(date)}</span>
                      {isTodayCol && <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#7B68EE' }} />}
                    </div>
                    {/* 日负载条 */}
                    <div className="mt-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--cd-bg-tertiary)' }}>
                      <div style={{
                        width: `${loadPct}%`, height: '100%', borderRadius: 4,
                        background: overLimit ? '#ef4444' : nearLimit ? '#F0C040' : '#10b981',
                        transition: 'width 0.4s',
                      }} />
                    </div>
                    <div className="text-center mt-0.5">
                      <span className="text-[8px] tabular-nums" style={{ color: overLimit ? '#ef4444' : 'var(--cd-text-tertiary)' }}>
                        {totalMin}m / {DAILY_LIMIT}m{overLimit && ' ⚠'}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 甘特行 */}
          <div className="flex-1 overflow-y-auto scrollbar-thin">
            {ganttRows.length === 0 ? (
              <div className="text-center py-12 text-cd-text-tertiary">
                <Target size={28} className="mx-auto mb-2 opacity-30" />
                <div className="text-xs">本周暂无任务，从左侧拖入任务开始规划</div>
              </div>
            ) : ganttRows.map(({ task: t, date }, rowIdx) => {
              const catColor = CATEGORY_COLORS[t.category] || '#9999B0'
              const isDone = t.status === 'completed'
              const progress = t.target_min > 0 ? Math.min(1, t.progress_min / t.target_min) : 0
              const dur = t.target_min || (t.estimated_pomodoros || 1) * (POMODORO_SIZES[t.pomodoro_size]?.work || 25)
              const isHabit = t.mode === 'habit'
              const pc = PRIORITY_COLORS[(t.priority || 3) - 1]
              const dateIdx = dates.indexOf(date)
              // 条宽：按时长占日限额比例，最小35%
              const barWidthPct = Math.max(35, Math.min(96, (dur / DAILY_LIMIT) * 100))
              return (
                <div key={t.id} className="flex group"
                  style={{
                    height: ROW_H,
                    borderBottom: '1px solid color-mix(in srgb, var(--cd-border) 50%, transparent)',
                    background: rowIdx % 2 === 1 ? 'color-mix(in srgb, var(--cd-bg-tertiary) 30%, transparent)' : 'transparent',
                    opacity: dragId === t.id ? 0.4 : 1,
                    transition: 'opacity 0.15s',
                  }}>
                  {/* 左：任务标签 */}
                  <div
                    draggable
                    onDragStart={handleDragStart(t)}
                    onDragEnd={handleDragEnd}
                    onClick={() => openDetail(t)}
                    className="flex items-center gap-1.5 px-2.5 shrink-0 cursor-grab active:cursor-grabbing overflow-hidden"
                    style={{ width: LABEL_W, borderRight: '1px solid var(--cd-border)', borderLeft: `3px solid ${pc}` }}
                  >
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: catColor }} />
                    <span className="text-[11px] text-cd-text truncate flex-1"
                      style={{ textDecoration: isDone ? 'line-through' : 'none', opacity: isDone ? 0.5 : 1 }}>
                      {t.title}
                    </span>
                    <span className="text-[9px] tabular-nums text-cd-text-tertiary shrink-0">{dur}m</span>
                  </div>
                  {/* 右：7天网格 + 甘特条 */}
                  <div className="flex-1 grid grid-cols-7 relative">
                    {dates.map((d, idx) => {
                      const isTodayCol = d === todayStr
                      const weekend = isWeekend(d)
                      const isDropTarget = dragOverCol === d
                      return (
                        <div key={d}
                          onDragOver={handleDragOver(d)}
                          onDragLeave={handleDragLeave(d)}
                          onDrop={handleDropDay(d)}
                          style={{
                            borderRight: idx < 6 ? '1px solid color-mix(in srgb, var(--cd-border) 60%, transparent)' : 'none',
                            background: isDropTarget ? '#7B68EE1A' : isTodayCol ? '#7B68EE08' : weekend ? 'color-mix(in srgb, var(--cd-bg-tertiary) 40%, transparent)' : 'transparent',
                            transition: 'background 0.15s',
                          }}
                        />
                      )
                    })}
                    {/* 甘特条（绝对定位于对应日期列） */}
                    {isHabit ? (
                      /* 习惯任务：横跨整周条纹条 */
                      <div
                        draggable
                        onDragStart={handleDragStart(t)}
                        onDragEnd={handleDragEnd}
                        onClick={() => openDetail(t)}
                        className="absolute rounded-md cursor-grab active:cursor-grabbing hover:brightness-110 transition flex items-center px-2 overflow-hidden"
                        style={{
                          left: 4, right: 4, top: (ROW_H - 26) / 2, height: 26,
                          background: `repeating-linear-gradient(135deg, ${catColor}22 0px, ${catColor}22 6px, ${catColor}0D 6px, ${catColor}0D 12px)`,
                          border: `1px solid ${catColor}55`,
                          borderLeft: `3px solid ${catColor}`,
                          opacity: isDone ? 0.5 : 1,
                        }}
                      >
                        <span className="text-[9px] font-medium" style={{ color: catColor }}>习惯 · 每日</span>
                        {progress > 0 && <span className="text-[8px] tabular-nums ml-auto text-cd-text-tertiary">{Math.round(progress * 100)}%</span>}
                      </div>
                    ) : (
                      /* 普通任务：定位于分配日列，宽度按时长比例 */
                      <div
                        draggable
                        onDragStart={handleDragStart(t)}
                        onDragEnd={handleDragEnd}
                        onClick={() => openDetail(t)}
                        className="absolute rounded-md cursor-grab active:cursor-grabbing hover:brightness-110 transition overflow-hidden flex items-center"
                        style={{
                          left: `calc(${(dateIdx * 100 / 7).toFixed(3)}% + 3px)`,
                          width: `${(barWidthPct / 7).toFixed(2)}%`,
                          minWidth: 54,
                          top: (ROW_H - 26) / 2, height: 26,
                          background: `${catColor}1A`,
                          border: `1px solid ${catColor}44`,
                          borderLeft: `3px solid ${catColor}`,
                          opacity: isDone ? 0.55 : 1,
                        }}
                      >
                        {/* 进度填充 */}
                        <div style={{
                          position: 'absolute', left: 0, top: 0, bottom: 0,
                          width: `${Math.round(progress * 100)}%`,
                          background: isDone ? '#10b98166' : `${catColor}55`,
                          transition: 'width 0.4s',
                        }} />
                        <span className="relative text-[9px] tabular-nums px-1.5 truncate"
                          style={{ color: isDone ? '#10b981' : catColor, fontWeight: 600 }}>
                          {isDone ? '✓ ' : ''}{t.plan_start_min != null ? fmtHM(t.plan_start_min) + ' ' : ''}{dur}m
                        </span>
                        {progress > 0 && !isDone && (
                          <span className="relative text-[8px] tabular-nums text-cd-text-tertiary ml-auto pr-1.5">{Math.round(progress * 100)}%</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {/* 底栏：今日专注入口 */}
          {todayTasks.some(t => t.status !== 'completed') && (
            <div className="shrink-0 px-3 py-2 flex items-center gap-2" style={{ borderTop: '1px solid var(--cd-border)' }}>
              <span className="text-[10px] text-cd-text-tertiary">今日待完成 {todayTasks.filter(t => t.status !== 'completed').length} 项</span>
              <button
                onClick={() => { const t = todayTasks.find(t => t.status !== 'completed'); if (t) startFocus(t.id) }}
                className="flex items-center gap-1 px-2.5 py-1 text-[10px] rounded transition hover:brightness-125"
                style={{ background: '#7B68EE22', color: '#937CFF', border: '1px solid #7B68EE55' }}
              >
                <Play size={9} /> 开始专注
              </button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ── 日视图（甘特时间轴）──
  function renderDayView() {
    if (!weekPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    const allTasks = (weekPlan.day_tasks[selectedDate] || []).slice().sort((a, b) => (a.priority || 3) - (b.priority || 3) || a.id - b.id)
    const isToday = selectedDate === getTodayStr()
    const shiftDay = (delta: number) => {
      const d = new Date(selectedDate + 'T00:00:00')
      d.setDate(d.getDate() + delta)
      const ns = formatLocalDate(d)
      setSelectedDate(ns)
      const ws = getWeekStart(new Date(ns + 'T00:00:00'))
      if (ws !== weekStart) setWeekStart(ws)
    }
    // 分离习惯任务和时间任务
    const habitTasks = allTasks.filter(t => t.mode === 'habit')
    const timeTasks = allTasks.filter(t => t.mode !== 'habit')

    // 甘特时间轴参数
    const DAY_START = 8 * 60  // 8:00
    const DAY_END = 22 * 60   // 22:00
    const TOTAL_MIN = DAY_END - DAY_START
    const PX_PER_MIN = 0.9    // 每分钟像素高度
    const GRID_HEIGHT = TOTAL_MIN * PX_PER_MIN
    const LEFT_LABEL_W = 48   // 左侧时间标签宽度

    // 自动排列算法：有 plan_start_min 的用存储值，没有的从 9:00 顺序累加（含番茄休息）
    let autoAcc = 9 * 60
    const BREAK_SHORT = 5   // 番茄间短休息
    const BREAK_LONG = 15   // 每4番茄长休息
    let pomodoroSinceBreak = 0
    const ganttItems = timeTasks.map(t => {
      const work = POMODORO_SIZES[t.pomodoro_size]?.work || 25
      const dur = (t.estimated_pomodoros || 1) * work
      let start: number
      if (t.plan_start_min != null && t.plan_start_min >= DAY_START && t.plan_start_min < DAY_END) {
        start = t.plan_start_min
      } else {
        // 自动排列：加入休息间隔
        if (pomodoroSinceBreak > 0) {
          autoAcc += (pomodoroSinceBreak % 4 === 0) ? BREAK_LONG : BREAK_SHORT
        }
        start = autoAcc
        pomodoroSinceBreak += (t.estimated_pomodoros || 1)
      }
      autoAcc = start + dur
      const progress = t.target_min > 0 ? t.progress_min / t.target_min : 0
      return { t, start, dur, progress }
    })

    // 当前时间（分钟）
    const now = new Date()
    const nowMin = now.getHours() * 60 + now.getMinutes()
    const showNowLine = isToday && nowMin >= DAY_START && nowMin <= DAY_END

    const d = new Date(selectedDate + 'T00:00:00')
    const wd = (d.getDay() + 6) % 7
    const totalMin = dayMin(allTasks)

    return (
      <div className="p-4 overflow-auto h-full">
        {/* 头部 */}
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-cd-text">{fmtDate(selectedDate)} {WEEKDAY_LABELS[wd]}</h2>
            <span className="text-xs text-cd-text-tertiary">{allTasks.length} 个任务 · 总计 {totalMin}m</span>
          </div>
          {isToday && allTasks.some(t => t.status !== 'completed') && (
            <button
              onClick={() => { const t = allTasks.find(t => t.status !== 'completed'); if (t) startFocus(t.id) }}
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

        <div className="flex gap-4">
          {/* 甘特时间轴主区 */}
          <div className="flex-1 max-w-3xl">
            {timeTasks.length === 0 && habitTasks.length === 0 ? (
              <div className="text-center py-8 text-cd-text-tertiary text-sm">
                <Target size={32} className="mx-auto mb-2 opacity-30" />
                当日无任务
              </div>
            ) : (
              <div className="rounded-lg overflow-hidden" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
                {/* 时间刻度 */}
                <TimeAxis mode="hour" start={8} end={22} cellWidth={60} labelOffset={LEFT_LABEL_W} height={24}
                  highlightIndex={isToday ? now.getHours() - 8 : -1} />
                {/* 时间网格 */}
                <div style={{ position: 'relative', height: GRID_HEIGHT, marginLeft: LEFT_LABEL_W }}>
                  {/* 小时网格线 */}
                  {Array.from({ length: 14 }, (_, i) => (
                    <div key={i} style={{
                      position: 'absolute', top: i * 60 * PX_PER_MIN, left: 0, right: 0,
                      height: 1, background: 'var(--cd-border)', opacity: 0.4,
                    }} />
                  ))}
                  {/* 半小时虚线 */}
                  {Array.from({ length: 14 }, (_, i) => (
                    <div key={`h${i}`} style={{
                      position: 'absolute', top: (i * 60 + 30) * PX_PER_MIN, left: 0, right: 0,
                      height: 1, background: 'var(--cd-border)', opacity: 0.15,
                      borderStyle: 'dashed',
                    }} />
                  ))}
                  {/* 任务甘特条 */}
                  {ganttItems.map(({ t, start, dur, progress }) => {
                    const top = (start - DAY_START) * PX_PER_MIN
                    const height = Math.max(dur * PX_PER_MIN, 22)
                    const catColor = CATEGORY_COLORS[t.category] || '#9999B0'
                    const isDone = t.status === 'completed'
                    return (
                      <GanttBar
                        key={t.id}
                        left={4}
                        width="calc(100% - 8px)"
                        top={top}
                        height={height}
                        progress={progress}
                        category={t.category}
                        label={t.title}
                        sublabel={`${dur}m · ${t.progress_min}/${t.target_min}m`}
                        done={isDone}
                        priorityColor={['#ef4444', '#f59e0b', '#F0C040', '#10b981', '#6b7280'][(t.priority || 3) - 1]}
                        draggable
                        onDragStart={handleDragStart(t)}
                        onDragEnd={handleDragEnd}
                        onClick={() => openDetail(t)}
                        style={{ opacity: dragId === t.id ? 0.5 : 1 }}
                      />
                    )
                  })}
                  {/* 当前时间红线 */}
                  {showNowLine && (
                    <div style={{
                      position: 'absolute',
                      top: (nowMin - DAY_START) * PX_PER_MIN,
                      left: -LEFT_LABEL_W,
                      right: 0,
                      height: 2,
                      background: '#ef4444',
                      zIndex: 10,
                      pointerEvents: 'none',
                    }}>
                      <div style={{
                        position: 'absolute', left: 4, top: -8,
                        fontSize: 9, color: '#ef4444', fontWeight: 600,
                        background: 'var(--cd-card)', padding: '0 3px', borderRadius: 2,
                      }}>
                        {fmtHM(nowMin)}
                      </div>
                    </div>
                  )}
                </div>
                {/* 左侧时间标签（覆盖层） */}
                <div style={{ position: 'absolute', top: 0, left: 0, width: LEFT_LABEL_W, pointerEvents: 'none' }}>
                </div>
              </div>
            )}
            {/* 左侧小时标签 */}
            {timeTasks.length > 0 && (
              <div className="flex mt-1" style={{ marginLeft: 0 }}>
                <div style={{ width: LEFT_LABEL_W }} className="flex flex-col text-right pr-2">
                  {Array.from({ length: 15 }, (_, i) => (
                    <span key={i} className="text-[9px] tabular-nums text-cd-text-tertiary" style={{ height: 60 * PX_PER_MIN, lineHeight: `${60 * PX_PER_MIN}px` }}>
                      {8 + i}:00
                    </span>
                  ))}
                </div>
              </div>
            )}
            {/* 添加任务 */}
            <button
              onClick={() => setShowCreateModal(true)}
              className="mt-4 flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-cd-green/20 text-cd-green border border-cd-green/30 hover:bg-cd-green/30 transition"
            >
              <Plus size={12} /> 添加任务
            </button>
          </div>

          {/* 右侧：习惯清单 */}
          {habitTasks.length > 0 && (
            <div className="w-52 shrink-0">
              <div className="rounded-lg p-3" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
                <h3 className="text-xs font-semibold text-cd-text mb-2 flex items-center gap-1">
                  <Flame size={12} className="text-cd-green" /> 每日习惯
                </h3>
                <div className="flex flex-col gap-1.5">
                  {habitTasks.map(t => {
                    const isDone = t.status === 'completed'
                    const catColor = CATEGORY_COLORS[t.category] || '#F0C040'
                    return (
                      <div key={t.id}
                        onClick={() => openDetail(t)}
                        className="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:brightness-110 transition"
                        style={{ background: `${catColor}12`, border: `1px solid ${catColor}33` }}
                      >
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: isDone ? 'var(--cd-green)' : catColor }} />
                        <span className="text-[11px] text-cd-text truncate" style={{ textDecoration: isDone ? 'line-through' : 'none', opacity: isDone ? 0.6 : 1 }}>
                          {t.title}
                        </span>
                        {isDone && <span className="text-[9px] text-green-400 ml-auto">✓</span>}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
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
