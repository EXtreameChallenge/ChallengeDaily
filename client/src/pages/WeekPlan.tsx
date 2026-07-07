import { useState, useEffect, useCallback } from 'react'
import {
  Calendar, CalendarDays, ChevronLeft, ChevronRight, Plus, GripVertical, Play, Check, Trash2, X, Target,
} from 'lucide-react'
import {
  getWeekPlan, getUnassignedTodos, getWeekPlanStats, getMonthPlan, getMonthPlanStats,
  assignTodo, unassignTodo, createTodo,
  getWeekStart, getWeekDates, getMonthKey,
  type TodoV2, type WeekPlanData, type WeekPlanStats, type MonthPlanData, type MonthPlanStats,
} from '../api/client'
import { useToast } from '../components/Toast'
import TaskDetailModal from '../components/TaskDetailModal'

// ── 常量 ──
const PRIORITY_COLORS = ['#ef4444', '#f59e0b', '#F0C040', '#10b981', '#6b7280']
const CATEGORIES = ['开发', '会议', '沟通', '文档', '测试', '设计', '运维', '数据分析', '学习', '管理', '产品', '生活']
const MODE_LABELS: Record<string, string> = { timer: '计时', goal: '目标', habit: '习惯' }
const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const TODAY_STR = new Date().toISOString().substring(0, 10)
const DAILY_LIMIT = 180 // 负载警示阈值（分钟）

