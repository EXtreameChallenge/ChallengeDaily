import { useState, useEffect, useCallback } from 'react'
import {
  Calendar, CalendarDays, ChevronLeft, ChevronRight, Plus, GripVertical, Play, X, Target,
} from 'lucide-react'
import {
  getWeekPlan, getUnassignedTodos, getWeekPlanStats, getMonthPlan, getMonthPlanStats,
  assignTodo, unassignTodo, createTodo, request,
  getWeekStart, getWeekDates, getMonthKey,
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

// 本地日期字符串（不受时区影响，每次调用时动态计算，避免跨午夜后过期）
function getTodayStr(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 本地日期格式化（不受时区影响）
function formatLocalDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// 本地月份格式化（不受时区影响）
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

// ── 任务卡片（共享组件）──
interface CardProps {
  todo: TodoV2
  compact?: boolean
  onClick?: () => void
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: (e: React.DragEvent) => void
}
function TaskCard({ todo, compact, onClick, onDragStart, onDragEnd }: CardProps) {
  const isDone = todo.status === 'completed'
  const pc = PRIORITY_COLORS[(todo.priority || 3) - 1]
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className="relative rounded-md cursor-grab active:cursor-grabbing transition hover:brightness-110"
      style={{
        background: compact ? 'var(--cd-bg-tertiary)' : 'var(--cd-bg-secondary)',
        borderLeft: `3px solid ${pc}`,
        padding: '6px 8px 6px 10px',
      }}
    >
      <GripVertical size={8} className="absolute top-1 right-1 opacity-30" style={{ color: 'var(--cd-text-tertiary)' }} />
      <div className="text-cd-text leading-tight" style={{ fontSize: 9, textDecoration: isDone ? 'line-through' : 'none', opacity: isDone ? 0.6 : 1 }}>
        {todo.title}
      </div>
      <div className="flex items-center justify-between mt-1" style={{ fontSize: 7, opacity: isDone ? 0.6 : 1 }}>
        <span className="text-cd-text-tertiary">{todo.category} · {MODE_LABELS[todo.mode] || todo.mode}</span>
        <span className="text-cd-text-tertiary tabular-nums">{todo.progress_min}/{todo.target_min}m</span>
      </div>
      {!todo.assigned_date && (
        <div style={{ fontSize: 9, color: '#F0C040' }} className="mt-0.5">⬚ 未安排</div>
      )}
    </div>
  )
}

// ── 底部统计块 ──
function Stat({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-xs font-semibold tabular-nums" style={{ color }}>{value}</span>
      <span className="text-[9px] text-cd-text-tertiary">{label}</span>
    </div>
  )
}

export default function WeekPlan() {
  const { success, error } = useToast()
  const [viewMode, setViewMode] = useState<'week' | 'month' | 'day'>('week')
  const [weekStart, setWeekStart] = useState(getWeekStart())
  const [monthKey, setMonthKey] = useState(getMonthKey())
  const [selectedDate, setSelectedDate] = useState(getTodayStr())
  const [weekPlan, setWeekPlan] = useState<WeekPlanData | null>(null)
  const [unassigned, setUnassigned] = useState<TodoV2[]>([])
  const [weekStats, setWeekStats] = useState<WeekPlanStats | null>(null)
  const [monthPlan, setMonthPlan] = useState<MonthPlanData | null>(null)
  const [monthStats, setMonthStats] = useState<MonthPlanStats | null>(null)
  const [dragId, setDragId] = useState<number | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [modalTodo, setModalTodo] = useState<TodoV2 | null>(null)
  const [splitDraft, setSplitDraft] = useState<SplitDraftTask[] | null>(null)
  const [splitLoading, setSplitLoading] = useState(false)
  const [splitGoalTitle, setSplitGoalTitle] = useState('')
  const [splitGoalDesc, setSplitGoalDesc] = useState('')

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
    } catch {
      error('加载月计划失败')
    }
  }, [error])

  useEffect(() => {
    if (viewMode === 'month') loadMonth(monthKey)
    else loadWeek(weekStart)
  }, [viewMode, weekStart, monthKey, loadWeek, loadMonth])

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
  const goToday = () => {
    setWeekStart(getWeekStart())
    setMonthKey(getMonthKey())
    setSelectedDate(getTodayStr())
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
    // E7: 拖拽满负荷阻止 — 检查目标日负载是否超阈值
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

  // ── 新建任务（通过 TaskCreateModal）──
  const handleTaskCreated = (_id: number) => {
    success('任务已创建')
    if (viewMode === 'month') loadMonth(monthKey); else loadWeek(weekStart)
  }

  const openDetail = (todo: TodoV2) => setModalTodo(todo)
  const refreshAfterModal = () => { if (viewMode === 'month') loadMonth(monthKey); else loadWeek(weekStart) }
  const startFocus = (id: number) => { window.location.hash = '#/focus?todo_id=' + id }
  const dates = weekPlan?.dates || getWeekDates(weekStart)

  // ── AI 拆解目标 ──
  const handleAutoSplit = async () => {
    if (!splitGoalTitle.trim()) {
      error('请先输入目标标题')
      return
    }
    setSplitLoading(true)
    try {
      const res = await request('/api/week-plan/auto-split', {
        method: 'POST',
        body: JSON.stringify({
          goal_title: splitGoalTitle,
          goal_description: splitGoalDesc,
          week_start: weekStart,
        }),
      }, 30000) as { draft_tasks?: SplitDraftTask[]; error?: string }
      if (res.error) {
        error(res.error)
        return
      }
      const tasks = (res.draft_tasks || []).map(t => ({ ...t, _checked: true }))
      setSplitDraft(tasks)
    } catch (e) {
      error(e instanceof Error ? e.message : 'AI 拆解失败')
    } finally {
      setSplitLoading(false)
    }
  }

  const removeSplitTask = (idx: number) => {
    setSplitDraft(prev => prev ? prev.filter((_, i) => i !== idx) : null)
  }

  const toggleSplitTask = (idx: number) => {
    setSplitDraft(prev => prev ? prev.map((t, i) => i === idx ? { ...t, _checked: !t._checked } : t) : null)
  }

  const updateSplitTask = (idx: number, field: keyof SplitDraftTask, value: string | number) => {
    setSplitDraft(prev => prev ? prev.map((t, i) => i === idx ? { ...t, [field]: value } : t) : null)
  }

  const confirmSplit = async () => {
    if (!splitDraft) return
    const checked = splitDraft.filter(t => t._checked)
    if (checked.length === 0) {
      error('请至少选择一个任务')
      return
    }
    // 按 day 分配到对应日期（day 1-5 -> 周一到周五）
    const weekDates = getWeekDates(weekStart)
    let created = 0
    for (const t of checked) {
      try {
        const dayIdx = (t.day || 1) - 1
        const assignedDate = dayIdx >= 0 && dayIdx < 5 ? weekDates[dayIdx] : ''
        await createTodo({
          title: t.title,
          category: t.category || '开发',
          target_min: Number(t.target_min) || 25,
          task_level: 'day',
          assigned_date: assignedDate || undefined,
          week_start: weekStart,
        })
        created++
      } catch {
        // 单条失败继续
      }
    }
    success(`已创建 ${created} 个任务`)
    setSplitDraft(null)
    setSplitGoalTitle('')
    setSplitGoalDesc('')
    if (viewMode === 'month') loadMonth(monthKey); else loadWeek(weekStart)
  }

  // ── 底部数据条 ──
  function renderBottomBar() {
    if (!weekStats) return null
    const maxMin = Math.max(60, ...weekStats.daily_focus.map(d => d.focus_min))
    return (
      <div className="flex items-center gap-4 px-4 border-t border-cd-border" style={{ height: 56, background: 'var(--cd-card)' }}>
        <div className="flex items-end gap-1.5" style={{ height: 40 }}>
          {weekStats.daily_focus.map(d => {
            const h = Math.max(2, (d.focus_min / maxMin) * 36)
            const isToday = d.date === getTodayStr()
            return (
              <div key={d.date} className="flex flex-col items-center" title={`${fmtDate(d.date)}: ${d.focus_min}min`}>
                <div style={{ width: 8, height: h, background: isToday ? '#7B68EE' : '#7B68EE55', borderRadius: 2, transition: 'height 0.5s' }} />
                <span style={{ fontSize: 7, color: 'var(--cd-text-tertiary)' }}>{fmtDate(d.date).split('/')[1]}</span>
              </div>
            )
          })}
        </div>
        <div className="flex-1" />
        <Stat label="完成率" value={`${Math.round(weekStats.completion_rate * 100)}%`} color="#10b981" />
        <Stat label="深度工作" value={`${Math.round(weekStats.deep_focus_min)}m`} color="#7B68EE" />
        <Stat label="中断次数" value={weekStats.interrupt_count} color="#ef4444" />
        <Stat label="连续天数" value={`${weekStats.streak_days}d`} color="#F0C040" />
      </div>
    )
  }

  // ── 周视图 ──
  function renderWeekView() {
    if (!weekPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    return (
      <div className="flex h-full">
        {/* 待分配区 */}
        <div
          onDragOver={handleDragOver('unassigned')}
          onDragLeave={handleDragLeave('unassigned')}
          onDrop={handleDropUnassigned}
          className="flex flex-col overflow-y-auto scrollbar-thin"
          style={{
            width: 180, background: 'var(--cd-bg-tertiary)',
            border: '1.5px dashed',
            borderColor: dragOverCol === 'unassigned' ? '#7B68EE' : '#F0C04066',
            transition: 'border-color 0.15s',
          }}
        >
          <div className="px-3 py-2 sticky top-0 z-10" style={{ background: 'var(--cd-bg-tertiary)' }}>
            <div className="text-xs font-semibold" style={{ color: '#F0C040' }}>待分配</div>
            <div className="text-[10px] text-cd-text-tertiary">{unassigned.length} 个任务</div>
          </div>
          <div className="flex flex-col gap-1.5 px-2 pb-2">
            {unassigned.length === 0 && (
              <div className="text-[10px] text-cd-text-tertiary text-center py-4 opacity-60">无待分配任务</div>
            )}
            {unassigned.map(t => (
              <TaskCard key={t.id} todo={t} onClick={() => openDetail(t)}
                onDragStart={handleDragStart(t)} onDragEnd={handleDragEnd} />
            ))}
          </div>
        </div>

        {/* 七天列 */}
        <div className="flex-1 flex overflow-hidden">
          {dates.map((date, idx) => {
            const tasks = weekPlan.day_tasks[date] || []
            const totalMin = dayMin(tasks)
            const overLimit = totalMin > DAILY_LIMIT
            const isTodayCol = date === getTodayStr()
            const weekend = isWeekend(date)
            return (
              <div key={date}
                onDragOver={handleDragOver(date)}
                onDragLeave={handleDragLeave(date)}
                onDrop={handleDropDay(date)}
                className="flex-1 flex flex-col overflow-hidden"
                style={{
                  background: 'var(--cd-card)',
                  border: `1px solid ${isTodayCol ? '#7B68EE' : dragOverCol === date ? '#7B68EE' : 'var(--cd-border)'}`,
                  opacity: weekend ? 0.7 : 1,
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
                  </div>
                  <div className="flex items-center gap-1">
                    {overLimit && <span style={{ fontSize: 10, color: '#ef4444' }} title={`${totalMin}min 超载`}>⚠</span>}
                    <span className="text-[9px] text-cd-text-tertiary tabular-nums">{fmtDate(date)}</span>
                  </div>
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
                {/* 今日开始专注按钮 */}
                {isTodayCol && tasks.some(t => t.status !== 'completed') && (
                  <button
                    onClick={() => { const t = tasks.find(t => t.status !== 'completed'); if (t) startFocus(t.id) }}
                    className="mx-2 my-1.5 flex items-center justify-center gap-1 py-1 text-[10px] rounded transition hover:brightness-125"
                    style={{ background: '#7B68EE22', color: '#937CFF', border: '1px solid #7B68EE55' }}
                  >
                    <Play size={9} /> 开始专注
                  </button>
                )}
                {/* 任务列表 */}
                <div className="flex-1 overflow-y-auto scrollbar-thin px-1.5 py-1.5 flex flex-col gap-1">
                  {tasks.length === 0 && <div className="text-[9px] text-cd-text-tertiary text-center py-2 opacity-50">空</div>}
                  {tasks.map(t => (
                    <div key={t.id} style={{ opacity: dragId === t.id ? 0.5 : 1, transition: 'opacity 0.15s' }}>
                      <TaskCard todo={t} compact onClick={() => openDetail(t)}
                        onDragStart={handleDragStart(t)} onDragEnd={handleDragEnd} />
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // ── 月视图 ──
  function renderMonthView() {
    if (!monthPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    const [y, m] = monthKey.split('-').map(Number)
    const firstDay = new Date(y, m - 1, 1)
    const startWeekday = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1
    const daysInMonth = new Date(y, m, 0).getDate()
    const totalCells = Math.ceil((startWeekday + daysInMonth) / 7) * 7
    // 扁平化所有任务（含月任务子任务）
    const allTasks: TodoV2[] = []
    monthPlan.month_tasks.forEach(mt => { allTasks.push(mt, ...mt.children) })

    return (
      <div className="p-4 overflow-auto h-full">
        <div className="mb-3 flex items-center gap-3">
          <CalendarDays size={16} className="text-cd-accent" />
          <h2 className="text-sm font-semibold text-cd-text">{monthPlan.title || `${monthKey} 月计划`}</h2>
          {monthPlan.goal && <span className="text-xs text-cd-text-tertiary">🎯 {monthPlan.goal}</span>}
        </div>
        {monthStats && (
          <div className="flex gap-3 mb-3 text-xs">
            <span className="text-cd-text-secondary">任务 {monthStats.total_tasks}</span>
            <span className="text-green-400">完成 {monthStats.completed_tasks}</span>
            <span className="text-cd-accent">完成率 {Math.round(monthStats.completion_rate * 100)}%</span>
            <span className="text-cd-text-secondary">深度 {Math.round(monthStats.deep_focus_min)}m</span>
            <span className="text-red-400">中断 {monthStats.interrupt_count}</span>
          </div>
        )}
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
            const isTodayCell = date === getTodayStr()
            return (
              <div key={i}
                onClick={() => { setSelectedDate(date); setViewMode('day'); setWeekStart(getWeekStart(new Date(date))) }}
                className="rounded p-1 cursor-pointer hover:brightness-125 transition flex flex-col"
                style={{
                  background: isTodayCell ? '#7B68EE15' : 'var(--cd-card)',
                  border: `1px solid ${isTodayCell ? '#7B68EE55' : 'var(--cd-border)'}`,
                  minHeight: 64,
                }}
              >
                <span className="text-[10px] text-cd-text-tertiary">{dayNum}</span>
                <div className="flex flex-col gap-0.5 mt-0.5">
                  {dayTasks.slice(0, 3).map(t => (
                    <div key={t.id} className="text-[8px] truncate rounded px-1"
                      style={{ background: 'var(--cd-bg-tertiary)', borderLeft: `2px solid ${PRIORITY_COLORS[(t.priority || 3) - 1]}`, color: 'var(--cd-text)' }}>
                      {t.title}
                    </div>
                  ))}
                  {dayTasks.length > 3 && <span className="text-[8px] text-cd-text-tertiary">+{dayTasks.length - 3}</span>}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // ── 日视图 ──
  function renderDayView() {
    if (!weekPlan) return <div className="p-8 text-center text-cd-text-tertiary text-sm">加载中...</div>
    const tasks = weekPlan.day_tasks[selectedDate] || []
    const isToday = selectedDate === getTodayStr()
    const shiftDay = (delta: number) => {
      const d = new Date(selectedDate + 'T00:00:00')
      d.setDate(d.getDate() + delta)
      const ns = formatLocalDate(d)
      setSelectedDate(ns)
      const ws = getWeekStart(new Date(ns + 'T00:00:00'))
      if (ws !== weekStart) setWeekStart(ws)
    }
    return (
      <div className="p-4 overflow-auto h-full">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-cd-text">{fmtDate(selectedDate)} 详情</h2>
            <span className="text-xs text-cd-text-tertiary">{tasks.length} 个任务 · 总计 {dayMin(tasks)}min</span>
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
        <div className="flex items-center gap-2 mb-3">
          <button onClick={() => shiftDay(-1)} className="p-1 rounded hover:bg-cd-hover text-cd-text-secondary"><ChevronLeft size={14} /></button>
          <input type="date" value={selectedDate} onChange={e => { setSelectedDate(e.target.value); const ws = getWeekStart(new Date(e.target.value)); if (ws !== weekStart) setWeekStart(ws) }}
            className="bg-cd-bg-input border border-cd-border rounded px-2 py-1 text-xs text-cd-text" />
          <button onClick={() => shiftDay(1)} className="p-1 rounded hover:bg-cd-hover text-cd-text-secondary"><ChevronRight size={14} /></button>
        </div>
        {/* 任务列表 */}
        <div className="space-y-1.5 max-w-2xl">
          {tasks.length === 0 && (
            <div className="text-center py-8 text-cd-text-tertiary text-sm">
              <Target size={32} className="mx-auto mb-2 opacity-30" />
              当日无任务
            </div>
          )}
          {tasks.map(t => (
            <div key={t.id} style={{ opacity: dragId === t.id ? 0.5 : 1, transition: 'opacity 0.15s' }}>
              <TaskCard todo={t} compact onClick={() => openDetail(t)}
                onDragStart={handleDragStart(t)} onDragEnd={handleDragEnd} />
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* ── 顶部导航栏 ── */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-cd-border">
        <div className="flex items-center gap-3">
          <Calendar size={18} className="text-cd-accent" />
          <h1 className="text-base font-semibold text-cd-text">周计划</h1>
          {/* 视图切换 */}
          <div className="flex bg-cd-bg-input rounded-lg p-0.5 ml-2">
            {(['month', 'week', 'day'] as const).map(v => (
              <button key={v} onClick={() => setViewMode(v)}
                className={`px-2.5 py-1 text-xs rounded-md transition ${viewMode === v ? 'bg-cd-accent/20 text-cd-accent' : 'text-cd-text-secondary hover:text-cd-text'}`}>
                {v === 'month' ? '月视图' : v === 'week' ? '周视图' : '日视图'}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => viewMode === 'month' ? shiftMonth(-1) : shiftWeek(-1)}
            className="p-1.5 rounded-lg hover:bg-cd-hover text-cd-text-secondary transition">
            <ChevronLeft size={16} />
          </button>
          <span className="text-sm text-cd-text tabular-nums min-w-[80px] text-center">
            {viewMode === 'month' ? monthKey : weekStart}
          </span>
          <button onClick={() => viewMode === 'month' ? shiftMonth(1) : shiftWeek(1)}
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

      {/* 主视图区 */}
      <div className="flex-1 overflow-hidden">
        {viewMode === 'week' && renderWeekView()}
        {viewMode === 'month' && renderMonthView()}
        {viewMode === 'day' && renderDayView()}
      </div>

      {/* 底部数据条 */}
      {viewMode !== 'month' && renderBottomBar()}

      {/* 任务详情浮层 */}
      <TaskDetailModal todo={modalTodo} onClose={() => setModalTodo(null)} onUpdate={refreshAfterModal} />

      {/* 统一任务创建弹窗 */}
      <TaskCreateModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleTaskCreated}
        defaults={{ week_start: weekStart, assigned_date: '' }}
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
