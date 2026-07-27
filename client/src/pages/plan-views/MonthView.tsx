import { CalendarDays, Target } from 'lucide-react'
import { CATEGORY_COLORS, type MonthPlanData, type MonthPlanStats, type TodoV2 } from '../../api/client'
import GanttBar from '../../components/GanttBar'
import TimeAxis from '../../components/TimeAxis'

interface MonthViewProps {
  monthKey: string
  monthPlan: MonthPlanData
  monthStats: MonthPlanStats | null
  monthGoalDraft: string
  setMonthGoalDraft: (v: string) => void
  saveMonthGoal: () => void
  openDetail: (todo: TodoV2) => void
}

export default function MonthView({
  monthKey, monthPlan, monthStats, monthGoalDraft, setMonthGoalDraft, saveMonthGoal, openDetail,
}: MonthViewProps) {
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
