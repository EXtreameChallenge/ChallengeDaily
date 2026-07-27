import { Play, Plus, Target, Flame, ChevronLeft, ChevronRight } from 'lucide-react'
import { CATEGORY_COLORS, POMODORO_SIZES, type TodoV2, type WeekPlanData } from '../../api/client'
import GanttBar from '../../components/GanttBar'
import TimeAxis from '../../components/TimeAxis'
import { PRIORITY_COLORS, WEEKDAY_LABELS, fmtDate, fmtHM, dayMin } from './weekPlanUtils'

interface DayViewProps {
  selectedDate: string
  weekPlan: WeekPlanData
  weekStart: string
  dragId: number | null
  setSelectedDate: (v: string) => void
  setWeekStart: (v: string) => void
  openDetail: (todo: TodoV2) => void
  startFocus: (id: number) => void
  handleDragStart: (todo: TodoV2) => (e: React.DragEvent) => void
  handleDragEnd: () => void
  setShowCreateModal: (v: boolean) => void
  getWeekStart: (d: Date) => string
}

export default function DayView({
  selectedDate, weekPlan, weekStart, dragId,
  setSelectedDate, setWeekStart, openDetail, startFocus,
  handleDragStart, handleDragEnd, setShowCreateModal, getWeekStart,
}: DayViewProps) {
  const allTasks = (weekPlan.day_tasks[selectedDate] || []).slice().sort((a, b) => (a.priority || 3) - (b.priority || 3) || a.id - b.id)
  const isToday = selectedDate === new Date().toISOString().slice(0, 10)
  const shiftDay = (delta: number) => {
    const d = new Date(selectedDate + 'T00:00:00')
    d.setDate(d.getDate() + delta)
    const ns = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
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
        <button onClick={() => { const today = new Date(); const ts = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`; setSelectedDate(ts); setWeekStart(getWeekStart(today)) }} className="px-2 py-1 text-xs rounded-lg bg-cd-bg-input text-cd-text-secondary hover:bg-cd-hover transition ml-1">今天</button>
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
                      priorityColor={PRIORITY_COLORS[(t.priority || 3) - 1]}
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
