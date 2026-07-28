import { useState, useCallback, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getActivities, CATEGORY_COLORS, request, type Activity } from '../api/client'
import { useAsyncData, ApiErrorDisplay } from '../components/shared'
import SankeyChart from '../components/SankeyChart'
import dayjs from 'dayjs'

type HeatRange = 'week' | 'month' | 'year'
type SubTab = 'heatmap' | 'ranking'
interface HeatCell { date: string; focus_min: number; level: number }
interface YearStats {
  total_active_days: number
  total_focus_min: number
  total_focus_hour: number
  avg_daily_min: number
  current_streak: number
  longest_streak: number
}

export default function Heatmap() {
  const [tooltip, setTooltip] = useState<{ day: string; hour: number; val: number } | null>(null)
  const [weekOffset, setWeekOffset] = useState(0)
  const [range, setRange] = useState<HeatRange>('week')
  const [subTab, setSubTab] = useState<SubTab>('heatmap')
  // 月/年视图基准日期（仅在 month/year 模式下使用）
  const [baseDate, setBaseDate] = useState<dayjs.Dayjs>(dayjs())
  const [heatmapData, setHeatmapData] = useState<HeatCell[]>([])
  const [heatmapLoading, setHeatmapLoading] = useState(false)
  const [heatmapError, setHeatmapError] = useState<string | null>(null)
  const [yearStats, setYearStats] = useState<YearStats | null>(null)
  const [hoverCell, setHoverCell] = useState<HeatCell | null>(null)
  const navigate = useNavigate()

  const getMondayOfWeek = (d: dayjs.Dayjs) => {
    const day = d.day()
    const diff = day === 0 ? 6 : day - 1
    return d.subtract(diff, 'day').startOf('day')
  }

  const { data: rawActivities, loading, error, refresh: refreshData } = useAsyncData(async () => {
    const today = dayjs().add(weekOffset, 'week')
    const monday = getMondayOfWeek(today)
    const dates = Array.from({ length: 7 }, (_, d) =>
      monday.add(d, 'day').format('YYYY-MM-DD')
    )
    const results = await Promise.allSettled(
      dates.map(d => getActivities(d))
    )
    const allActs: Activity[] = []
    results.forEach(r => {
      if (r.status === 'fulfilled') allActs.push(...r.value.activities)
    })
    return allActs
  }, [weekOffset])
  const activities = rawActivities ?? []

  // 月/年视图：拉取聚合热力图数据
  useEffect(() => {
    if (range === 'week') {
      setHeatmapData([])
      setYearStats(null)
      return
    }
    let cancelled = false
    setHeatmapLoading(true)
    setHeatmapError(null)
    setHoverCell(null)
    const dateStr = baseDate.format('YYYY-MM-DD')
    request(`/api/stats/heatmap?range=${range}&date=${dateStr}`, undefined, 15000)
      .then((res: any) => {
        if (cancelled) return
        setHeatmapData((res?.data ?? []) as HeatCell[])
        setYearStats((res?.stats ?? null) as YearStats | null)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setHeatmapError(e instanceof Error ? e.message : '加载失败')
      })
      .finally(() => {
        if (!cancelled) setHeatmapLoading(false)
      })
    return () => { cancelled = true }
  }, [range, baseDate])

  const today = dayjs().add(weekOffset, 'week')
  const monday = getMondayOfWeek(today)
  const days = useMemo(() =>
    Array.from({ length: 7 }, (_, i) => monday.add(i, 'day')),
    [monday.valueOf()]
  )
  const weekdayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

  // Stable grid data — only recalculates when activities change
  const gridData = useMemo(() => {
    return days.map((day) => {
      const dayStr = day.format('YYYY-MM-DD')
      const dayActs = activities.filter((a) => dayjs(a.timestamp).format('YYYY-MM-DD') === dayStr)
      return Array.from({ length: 24 }, (_, h) => {
        const hourActs = dayActs.filter((a) => dayjs(a.timestamp).hour() === h)
        return hourActs.reduce((sum, a) => sum + (a.duration_min || 0), 0)
      })
    })
  }, [days, activities])

  const maxVal = useMemo(() => Math.max(...gridData.flat(), 1), [gridData])
  const totalMin = useMemo(() => gridData.flat().reduce((s, v) => s + v, 0), [gridData])
  const peakH = useMemo(() => {
    const peakHour = gridData[0].map((_, h) => gridData.reduce((s, dayData) => s + dayData[h], 0))
    return peakHour.indexOf(Math.max(...peakHour))
  }, [gridData])

  const handleCellEnter = useCallback((day: string, hour: number, val: number) => {
    setTooltip({ day, hour, val: Math.round(val) })
  }, [])
  const handleCellLeave = useCallback(() => {
    setTooltip(null)
  }, [])

  // 月/年视图：构建完整日期格子（含无数据日期，level=0）
  const monthYearCells = useMemo<HeatCell[]>(() => {
    if (range === 'week' || heatmapData.length === 0) return []
    const dataMap = new Map(heatmapData.map(d => [d.date, d]))
    const cells: HeatCell[] = []
    if (range === 'year') {
      const year = baseDate.year()
      const start = dayjs(`${year}-01-01`)
      const end = dayjs(`${year}-12-31`)
      let cur = start
      while (cur.isBefore(end) || cur.isSame(end, 'day')) {
        const ds = cur.format('YYYY-MM-DD')
        const d = dataMap.get(ds)
        cells.push(d ?? { date: ds, focus_min: 0, level: 0 })
        cur = cur.add(1, 'day')
      }
    } else {
      // month
      const start = baseDate.startOf('month')
      const end = baseDate.endOf('month')
      let cur = start
      while (cur.isBefore(end) || cur.isSame(end, 'day')) {
        const ds = cur.format('YYYY-MM-DD')
        const d = dataMap.get(ds)
        cells.push(d ?? { date: ds, focus_min: 0, level: 0 })
        cur = cur.add(1, 'day')
      }
    }
    return cells
  }, [range, heatmapData, baseDate])

  const monthYearTotalMin = useMemo(
    () => monthYearCells.reduce((s, c) => s + c.focus_min, 0),
    [monthYearCells]
  )

  // P6-3: GitHub 风格年视图 — 月份标签位置（列偏移）
  const monthLabels = useMemo<{ label: string; col: number }[]>(() => {
    if (range !== 'year' || monthYearCells.length === 0) return []
    const labels: { label: string; col: number }[] = []
    const jan1 = dayjs(`${baseDate.year()}-01-01`)
    // Monday-based weekday of Jan 1 (0=Mon, 6=Sun)
    const jan1Dow = (jan1.day() + 6) % 7
    for (let m = 0; m < 12; m++) {
      const firstOfMonth = jan1.add(m, 'month')
      const dayOfYear = firstOfMonth.diff(jan1, 'day')
      const col = Math.floor((dayOfYear + jan1Dow) / 7)
      labels.push({ label: `${m + 1}月`, col })
    }
    return labels
  }, [range, monthYearCells, baseDate])

  const goPrevRange = useCallback(() => {
    if (range === 'week') setWeekOffset((w) => Math.max(w - 1, -52))
    else if (range === 'month') setBaseDate((d) => d.subtract(1, 'month'))
    else setBaseDate((d) => d.subtract(1, 'year'))
  }, [range])

  const goNextRange = useCallback(() => {
    if (range === 'week') setWeekOffset((w) => Math.min(w + 1, 0))
    else if (range === 'month') {
      // 不超过当前月
      setBaseDate((d) => {
        const next = d.add(1, 'month')
        return next.isAfter(dayjs(), 'month') ? d : next
      })
    } else {
      setBaseDate((d) => {
        const next = d.add(1, 'year')
        return next.isAfter(dayjs(), 'year') ? d : next
      })
    }
  }, [range])

  const rangeLabel = useMemo(() => {
    if (range === 'week') return `${days[0].format('MM/DD')} - ${days[6].format('MM/DD')}`
    if (range === 'month') return baseDate.format('YYYY-MM')
    return baseDate.format('YYYY')
  }, [range, days, baseDate])

  const cellColor = (level: number) => {
    if (level === 0) return 'var(--cd-bg-tertiary)'
    return `rgba(34, 197, 94, ${0.2 + level * 0.2})`
  }

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-cd-text">时段热力图</h1>
          {/* 子标签：热力图 / 排行榜 */}
          <div className="flex items-center rounded-lg border border-cd-border overflow-hidden">
            {([['heatmap', '热力图'], ['ranking', '排行榜']] as [SubTab, string][]).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setSubTab(key)}
                className={`px-3 py-1 text-xs transition-colors ${
                  subTab === key
                    ? 'bg-cd-green/30 text-cd-green'
                    : 'bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {subTab === 'heatmap' ? (
        <div className="flex items-center gap-2 flex-wrap">
          {/* 范围切换器 */}
          <div className="flex items-center rounded-lg border border-cd-border overflow-hidden">
            {(['week', 'month', 'year'] as HeatRange[]).map((r) => (
              <button
                key={r}
                onClick={() => setRange(r)}
                className={`px-3 py-1 text-xs transition-colors ${
                  range === r
                    ? 'bg-cd-purple/30 text-cd-purple'
                    : 'bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover'
                }`}
              >
                {r === 'week' ? '周' : r === 'month' ? '月' : '年'}
              </button>
            ))}
          </div>
          <button
            onClick={goPrevRange}
            className="px-3 py-1 text-xs rounded-lg bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
          >
            {range === 'week' ? '上一周' : range === 'month' ? '上一月' : '上一年'}
          </button>
          <span className="text-xs text-cd-text-secondary font-medium px-2 min-w-[90px] text-center">
            {rangeLabel}
          </span>
          <button
            onClick={goNextRange}
            disabled={
              range === 'week'
                ? weekOffset >= 0
                : (range === 'month' ? !baseDate.isBefore(dayjs(), 'month') : !baseDate.isBefore(dayjs(), 'year'))
            }
            className="px-3 py-1 text-xs rounded-lg bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
          >
            {range === 'week' ? '下一周' : range === 'month' ? '下一月' : '下一年'}
          </button>
        </div>
        ) : null}
      </div>

      {/* ─── 热力图内容 ──────────────────────── */}
      {subTab === 'heatmap' && (
      <>
      <div className="grid grid-cols-3 gap-4">
        {range === 'week' ? (
          <>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">{(totalMin / 60).toFixed(1)}</div>
              <div className="text-xs text-cd-text-tertiary mt-1">本周总时长 (h)</div>
            </div>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">{totalMin > 0 ? Math.round(totalMin / 7) : 0}</div>
              <div className="text-xs text-cd-text-tertiary mt-1">日均时长 (min)</div>
            </div>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">{peakH}:00</div>
              <div className="text-xs text-cd-text-tertiary mt-1">最活跃时段</div>
            </div>
          </>
        ) : range === 'year' && yearStats ? (
          <>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">{yearStats.total_focus_hour}</div>
              <div className="text-xs text-cd-text-tertiary mt-1">本年总时长 (h)</div>
            </div>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">
                {yearStats.current_streak}<span className="text-sm text-cd-text-tertiary"> / {yearStats.longest_streak}</span>
              </div>
              <div className="text-xs text-cd-text-tertiary mt-1">当前连续 / 最长连续 (天)</div>
            </div>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">{yearStats.total_active_days}</div>
              <div className="text-xs text-cd-text-tertiary mt-1">活跃天数 / 365</div>
            </div>
          </>
        ) : (
          <>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">{(monthYearTotalMin / 60).toFixed(1)}</div>
              <div className="text-xs text-cd-text-tertiary mt-1">{range === 'year' ? '本年总时长 (h)' : '本月总时长 (h)'}</div>
            </div>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">
                {monthYearTotalMin > 0 ? Math.round(monthYearTotalMin / monthYearCells.length) : 0}
              </div>
              <div className="text-xs text-cd-text-tertiary mt-1">日均专注 (min)</div>
            </div>
            <div className="card text-center">
              <div className="text-xl font-bold text-cd-green font-display">
                {monthYearCells.filter((c) => c.level > 0).length}
              </div>
              <div className="text-xs text-cd-text-tertiary mt-1">活跃天数</div>
            </div>
          </>
        )}
      </div>

      {/* ─── 热力图网格 ────────────────────── */}
      {range === 'week' ? (
        <div className="card">
          {error ? (
            <ApiErrorDisplay error={error} onRetry={refreshData} />
          ) : loading ? (
            <div className="text-center py-8 text-cd-text-tertiary animate-pulse">加载中...</div>
          ) : (
            <>
              {/* 小时标题 */}
              <div className="flex items-center gap-[3px] mb-2 pl-16">
                {Array.from({ length: 24 }, (_, h) => (
                  <div key={h} className="flex-1 text-center text-[9px] text-cd-text-tertiary">
                    {h % 3 === 0 ? `${h}` : ''}
                  </div>
                ))}
              </div>

              {/* 每天 */}
              <div className="space-y-[3px]">
                {days.map((day, di) => (
                  <div key={di} className="flex items-center gap-[3px]">
                    <div className="w-14 text-right text-[11px] text-cd-text-tertiary shrink-0 pr-1">
                      {weekdayNames[di]}
                      <div className="text-[9px]">{day.format('MM/DD')}</div>
                    </div>
                    <div className="flex gap-[3px] flex-1">
                      {gridData[di].map((val, h) => {
                        const intensity = val / maxVal
                        return (
                          <div
                            key={h}
                            className="flex-1 aspect-square rounded-sm cursor-pointer heatmap-cell"
                            style={{
                              background:
                                val === 0
                                  ? 'var(--cd-bg-tertiary)'
                                  : `rgba(99,91,255,${0.15 + intensity * 0.75})`,
                            }}
                            onMouseEnter={() => handleCellEnter(`${weekdayNames[di]} ${day.format('MM/DD')}`, h, val)}
                            onMouseLeave={handleCellLeave}
                          />
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>

              {/* 悬浮提示 — 始终占位，避免卡片高度抖动 */}
              <div className="mt-3 text-xs text-cd-text-secondary min-h-[1.25em]">
                {tooltip ? (
                  <>
                    {tooltip.day} {tooltip.hour}:00 - 
                    <span className="text-cd-green font-medium ml-1">
                      {tooltip.val > 0 ? `${tooltip.val} 分钟` : '无记录'}
                    </span>
                  </>
                ) : (
                  <span className="text-cd-text-tertiary">将鼠标悬停在方格上查看详情</span>
                )}
              </div>

              {/* 图例 */}
              <div className="flex items-center gap-2 mt-4 justify-center">
                <span className="text-[10px] text-cd-text-tertiary">低</span>
                {[0, 0.25, 0.5, 0.75, 1].map((v, i) => (
                  <div
                    key={i}
                    className="w-4 h-4 rounded-sm"
                    style={{
                      background: v === 0 ? 'var(--cd-bg-tertiary)' : `rgba(99,91,255,${0.15 + v * 0.75})`,
                    }}
                  />
                ))}
                <span className="text-[10px] text-cd-text-tertiary">高</span>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="card">
          {heatmapError ? (
            <ApiErrorDisplay error={heatmapError} onRetry={() => setBaseDate((d) => d)} />
          ) : heatmapLoading ? (
            <div className="text-center py-8 text-cd-text-tertiary animate-pulse">加载中...</div>
          ) : monthYearCells.length === 0 ? (
            <div className="text-center py-8 text-cd-text-tertiary">暂无数据</div>
          ) : range === 'year' ? (
            <>
              <h2 className="text-sm font-semibold text-cd-text mb-3">
                {baseDate.format('YYYY')} 年专注热力图（GitHub 风格，点击查看当日时间线）
              </h2>
              {/* GitHub 风格：月份标签 + 星期标签 + 53 列 × 7 行 */}
              <div className="overflow-x-auto">
                <div className="inline-block">
                  {/* 月份标签行 */}
                  <div className="flex pl-8 mb-1" style={{ gap: '3px' }}>
                    {monthLabels.map((ml, i) => (
                      <div
                        key={i}
                        className="text-[10px] text-cd-text-tertiary"
                        style={{ marginLeft: i === 0 ? 0 : `${(ml.col - (monthLabels[i - 1]?.col ?? 0)) * 15 - 15}px` }}
                      >
                        {ml.label}
                      </div>
                    ))}
                  </div>
                  <div className="flex gap-1">
                    {/* 星期标签列 */}
                    <div className="flex flex-col gap-[3px] mr-1 pt-[1px]">
                      {['', '一', '', '三', '', '五', ''].map((w, i) => (
                        <div key={i} className="h-3 text-[9px] text-cd-text-tertiary flex items-center justify-end pr-1" style={{ width: '20px' }}>
                          {w}
                        </div>
                      ))}
                    </div>
                    {/* 热力图格子：53 列 × 7 行 */}
                    <div
                      className="grid gap-[3px]"
                      style={{ gridTemplateRows: 'repeat(7, 1fr)', gridAutoFlow: 'column', width: 'fit-content' }}
                    >
                      {monthYearCells.map((cell) => (
                        <div
                          key={cell.date}
                          className="w-3 h-3 rounded-sm cursor-pointer transition-all hover:ring-1 hover:ring-cd-purple"
                          style={{
                            backgroundColor: cellColor(cell.level),
                            outline: hoverCell?.date === cell.date ? '1.5px solid var(--cd-purple)' : 'none',
                          }}
                          onMouseEnter={() => setHoverCell(cell)}
                          onMouseLeave={() => setHoverCell(null)}
                          onClick={() => navigate(`/timeline?date=${cell.date}`)}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              {/* 悬浮提示 */}
              <div className="mt-3 text-xs text-cd-text-secondary min-h-[1.25em]">
                {hoverCell ? (
                  <>
                    <span className="text-cd-text">{hoverCell.date}</span>{' '}
                    <span className="text-cd-text-tertiary">({weekdayNames[(dayjs(hoverCell.date).day() + 6) % 7]})</span>{' '}
                    <span className="text-cd-green font-medium ml-1">
                      {hoverCell.focus_min > 0 ? `${hoverCell.focus_min} 分钟专注` : '无记录'}
                    </span>
                  </>
                ) : (
                  <span className="text-cd-text-tertiary">将鼠标悬停在方格上查看详情，点击跳转到当日时间线</span>
                )}
              </div>
            </>
          ) : (
            <>
              <h2 className="text-sm font-semibold text-cd-text mb-3">
                {baseDate.format('YYYY-MM')} 月专注热力图（点击查看当日时间线）
              </h2>
              <div className="grid grid-cols-7 gap-1.5">
                {/* 星期表头 */}
                {weekdayNames.map((w) => (
                  <div key={w} className="text-center text-[10px] text-cd-text-tertiary pb-1">{w}</div>
                ))}
                {/* 月初空白对齐（按周一对齐） */}
                {Array.from({ length: (() => { const d = dayjs(baseDate).startOf('month').day(); return d === 0 ? 6 : d - 1 })() }, (_, i) => (
                  <div key={`pad-${i}`} />
                ))}
                {monthYearCells.map((cell) => (
                  <div
                    key={cell.date}
                    className="aspect-square rounded-sm cursor-pointer hover:ring-1 hover:ring-cd-purple flex items-center justify-center text-[9px] transition-all"
                    style={{
                      backgroundColor: cellColor(cell.level),
                      outline: hoverCell?.date === cell.date ? '1.5px solid var(--cd-purple)' : 'none',
                    }}
                    onMouseEnter={() => setHoverCell(cell)}
                    onMouseLeave={() => setHoverCell(null)}
                    onClick={() => navigate(`/timeline?date=${cell.date}`)}
                  >
                    <span className={cell.level > 0 ? 'text-white/80' : 'text-cd-text-tertiary'}>
                      {dayjs(cell.date).date()}
                    </span>
                  </div>
                ))}
              </div>
              <div className="mt-3 text-xs text-cd-text-secondary min-h-[1.25em]">
                {hoverCell ? (
                  <>
                    <span className="text-cd-text">{hoverCell.date}</span>{' '}
                    <span className="text-cd-green font-medium ml-1">
                      {hoverCell.focus_min > 0 ? `${hoverCell.focus_min} 分钟专注` : '无记录'}
                    </span>
                  </>
                ) : (
                  <span className="text-cd-text-tertiary">将鼠标悬停在方格上查看详情，点击跳转到当日时间线</span>
                )}
              </div>
            </>
          )}
          {/* 月/年视图图例 */}
          <div className="flex items-center gap-2 mt-4 justify-center">
            <span className="text-[10px] text-cd-text-tertiary">少</span>
            {[0, 1, 2, 3, 4].map((lv) => (
              <div
                key={lv}
                className="w-4 h-4 rounded-sm"
                style={{ backgroundColor: cellColor(lv) }}
              />
            ))}
            <span className="text-[10px] text-cd-text-tertiary">多</span>
          </div>
        </div>
        )}

      {/* ─── 分类时段分布 ──────────────────── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-cd-text mb-3">分类时段分布</h2>
        <div className="space-y-2">
          {Object.entries(CATEGORY_COLORS).slice(0, 8).map(([cat, color]) => {
            const catMin = activities
              .filter((a) => a.category === cat)
              .reduce((s, a) => s + (a.duration_min || 0), 0)
            if (catMin === 0) return null
            const pct = totalMin > 0 ? (catMin / totalMin) * 100 : 0
            return (
              <div key={cat} className="flex items-center gap-3">
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ background: color }}
                />
                <span className="text-xs text-cd-text w-16 shrink-0">{cat}</span>
                <div className="flex-1 progress-bar">
                  <div
                    className="progress-bar-fill"
                    style={{ width: `${Math.max(pct, 2)}%`, background: color }}
                  />
                </div>
                <span className="text-xs text-cd-text-tertiary w-12 text-right shrink-0">
                  {Math.round(catMin)}min
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* P7-4: 桑基图（仅周视图显示当天数据） */}
      {range === 'week' && (
        <SankeyChart date={days[0].format('YYYY-MM-DD')} />
      )}
      </>
      )}

      {/* ── 排行榜子标签 ── */}
      {subTab === 'ranking' && (
        <RankingView activities={activities} totalMin={totalMin} />
      )}
    </div>
  )
}

/** 排行榜视图：应用时长排行 + 分类占比排行 */
function RankingView({ activities, totalMin }: { activities: Activity[]; totalMin: number }) {
  const appRank = useMemo(() => {
    const map: Record<string, { name: string; min: number; cat: string }> = {}
    for (const a of activities) {
      const key = a.app_name || a.window_title || '未知'
      if (!map[key]) map[key] = { name: key, min: 0, cat: a.category || '其他' }
      map[key].min += a.duration_min || 0
    }
    return Object.values(map).sort((a, b) => b.min - a.min)
  }, [activities])

  const catRank = useMemo(() => {
    const map: Record<string, { name: string; min: number }> = {}
    for (const a of activities) {
      const key = a.category || '其他'
      if (!map[key]) map[key] = { name: key, min: 0 }
      map[key].min += a.duration_min || 0
    }
    return Object.values(map).sort((a, b) => b.min - a.min)
  }, [activities])

  const maxAppMin = appRank.length > 0 ? appRank[0].min : 1

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* 应用使用排行 */}
      <div className="bg-cd-bg-card rounded-xl p-4 border border-cd-border">
        <h3 className="text-sm font-medium text-cd-text mb-3">应用使用排行</h3>
        {appRank.length === 0 ? (
          <p className="text-xs text-cd-text-tertiary text-center py-8">暂无数据</p>
        ) : (
          <div className="space-y-2">
            {appRank.slice(0, 15).map((app, i) => (
              <div key={app.name} className="flex items-center gap-2">
                <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold shrink-0 ${
                  i < 3 ? 'bg-cd-green/20 text-cd-green' : 'bg-cd-bg-tertiary text-cd-text-tertiary'
                }`}>{i + 1}</span>
                <span className="text-xs text-cd-text flex-1 truncate">{app.name}</span>
                <div className="w-20 progress-bar shrink-0">
                  <div className="progress-bar-fill" style={{ width: `${(app.min / maxAppMin) * 100}%` }} />
                </div>
                <span className="text-xs text-cd-text-tertiary w-12 text-right shrink-0 tabular-nums">
                  {Math.round(app.min)}min
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 分类时长排行 */}
      <div className="bg-cd-bg-card rounded-xl p-4 border border-cd-border">
        <h3 className="text-sm font-medium text-cd-text mb-3">分类时长排行</h3>
        {catRank.length === 0 ? (
          <p className="text-xs text-cd-text-tertiary text-center py-8">暂无数据</p>
        ) : (
          <div className="space-y-2">
            {catRank.map((cat, i) => {
              const pct = totalMin > 0 ? (cat.min / totalMin) * 100 : 0
              return (
                <div key={cat.name} className="flex items-center gap-2">
                  <span className={`w-5 h-5 rounded flex items-center justify-center text-[10px] font-bold shrink-0 ${
                    i < 3 ? 'bg-cd-green/20 text-cd-green' : 'bg-cd-bg-tertiary text-cd-text-tertiary'
                  }`}>{i + 1}</span>
                  <span className="text-xs text-cd-text flex-1">{cat.name}</span>
                  <div className="w-20 progress-bar shrink-0">
                    <div className="progress-bar-fill" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-xs text-cd-text-tertiary w-12 text-right shrink-0 tabular-nums">
                    {Math.round(cat.min)}min
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
