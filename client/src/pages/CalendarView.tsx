import { useState, useEffect, useCallback } from 'react'
import { ChevronLeft, ChevronRight, CalendarDays } from 'lucide-react'
import { getCalendarView, type CalendarViewData, type CalendarDay } from '../api/client'
import dayjs from 'dayjs'

const LEVEL_OPACITY = [0.08, 0.35, 0.55, 0.75, 1.0]
const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

export default function CalendarView() {
  const [month, setMonth] = useState<dayjs.Dayjs>(dayjs())
  const [data, setData] = useState<CalendarViewData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hoverDay, setHoverDay] = useState<CalendarDay | null>(null)

  const load = useCallback(async (m: dayjs.Dayjs) => {
    setLoading(true)
    setError(null)
    try {
      const res = await getCalendarView(m.format('YYYY-MM'))
      setData(res)
    } catch (e) {
      setError('加载失败')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load(month) }, [month, load])

  // 构建月度网格（含前置占位）
  const grid = buildMonthGrid(month)

  // 按日期索引数据
  const dayMap: Record<string, CalendarDay> = {}
  data?.days.forEach(d => { dayMap[d.date] = d })

  // 分类颜色映射（从 legend 取）
  const catColorMap: Record<string, string> = {}
  data?.legend.forEach(l => { catColorMap[l.cat] = l.color })

  const prevMonth = () => setMonth(m => m.subtract(1, 'month'))
  const nextMonth = () => setMonth(m => m.add(1, 'month'))
  const goToday = () => setMonth(dayjs())

  // 月度总览
  const totalMin = data?.days.reduce((s, d) => s + d.total_min, 0) ?? 0
  const activeDays = data?.days.filter(d => d.total_min > 0).length ?? 0
  const avgMin = activeDays > 0 ? Math.round(totalMin / activeDays) : 0

  return (
    <div className="min-h-screen p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <CalendarDays className="text-cd-accent" size={24} /> 日历视图
        </h1>
        <button onClick={goToday}
          className="px-3 py-1.5 text-sm bg-cd-bg-card border border-white/5 rounded-lg text-cd-text-secondary hover:text-cd-text transition">
          回到今天
        </button>
      </div>

      {/* 月份切换 */}
      <div className="flex items-center justify-between mb-4">
        <button onClick={prevMonth}
          className="p-2 rounded-lg bg-cd-bg-card border border-white/5 text-cd-text-secondary hover:text-cd-text hover:bg-white/5 transition">
          <ChevronLeft size={18} />
        </button>
        <div className="text-lg font-semibold text-cd-text tabular-nums">
          {month.format('YYYY 年 M 月')}
        </div>
        <button onClick={nextMonth}
          className="p-2 rounded-lg bg-cd-bg-card border border-white/5 text-cd-text-secondary hover:text-cd-text hover:bg-white/5 transition">
          <ChevronRight size={18} />
        </button>
      </div>

      {/* 月度总览 */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-gold">{Math.floor(totalMin / 60)}<span className="text-sm font-normal text-cd-text-tertiary ml-1">小时</span></div>
          <div className="text-sm text-cd-text-secondary mt-1">本月专注</div>
        </div>
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-cd-accent">{activeDays}<span className="text-sm font-normal text-cd-text-tertiary ml-1">天</span></div>
          <div className="text-sm text-cd-text-secondary mt-1">活跃天数</div>
        </div>
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-green-400">{avgMin}<span className="text-sm font-normal text-cd-text-tertiary ml-1">分钟</span></div>
          <div className="text-sm text-cd-text-secondary mt-1">日均专注</div>
        </div>
      </div>

      {/* 日历网格 */}
      <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4">
        {loading ? (
          <div className="text-center py-16 text-cd-text-secondary text-sm">加载中…</div>
        ) : error ? (
          <div className="text-center py-16 text-red-400 text-sm">{error}</div>
        ) : (
          <>
            {/* 星期表头 */}
            <div className="grid grid-cols-7 gap-2 mb-2">
              {WEEKDAYS.map(w => (
                <div key={w} className="text-center text-xs text-cd-text-tertiary py-1">{w}</div>
              ))}
            </div>
            {/* 日期网格 */}
            <div className="grid grid-cols-7 gap-2">
              {grid.map((d, i) => {
                if (!d) {
                  return <div key={i} className="aspect-square rounded-lg bg-transparent" />
                }
                const dayData = dayMap[d.format('YYYY-MM-DD')]
                const level = dayData?.level ?? 0
                const dom = dayData?.dominant_cat
                const color = dom ? (catColorMap[dom] || '#6b7280') : '#6b7280'
                const isToday = d.format('YYYY-MM-DD') === dayjs().format('YYYY-MM-DD')
                const inMonth = d.month() === month.month()
                return (
                  <div
                    key={i}
                    onMouseEnter={() => dayData && setHoverDay(dayData)}
                    onMouseLeave={() => setHoverDay(null)}
                    className={`aspect-square rounded-lg border flex flex-col items-center justify-center cursor-default transition relative ${
                      isToday ? 'border-cd-accent/60 ring-1 ring-cd-accent/30' : 'border-white/5'
                    } ${inMonth ? '' : 'opacity-40'}`}
                    style={level > 0 ? {
                      backgroundColor: hexWithOpacity(color, LEVEL_OPACITY[level]),
                    } : {
                      backgroundColor: 'rgba(255,255,255,0.02)',
                    }}
                  >
                    <span className={`text-xs ${level > 0 ? 'text-cd-text font-medium' : 'text-cd-text-tertiary'}`}>
                      {d.date()}
                    </span>
                    {level > 0 && dayData && (
                      <span className="text-[9px] text-cd-text-secondary mt-0.5 leading-none">
                        {Math.floor(dayData.total_min / 60) > 0 ? `${Math.floor(dayData.total_min / 60)}h` : `${dayData.total_min}m`}
                      </span>
                    )}
                    {dom && level > 0 && (
                      <span className="text-[8px] text-cd-text-tertiary mt-0.5 leading-none truncate max-w-full px-1">
                        {dom}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* 图例 */}
      {data && data.legend.length > 0 && (
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4">
          <h3 className="text-sm text-cd-text-secondary mb-3">分类图例</h3>
          <div className="flex flex-wrap gap-3">
            {data.legend.map(l => (
              <div key={l.cat} className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded" style={{ backgroundColor: l.color }} />
                <span className="text-xs text-cd-text-secondary">{l.cat}</span>
                <span className="text-xs text-cd-text-tertiary">
                  {Math.floor((data.category_totals[l.cat] || 0) / 60)}h
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 悬浮详情 */}
      {hoverDay && (
        <div className="fixed bottom-6 right-6 bg-cd-bg-card border border-white/10 rounded-lg p-3 shadow-xl max-w-xs z-30">
          <div className="text-sm font-medium text-cd-text mb-1">{hoverDay.date}</div>
          <div className="text-xs text-cd-text-secondary mb-2">
            总专注 {Math.floor(hoverDay.total_min / 60)}h {hoverDay.total_min % 60}m
          </div>
          {Object.entries(hoverDay.cats).sort((a, b) => b[1] - a[1]).map(([cat, min]) => (
            <div key={cat} className="flex items-center justify-between text-xs py-0.5">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded" style={{ backgroundColor: catColorMap[cat] || '#6b7280' }} />
                <span className="text-cd-text-secondary">{cat}</span>
              </span>
              <span className="text-cd-text-tertiary tabular-nums">{min}m</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** 构建月度网格（周一开头，含前置空格） */
function buildMonthGrid(month: dayjs.Dayjs): (dayjs.Dayjs | null)[] {
  const first = month.startOf('month')
  const daysInMonth = month.daysInMonth()
  // 周一为一周第一天：dayjs day() 周日=0, 周一=1...
  const firstDayWeekday = first.day() === 0 ? 6 : first.day() - 1
  const grid: (dayjs.Dayjs | null)[] = []
  for (let i = 0; i < firstDayWeekday; i++) grid.push(null)
  for (let d = 1; d <= daysInMonth; d++) {
    grid.push(month.date(d))
  }
  // 补齐到 7 的倍数
  while (grid.length % 7 !== 0) grid.push(null)
  return grid
}

/** hex 颜色加透明度 */
function hexWithOpacity(hex: string, opacity: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.substring(0, 2), 16)
  const g = parseInt(h.substring(2, 4), 16)
  const b = parseInt(h.substring(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${opacity})`
}