function fmtDate(d: string) {
  const dt = new Date(d)
  return `${dt.getMonth() + 1}/${dt.getDate()}`
}
function isWeekend(d: string) {
  const day = new Date(d).getDay()
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
        background: compact ? '#2D2D2D' : '#2a2218',
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
  const [selectedDate, setSelectedDate] = useState(TODAY_STR)
  const [weekPlan, setWeekPlan] = useState<WeekPlanData | null>(null)
  const [unassigned, setUnassigned] = useState<TodoV2[]>([])
  const [weekStats, setWeekStats] = useState<WeekPlanStats | null>(null)
  const [monthPlan, setMonthPlan] = useState<MonthPlanData | null>(null)
  const [monthStats, setMonthStats] = useState<MonthPlanStats | null>(null)
  const [dragId, setDragId] = useState<number | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)
  const [showNewForm, setShowNewForm] = useState(false)
  const [newForm, setNewForm] = useState({ title: '', priority: 3, category: '开发', mode: 'timer' as 'timer' | 'goal' | 'habit', target_min: 25 })
  const [modalTodo, setModalTodo] = useState<TodoV2 | null>(null)

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
    const d = new Date(weekStart)
    d.setDate(d.getDate() + delta * 7)
    setWeekStart(d.toISOString().substring(0, 10))
  }
  const shiftMonth = (delta: number) => {
    const [y, m] = monthKey.split('-').map(Number)
    setMonthKey(new Date(y, m - 1 + delta, 1).toISOString().substring(0, 7))
  }
  const goToday = () => {
    setWeekStart(getWeekStart())
    setMonthKey(getMonthKey())
    setSelectedDate(TODAY_STR)
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
  const handleCreate = async () => {
    if (!newForm.title.trim()) return
    try {
      await createTodo({
        title: newForm.title, category: newForm.category, mode: newForm.mode,
        target_min: newForm.target_min, priority: newForm.priority,
      })
      success('任务已创建')
      setNewForm({ title: '', priority: 3, category: '开发', mode: 'timer', target_min: 25 })
      setShowNewForm(false)
      if (viewMode === 'month') loadMonth(monthKey); else loadWeek(weekStart)
    } catch { error('创建失败') }
  }

  const openDetail = (todo: TodoV2) => setModalTodo(todo)
  const refreshAfterModal = () => { if (viewMode === 'month') loadMonth(monthKey); else loadWeek(weekStart) }
  const startFocus = (id: number) => { window.location.hash = '#/focus?todo_id=' + id }
  const dates = weekPlan?.dates || getWeekDates(weekStart)

  // ── 底部数据条 ──
  function renderBottomBar() {
    if (!weekStats) return null
    const maxMin = Math.max(60, ...weekStats.daily_focus.map(d => d.focus_min))
    return (
      <div className="flex items-center gap-4 px-4 border-t border-cd-border" style={{ height: 56, background: 'var(--cd-card)' }}>
        <div className="flex items-end gap-1.5" style={{ height: 40 }}>
          {weekStats.daily_focus.map(d => {
            const h = Math.max(2, (d.focus_min / maxMin) * 36)
            const isToday = d.date === TODAY_STR
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
            width: 180, background: '#1a1410',
            border: '1.5px dashed',
            borderColor: dragOverCol === 'unassigned' ? '#7B68EE' : '#F0C04066',
            transition: 'border-color 0.15s',
          }}
        >
          <div className="px-3 py-2 sticky top-0 z-10" style={{ background: '#1a1410' }}>
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
            const isTodayCol = date === TODAY_STR
            const weekend = isWeekend(date)
            return (
              <div key={date}
                onDragOver={handleDragOver(date)}
                onDragLeave={handleDragLeave(date)}
                onDrop={handleDropDay(date)}
                className="flex-1 flex flex-col overflow-hidden"
                style={{
                  background: '#1E1E1E',
                  border: `1px solid ${isTodayCol ? '#7B68EE' : dragOverCol === date ? '#7B68EE' : '#2D2D2D'}`,
                  opacity: weekend ? 0.7 : 1,
                  minWidth: 0,
                  transition: 'border-color 0.15s, opacity 0.15s',
                }}
              >
                {/* 日期头 */}
                <div className="px-2 py-1.5 flex items-center justify-between" style={{ borderBottom: '1px solid #2D2D2D' }}>
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
                    <div className="h-1 mx-2 rounded-full overflow-hidden" style={{ background: '#2D2D2D' }}>
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
          <CalendarDays size={16} className="text-purple-400" />
          <h2 className="text-sm font-semibold text-cd-text">{monthPlan.title || `${monthKey} 月计划`}</h2>
          {monthPlan.goal && <span className="text-xs text-cd-text-tertiary">🎯 {monthPlan.goal}</span>}
        </div>
        {monthStats && (
          <div className="flex gap-3 mb-3 text-xs">
            <span className="text-cd-text-secondary">任务 {monthStats.total_tasks}</span>
            <span className="text-green-400">完成 {monthStats.completed_tasks}</span>
            <span className="text-purple-400">完成率 {Math.round(monthStats.completion_rate * 100)}%</span>
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
              return <div key={i} style={{ background: '#1a1a1a', borderRadius: 4, minHeight: 64 }} />
            }
            const date = `${monthKey}-${String(dayNum).padStart(2, '0')}`
            const dayTasks = allTasks.filter(t => t.assigned_date === date)
            const isTodayCell = date === TODAY_STR
            return (
              <div key={i}
                onClick={() => { setSelectedDate(date); setViewMode('day'); setWeekStart(getWeekStart(new Date(date))) }}
                className="rounded p-1 cursor-pointer hover:brightness-125 transition flex flex-col"
                style={{
                  background: isTodayCell ? '#7B68EE15' : '#1E1E1E',
                  border: `1px solid ${isTodayCell ? '#7B68EE55' : '#2D2D2D'}`,
                  minHeight: 64,
                }}
              >
                <span className="text-[10px] text-cd-text-tertiary">{dayNum}</span>
                <div className="flex flex-col gap-0.5 mt-0.5">
                  {dayTasks.slice(0, 3).map(t => (
                    <div key={t.id} className="text-[8px] truncate rounded px-1"
                      style={{ background: '#2D2D2D', borderLeft: `2px solid ${PRIORITY_COLORS[(t.priority || 3) - 1]}`, color: '#fff' }}>
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
    const isToday = selectedDate === TODAY_STR
    const shiftDay = (delta: number) => {
      const d = new Date(selectedDate)
      d.setDate(d.getDate() + delta)
      const ns = d.toISOString().substring(0, 10)
      setSelectedDate(ns)
      const ws = getWeekStart(new Date(ns))
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
              className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-purple-500/20 text-purple-300 border border-purple-400/30 hover:bg-purple-500/30 transition"
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
          <Calendar size={18} className="text-purple-400" />
          <h1 className="text-base font-semibold text-cd-text">周计划</h1>
          {/* 视图切换 */}
          <div className="flex bg-cd-bg-input rounded-lg p-0.5 ml-2">
            {(['month', 'week', 'day'] as const).map(v => (
              <button key={v} onClick={() => setViewMode(v)}
                className={`px-2.5 py-1 text-xs rounded-md transition ${viewMode === v ? 'bg-purple-500/20 text-purple-300' : 'text-cd-text-secondary hover:text-cd-text'}`}>
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
          <button onClick={() => setShowNewForm(!showNewForm)}
            className="flex items-center gap-1 px-3 py-1 text-xs rounded-lg bg-purple-500/20 text-purple-300 border border-purple-400/30 hover:bg-purple-500/30 transition">
            <Plus size={12} /> 新建
          </button>
        </div>
      </div>

      {/* 新建任务表单 */}
      {showNewForm && (
        <div className="flex items-center gap-2 px-4 py-2 border-b border-cd-border animate-fade-in" style={{ background: 'var(--cd-card)' }}>
          <input autoFocus value={newForm.title} onChange={e => setNewForm({ ...newForm, title: e.target.value })}
            placeholder="任务标题..."
            className="flex-1 bg-cd-bg-input border border-cd-border rounded-lg px-3 py-1.5 text-xs text-cd-text focus:outline-none focus:border-purple-400/50"
            onKeyDown={e => e.key === 'Enter' && handleCreate()} />
          <select value={newForm.category} onChange={e => setNewForm({ ...newForm, category: e.target.value })}
            className="bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 text-xs text-cd-text">
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={newForm.mode} onChange={e => setNewForm({ ...newForm, mode: e.target.value as 'timer' | 'goal' | 'habit' })}
            className="bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 text-xs text-cd-text">
            {Object.entries(MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <div className="flex items-center gap-1">
            <input type="number" min={5} step={5} value={newForm.target_min}
              onChange={e => setNewForm({ ...newForm, target_min: parseInt(e.target.value) || 25 })}
              className="w-14 bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 text-xs text-cd-text text-center" />
            <span className="text-[10px] text-cd-text-tertiary">min</span>
          </div>
          <div className="flex gap-0.5">
            {[1, 2, 3, 4, 5].map(p => (
              <button key={p} onClick={() => setNewForm({ ...newForm, priority: p })}
                className="w-5 h-5 rounded text-[10px] font-bold transition"
                style={{
                  background: newForm.priority === p ? PRIORITY_COLORS[p - 1] : 'transparent',
                  color: newForm.priority === p ? '#fff' : PRIORITY_COLORS[p - 1],
                  border: `1px solid ${PRIORITY_COLORS[p - 1]}`,
                }}>P{p}</button>
            ))}
          </div>
          <button onClick={handleCreate}
            className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-purple-500/20 text-purple-300 border border-purple-400/30 hover:bg-purple-500/30 transition">
            <Check size={12} /> 创建
          </button>
        </div>
      )}

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
    </div>
  )
}
