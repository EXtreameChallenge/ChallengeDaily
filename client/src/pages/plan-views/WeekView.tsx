import { Search, Plus, Play, Target } from 'lucide-react'
import { CATEGORY_COLORS, POMODORO_SIZES, type TodoV2, type WeekPlanData } from '../../api/client'
import { TaskCard } from './weekPlanComponents'
import {
  DAILY_LIMIT, PRIORITY_COLORS, WEEKDAY_LABELS,
  getTodayStr, fmtDate, isWeekend, dayMin, fmtHM,
} from './weekPlanUtils'

interface WeekViewProps {
  weekPlan: WeekPlanData
  dates: string[]
  unassigned: TodoV2[]
  searchQuery: string
  setSearchQuery: (v: string) => void
  dragId: number | null
  dragOverCol: string | null
  expandedTaskId: number | null
  handleDragStart: (todo: TodoV2) => (e: React.DragEvent) => void
  handleDragEnd: () => void
  handleDragOver: (col: string) => (e: React.DragEvent) => void
  handleDragLeave: (col: string) => () => void
  handleDropDay: (date: string) => (e: React.DragEvent) => void
  handleDropUnassigned: (e: React.DragEvent) => void
  openDetail: (todo: TodoV2) => void
  startFocus: (id: number) => void
  setShowCreateModal: (v: boolean) => void
  toggleExpand: (id: number) => void
}

export default function WeekView({
  weekPlan, dates, unassigned, searchQuery, setSearchQuery,
  dragId, dragOverCol, expandedTaskId,
  handleDragStart, handleDragEnd, handleDragOver, handleDragLeave,
  handleDropDay, handleDropUnassigned, openDetail, startFocus, setShowCreateModal, toggleExpand,
}: WeekViewProps) {
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
          ) : ganttRows.map(({ task: t, date }) => {
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
                  background: 'color-mix(in srgb, var(--cd-bg-tertiary) 30%, transparent)',
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
