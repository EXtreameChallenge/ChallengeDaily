import { Layers, Target, Flame } from 'lucide-react'
import { CATEGORY_COLORS } from '../../api/client'
import type { WeekPlanStats, MonthPlanStats, TodoV2 } from '../../api/client'
import GanttBar from '../../components/GanttBar'
import TimeAxis from '../../components/TimeAxis'
import { MonthProgressBar } from './weekPlanComponents'
import {
  HEAT_COLORS, heatColor, formatLocalDate, getTodayStr, dayMin,
} from './weekPlanUtils'

interface YearViewProps {
  yearKey: number
  yearMonthStats: (MonthPlanStats | null)[]
  yearWeekStats: Map<string, WeekPlanStats>
  yearLoading: boolean
  yearGoal: string
  setYearGoal: (v: string) => void
  yearGoals: any[]
  getYearWeekStarts: (year: number) => string[]
}

export default function YearView({
  yearKey, yearMonthStats, yearWeekStats, yearLoading, yearGoal, setYearGoal, yearGoals, getYearWeekStarts,
}: YearViewProps) {
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
