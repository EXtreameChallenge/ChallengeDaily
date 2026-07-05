import { useState, useCallback, useMemo } from 'react'
import { getActivities, CATEGORY_COLORS, type Activity } from '../api/client'
import { useAsyncData, ApiErrorDisplay } from '../components/shared'
import dayjs from 'dayjs'

export default function Heatmap() {
  const [tooltip, setTooltip] = useState<{ day: string; hour: number; val: number } | null>(null)
  const [weekOffset, setWeekOffset] = useState(0)

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

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-cd-text">时段热力图</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setWeekOffset((w) => w - 1)}
            className="px-3 py-1 text-xs rounded-lg bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
          >
            上一周
          </button>
          <span className="text-xs text-cd-text-secondary font-medium px-2">
            {days[0].format('MM/DD')} - {days[6].format('MM/DD')}
          </span>
          <button
            onClick={() => setWeekOffset((w) => Math.min(w + 1, 0))}
            disabled={weekOffset >= 0}
            className="px-3 py-1 text-xs rounded-lg bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
          >
            下一周
          </button>
        </div>
      </div>

      {/* ─── 统计摘要 ──────────────────────── */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card text-center">
          <div className="text-xl font-bold text-cd-green">{(totalMin / 60).toFixed(1)}</div>
          <div className="text-xs text-cd-text-tertiary mt-1">本周总时长 (h)</div>
        </div>
        <div className="card text-center">
          <div className="text-xl font-bold text-cd-green">{totalMin > 0 ? Math.round(totalMin / 7) : 0}</div>
          <div className="text-xs text-cd-text-tertiary mt-1">日均时长 (min)</div>
        </div>
        <div className="card text-center">
          <div className="text-xl font-bold text-cd-green">{peakH}:00</div>
          <div className="text-xs text-cd-text-tertiary mt-1">最活跃时段</div>
        </div>
      </div>

      {/* ─── 热力图网格 ────────────────────── */}
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
    </div>
  )
}
