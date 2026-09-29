import { useState, useEffect } from 'react'
import { request } from '../api/client'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface CalendarDay {
  date: string
  score: number
  grade: string
}

interface MonthStat {
  month: string
  avg_score: number
  best_score: number
  days_count: number
}

const GRADE_COLORS: Record<string, string> = {
  S: '#10b981',
  A: '#22c55e',
  B: '#60a5fa',
  C: '#f59e0b',
  D: '#ef4444',
}

const GRADE_BG: Record<string, string> = {
  S: 'bg-emerald-500/80',
  A: 'bg-green-500/70',
  B: 'bg-blue-400/60',
  C: 'bg-amber-400/50',
  D: 'bg-red-400/40',
}

const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日']

function getGradeColor(score: number): string {
  if (score >= 90) return GRADE_COLORS.S
  if (score >= 75) return GRADE_COLORS.A
  if (score >= 60) return GRADE_COLORS.B
  if (score >= 40) return GRADE_COLORS.C
  return GRADE_COLORS.D
}

export default function FocusScoreCalendar() {
  const [days, setDays] = useState<CalendarDay[]>([])
  const [monthStats, setMonthStats] = useState<MonthStat[]>([])
  const [loading, setLoading] = useState(true)
  const [hoveredDay, setHoveredDay] = useState<CalendarDay | null>(null)
  const [selectedMonth, setSelectedMonth] = useState<string>('')

  useEffect(() => {
    const fetchData = async () => {
      try {
        const result = await request('/api/stats/focus-score/calendar?months=3') as { days: CalendarDay[]; month_stats: MonthStat[] }
        setDays(result.days || [])
        setMonthStats(result.month_stats || [])
        if (result.month_stats && result.month_stats.length > 0) {
          setSelectedMonth(result.month_stats[result.month_stats.length - 1].month)
        }
      } catch {
        // silent
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="bg-cd-surface rounded-2xl p-5 border border-cd-border animate-pulse">
        <div className="h-5 bg-cd-surface-elevated rounded-lg w-40 mb-4" />
        <div className="grid grid-cols-7 gap-1.5">
          {Array.from({ length: 35 }).map((_, i) => (
            <div key={i} className="w-full aspect-square bg-cd-surface-elevated rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  if (days.length === 0) return null

  // 筛选选中月份的数据
  const monthDays = days.filter(d => d.date.startsWith(selectedMonth))
  const todayStr = new Date().toISOString().slice(0, 10)

  // 计算日历网格起始位置（周一开始）
  const firstDay = monthDays.length > 0 ? new Date(monthDays[0].date + 'T00:00:00') : new Date()
  const startOffset = (firstDay.getDay() + 6) % 7 // 周一=0, 周日=6

  // 构建日历网格
  const calendarCells: (CalendarDay | null)[] = []
  for (let i = 0; i < startOffset; i++) calendarCells.push(null)
  monthDays.forEach(d => calendarCells.push(d))
  while (calendarCells.length % 7 !== 0) calendarCells.push(null)

  const currentMonthStat = monthStats.find(m => m.month === selectedMonth)

  // 月份导航
  const monthIdx = monthStats.findIndex(m => m.month === selectedMonth)
  const prevMonth = monthIdx > 0 ? monthStats[monthIdx - 1].month : null
  const nextMonth = monthIdx < monthStats.length - 1 ? monthStats[monthIdx + 1].month : null

  return (
    <div className="bg-cd-surface rounded-2xl p-5 border border-cd-border">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-cd-text">Focus Score 日历</h3>
          {currentMonthStat && (
            <div className="flex items-center gap-2 text-xs text-cd-text-tertiary">
              <span>均分 <span className="text-cd-text font-medium">{currentMonthStat.avg_score}</span></span>
              <span>·</span>
              <span>最佳 <span className="text-cd-text font-medium">{currentMonthStat.best_score}</span></span>
            </div>
          )}
        </div>
        {/* Month navigation */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => prevMonth && setSelectedMonth(prevMonth)}
            disabled={!prevMonth}
            className="p-1 rounded-lg text-cd-text-tertiary hover:text-cd-text hover:bg-cd-surface-elevated disabled:opacity-30 transition"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="text-xs font-medium text-cd-text min-w-[60px] text-center">
            {selectedMonth ? `${selectedMonth.slice(0, 4)}年${parseInt(selectedMonth.slice(5))}月` : ''}
          </span>
          <button
            onClick={() => nextMonth && setSelectedMonth(nextMonth)}
            disabled={!nextMonth}
            className="p-1 rounded-lg text-cd-text-tertiary hover:text-cd-text hover:bg-cd-surface-elevated disabled:opacity-30 transition"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      </div>

      {/* Weekday labels */}
      <div className="grid grid-cols-7 gap-1.5 mb-1.5">
        {WEEKDAY_LABELS.map(wd => (
          <div key={wd} className="text-center text-[10px] text-cd-text-tertiary font-medium">{wd}</div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1.5">
        {calendarCells.map((cell, i) => {
          if (!cell) {
            return <div key={i} className="aspect-square" />
          }
          const isToday = cell.date === todayStr
          const color = getGradeColor(cell.score)
          const opacity = cell.score === 0 ? 0.15 : Math.max(0.3, cell.score / 100)

          return (
            <div
              key={i}
              className="aspect-square rounded-lg relative cursor-pointer transition hover:scale-110 hover:z-10"
              style={{
                backgroundColor: color,
                opacity: opacity,
                border: isToday ? '2px solid #fff' : 'none',
                boxShadow: isToday ? '0 0 0 2px rgba(255,255,255,0.3)' : 'none',
              }}
              onMouseEnter={() => setHoveredDay(cell)}
              onMouseLeave={() => setHoveredDay(null)}
            >
              <span className="absolute inset-0 flex items-center justify-center text-[9px] font-bold text-white/80">
                {parseInt(cell.date.slice(8))}
              </span>
              {/* Tooltip on hover */}
              {hoveredDay === cell && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-20 whitespace-nowrap px-2.5 py-1.5 rounded-2xl text-[11px] bg-black/90 text-white border border-white/10 shadow-lg pointer-events-none">
                  <div className="font-medium">{cell.date}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-lg leading-none" style={{ color }}>{cell.grade}</span>
                    <span>{cell.score.toFixed(0)} 分</span>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-3 mt-4">
        <span className="text-[10px] text-cd-text-tertiary">等级</span>
        {(['S', 'A', 'B', 'C', 'D'] as const).map(grade => (
          <div key={grade} className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-lg" style={{ backgroundColor: GRADE_COLORS[grade], opacity: 0.7 }} />
            <span className="text-[10px] text-cd-text-tertiary">{grade}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
