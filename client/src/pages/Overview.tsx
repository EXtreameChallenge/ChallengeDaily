import { useState, useEffect } from 'react'
import {
  ResponsiveContainer, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import {
  getTodayStats,
  getStatus,
  getActivities,
  pauseCollector,
  resumeCollector,
  getHourlyStats,
  getTrendStats,
  getRhythmStats,
  getAppIconUrl,
  CATEGORY_COLORS,
  type TodayStats,
  type CollectorStatus,
  type Activity,
} from '../api/client'
import {
  Clock, Monitor, Zap, TrendingUp, Camera, Focus,
  Activity as ActivityIcon, Play,
} from 'lucide-react'
import dayjs from 'dayjs'

export default function Overview() {
  const [stats, setStats] = useState<TodayStats | null>(null)
  const [status, setStatus] = useState<CollectorStatus | null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [heatmap3Day, setHeatmap3Day] = useState<number[][]>([Array(24).fill(0), Array(24).fill(0), Array(24).fill(0)])
  const [trendData, setTrendData] = useState<Array<{ date: string; count: number; category_count: number; duration_min: number }>>([])
  const [rhythmData, setRhythmData] = useState<Array<{ period: string; count: number; percentage: number; duration_min: number }>>([])
  const [peakPeriod, setPeakPeriod] = useState('')
  const [loading, setLoading] = useState(true)
  // 应用图标缓存：app_name -> iconUrl（或空字符串表示无图标）
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})

  useEffect(() => {
    const refresh = async () => {
      try {
        const [s, st, actsPage] = await Promise.all([
          getTodayStats(),
          getStatus(),
          getActivities(undefined, 1, 8),
        ])
        setStats(s)
        setStatus(st)
        setActivities(actsPage.activities)

        const days3 = [0, 1, 2].map((offset) => dayjs().subtract(offset, 'day').format('YYYY-MM-DD'))
        const hourlyResults = await Promise.all(days3.map((d) => getHourlyStats(d)))
        const interval = st?.interval_sec || 60
        const heatData = hourlyResults.map((res) =>
          res.hours.map((h) => Math.round(h.count * interval / 60))
        )
        setHeatmap3Day(heatData)

        try {
          const trend = await getTrendStats(7)
          setTrendData(trend.trend)
        } catch { /* 趋势数据非关键 */ }

        try {
          const rhythm = await getRhythmStats()
          setRhythmData(rhythm.periods)
          setPeakPeriod(rhythm.peak_period)
        } catch { /* 节奏数据非关键 */ }
      } catch (err) {
        console.error('Failed to load stats:', err)
      } finally {
        setLoading(false)
      }
    }
    refresh()
    const interval = setInterval(refresh, 30000)
    return () => clearInterval(interval)
  }, [])

  // 加载 Top 应用图标（参考 AppTags 的做法，并行加载避免阻塞）
  useEffect(() => {
    if (!stats?.top_apps?.length) return
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      await Promise.all(
        stats.top_apps!.slice(0, 5).map(async (app) => {
          try {
            map[app.app_name] = await getAppIconUrl(app.app_name)
          } catch {
            map[app.app_name] = ''
          }
        }),
      )
      if (!cancelled) setIconUrls(map)
    })()
    return () => { cancelled = true }
  }, [stats?.top_apps?.map((a) => a.app_name).join('|')])

  if (loading) {
    return <div className="animate-pulse text-cd-text-tertiary text-base p-6">加载中...</div>
  }

  const totalMin = stats?.total_duration_min || 0
  const totalHours = (totalMin / 60).toFixed(1)
  const hours = Math.floor(totalMin / 60)
  const mins = Math.round(totalMin % 60)
  const timeStr = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
  const captureCount = status?.total_captures || 0
  const focusSessions = stats?.focus_sessions || 0
  const longestFocus = stats?.longest_focus_min || 0
  const isRecording = status?.running && !status?.paused
  const isPaused = status !== null && !status.running

  const days = [0, 1, 2].map((offset) => dayjs().subtract(offset, 'day'))
  const heatmapData = heatmap3Day
  const maxHeatVal = Math.max(...heatmapData.flat(), 1)

  const topApps = stats?.top_apps?.slice(0, 5) || []

  const categoryBars = stats?.categories
    ? Object.entries(stats.categories)
        .map(([name, value]) => ({ name, value: Math.round(value) }))
        .filter(d => d.value > 0)
        .sort((a, b) => b.value - a.value)
    : []
  const totalCategoryMin = categoryBars.reduce((s, d) => s + d.value, 0)
  const topCategory = categoryBars[0]?.name || '-'

  const recentActivities = activities.slice(0, 8)

  const validTrend = trendData.filter(d => d.duration_min > 0)

  const isEmptyState = !stats?.total_duration_min && activities.length === 0

  const handleResume = async () => {
    try {
      await resumeCollector()
      const s = await getStatus()
      setStatus(s)
    } catch (err) {
      console.error('Failed to resume collector:', err)
    }
  }

  const formatDur = (m: number) => m >= 60 ? `${(m / 60).toFixed(1)}h` : `${Math.round(m)}min`

  const rhythmIcons: Record<string, string> = {
    '早晨 (6-12)': '🌅',
    '下午 (12-18)': '☀️',
    '晚间 (18-22)': '🌆',
    '夜间 (22-6)': '🌙',
  }
  const rhythmShort: Record<string, string> = {
    '早晨 (6-12)': '早晨',
    '下午 (12-18)': '下午',
    '晚间 (18-22)': '晚间',
    '夜间 (22-6)': '夜间',
  }

  if (isEmptyState) {
    return (
      <div className="animate-fade-in flex items-center justify-center h-full">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 rounded-2xl bg-cd-green/10 flex items-center justify-center mx-auto mb-5">
            <ActivityIcon size={40} className="text-cd-green" />
          </div>
          <h2 className="text-xl font-semibold text-cd-text mb-3">欢迎使用 ChallengeDaily</h2>
          {isPaused ? (
            <>
              <p className="text-base text-cd-text-secondary mb-6">采集器已暂停，点击开始自动记录。</p>
              <button onClick={handleResume}
                className="inline-flex items-center gap-2 bg-cd-green text-white px-7 py-3 rounded-lg text-base font-medium hover:opacity-90 transition">
                <Play size={18} /> 开始记录
              </button>
            </>
          ) : (
            <p className="text-base text-cd-text-secondary">正在自动记录你的活动，稍等片刻即可看到数据。</p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="animate-fade-in space-y-3">
      {/* ─── 顶部状态栏 ─────────────────────── */}
      <div className="flex items-center justify-between px-5 py-3.5 rounded-xl bg-cd-card border border-cd-border">
        <div className="flex items-center gap-5">
          <span className="text-lg font-semibold text-cd-text">
            {dayjs().format('M月D日 dddd')}
          </span>
          <button
            onClick={isRecording ? () => { pauseCollector().then(() => getStatus()).then(setStatus) } : handleResume}
            className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg transition ${
              isRecording
                ? 'bg-cd-green/10 text-cd-green'
                : 'bg-cd-red/10 text-cd-red'
            }`}
          >
            {isRecording ? <><span className="w-2 h-2 rounded-full bg-cd-green animate-pulse-soft" /> 正在记录</> : <><span className="w-2 h-2 rounded-full bg-cd-red" /> 已暂停</>}
          </button>
        </div>
        <div className="flex items-center gap-6 text-sm text-cd-text-secondary">
          <span className="flex items-center gap-1.5"><Clock size={16} className="text-cd-green" /> <b className="text-cd-text">{timeStr}</b></span>
          <span className="flex items-center gap-1.5"><Camera size={16} /> {captureCount}次</span>
          <span className="flex items-center gap-1.5"><Focus size={16} /> 深度{focusSessions}次</span>
          {longestFocus > 0 && <span className="flex items-center gap-1.5"><Zap size={16} /> 最长{formatDur(longestFocus)}</span>}
        </div>
      </div>

      {/* ─── 4 核心指标（行业惯例：精简为 4 个，避免信息过载） ──── */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: '专注时长', value: timeStr, sub: `≈ ${totalHours} 小时`, icon: Clock, color: 'text-cd-green' },
          { label: '深度工作', value: `${focusSessions}次`, sub: longestFocus > 0 ? `最长 ${formatDur(longestFocus)}` : '今日暂无', icon: Focus, color: 'text-cd-blue' },
          { label: '主要分类', value: topCategory, sub: totalCategoryMin > 0 ? `${formatDur(totalCategoryMin)} 总计` : '-', icon: Monitor, color: CATEGORY_COLORS[topCategory] ? '' : 'text-cd-orange', customColor: CATEGORY_COLORS[topCategory] },
          { label: '高效时段', value: peakPeriod ? rhythmShort[peakPeriod] || peakPeriod.split(' ')[0] : '-', sub: captureCount > 0 ? `${captureCount} 次截图` : '-', icon: TrendingUp, color: 'text-cd-orange' },
        ].map(({ label, value, sub, icon: Icon, color, customColor }) => (
          <div key={label} className="bg-cd-card border border-cd-border rounded-xl px-5 py-4 flex items-center gap-4">
            <div className="w-11 h-11 rounded-xl bg-cd-bg-secondary flex items-center justify-center shrink-0">
              <Icon size={20} className={color} style={customColor ? { color: customColor } : undefined} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xl font-bold text-cd-text truncate">{value}</div>
              <div className="text-xs text-cd-text-tertiary mt-0.5 truncate">{label} · {sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ─── 主可视化区：左 1/2 时间分布 | 右 1/2 热力图 ──── */}
      <div className="grid grid-cols-2 gap-3 items-stretch">
        {/* 左：时间分布（横向条形图，参考 RescueTime） */}
        <div className="bg-cd-card border border-cd-border rounded-xl p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-cd-text">时间都去哪了</h3>
            <span className="text-xs text-cd-text-tertiary">{formatDur(totalCategoryMin)}</span>
          </div>
          {categoryBars.length > 0 ? (
            <div className="space-y-3 flex-1 flex flex-col justify-center">
              {categoryBars.slice(0, 6).map((entry) => {
                const pct = totalCategoryMin > 0 ? Math.round(entry.value / totalCategoryMin * 100) : 0
                const color = CATEGORY_COLORS[entry.name] || 'var(--cd-text-tertiary)'
                return (
                  <div key={entry.name}>
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
                        <span className="text-sm text-cd-text truncate">{entry.name}</span>
                      </div>
                      <span className="text-xs text-cd-text-tertiary shrink-0 ml-2"><b className="text-cd-text font-semibold">{formatDur(entry.value)}</b> · {pct}%</span>
                    </div>
                    <div className="h-2.5 rounded-full bg-cd-bg-secondary overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%`, background: color }} />
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-cd-text-tertiary text-center py-8">暂无分类数据</p>
          )}
        </div>

        {/* 右：3天热力图（GitHub Contributions 风格） */}
        <div className="bg-cd-card border border-cd-border rounded-xl p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-cd-text">近三天活动热力图</h3>
            <span className="text-xs text-cd-text-tertiary">每小时分布</span>
          </div>
          <div className="overflow-x-auto flex-1 flex flex-col justify-center">
            <div className="min-w-fit">
              <div className="flex items-center gap-1 pl-12 mb-1.5">
                {Array.from({ length: 24 }, (_, h) => (
                  <div key={h} className="w-7 text-center text-[10px] text-cd-text-tertiary">{h % 4 === 0 ? h : ''}</div>
                ))}
              </div>
              {days.map((day, di) => (
                <div key={di} className="flex items-center gap-1 mb-1">
                  <span className="text-[11px] text-cd-text-tertiary w-10 text-right shrink-0 mr-1">
                    {di === 0 ? '今天' : di === 1 ? '昨天' : day.format('MM/DD')}
                  </span>
                  {heatmapData[di].map((val, h) => {
                    const intensity = maxHeatVal > 0 ? val / maxHeatVal : 0
                    return (
                      <div key={h}
                        className="rounded transition-all hover:scale-125 cursor-default"
                        style={{
                          width: 28, height: 22,
                          background: val === 0
                            ? 'var(--cd-bg-tertiary)'
                            : `rgba(99,91,255,${0.12 + intensity * 0.75})`,
                        }}
                        title={`${day.format('MM/DD')} ${h}:00 - ${val}分钟`}
                      />
                    )
                  })}
                </div>
              ))}
              <div className="flex items-center gap-1.5 mt-2 pl-12">
                <span className="text-[10px] text-cd-text-tertiary">少</span>
                {[0, 0.25, 0.5, 0.75, 1].map((v, i) => (
                  <div key={i} className="w-4 h-3 rounded-sm"
                    style={{ background: v === 0 ? 'var(--cd-bg-tertiary)' : `rgba(99,91,255,${0.12 + v * 0.75})` }} />
                ))}
                <span className="text-[10px] text-cd-text-tertiary">多</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ─── 应用使用 Top 5（真实应用图标） + 效率趋势 ──── */}
      <div className="grid grid-cols-5 gap-3 items-stretch">
        {/* 左：应用使用 Top 5，占 3/5 */}
        <div className="col-span-3 bg-cd-card border border-cd-border rounded-xl p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-cd-text">应用使用 Top 5</h3>
            <span className="text-xs text-cd-text-tertiary">共 {topApps.length} 个应用</span>
          </div>
          {topApps.length > 0 ? (
            <div className="space-y-2.5 flex-1 flex flex-col justify-center">
              {topApps.map((app, idx) => {
                const pct = totalMin > 0 ? (app.duration_min / totalMin) * 100 : 0
                const iconUrl = iconUrls[app.app_name]
                const iconChar = app.app_name.replace(/\s+/g, '').slice(0, 1).toUpperCase()
                const displayName = app.app_name.replace(/\.exe$/i, '')
                return (
                  <div key={app.app_name} className="flex items-center gap-3">
                    <span className="text-xs text-cd-text-tertiary w-4 text-right shrink-0">{idx + 1}</span>
                    <div className="w-8 h-8 rounded-lg bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center shrink-0 overflow-hidden">
                      {iconUrl ? (
                        <img
                          src={iconUrl}
                          alt=""
                          className="w-6 h-6 object-contain"
                          onError={(e) => {
                            // 加载失败回退到首字母占位
                            e.currentTarget.style.display = 'none'
                            const parent = e.currentTarget.parentElement
                            if (parent && !parent.querySelector('.fallback-char')) {
                              const span = document.createElement('span')
                              span.className = 'fallback-char text-xs font-medium text-cd-text-secondary'
                              span.textContent = iconChar
                              parent.appendChild(span)
                            }
                          }}
                        />
                      ) : (
                        <span className="text-xs font-medium text-cd-text-secondary">{iconChar}</span>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-cd-text truncate" title={app.app_name}>{displayName}</span>
                        <span className="text-xs text-cd-text-tertiary shrink-0 ml-2"><b className="text-cd-text font-semibold">{formatDur(app.duration_min)}</b> · {Math.round(pct)}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-cd-bg-secondary overflow-hidden">
                        <div className="h-full rounded-full bg-cd-green/70 transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%` }} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-cd-text-tertiary text-center py-8">暂无应用记录</p>
          )}
        </div>

        {/* 右：效率趋势，占 2/5 */}
        <div className="col-span-2 bg-cd-card border border-cd-border rounded-xl p-5 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-cd-text">效率趋势</h3>
            <span className="text-xs text-cd-text-tertiary">7 天</span>
          </div>
          {validTrend.length > 0 ? (
            <div className="flex-1 flex flex-col">
              <div className="flex-1" style={{ width: '100%', minHeight: 160 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 8, right: 12, left: -10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--cd-border)" />
                    <XAxis dataKey="date" tickFormatter={(v: string) => dayjs(v).format('MM/DD')}
                      tick={{ fontSize: 11, fill: 'var(--cd-text-tertiary)' }} axisLine={{ stroke: 'var(--cd-border)' }} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--cd-text-tertiary)' }} axisLine={{ stroke: 'var(--cd-border)' }}
                      tickFormatter={(v: number) => `${Math.round(v / 60 * 10) / 10}h`} width={40} />
                    <Tooltip formatter={(value: number) => [value >= 60 ? `${(value / 60).toFixed(1)}h` : `${Math.round(value)}min`, '时长']}
                      labelFormatter={(label: string) => dayjs(label).format('YYYY-MM-DD')}
                      contentStyle={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderRadius: 8, fontSize: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }} />
                    <Line type="monotone" dataKey="duration_min" stroke="var(--cd-green)" strokeWidth={2.5}
                      dot={{ r: 3, fill: 'var(--cd-green)' }} activeDot={{ r: 5 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
            <p className="text-sm text-cd-text-tertiary text-center py-8">数据积累中，明天开始可看趋势</p>
          )}
        </div>
      </div>

      {/* ─── 最近活动 + 个人节奏 ──── */}
      <div className="grid grid-cols-3 gap-3 items-stretch">
        {/* 左：最近活动，占 2/3 */}
        {recentActivities.length > 0 && (
          <div className="col-span-2 bg-cd-card border border-cd-border rounded-xl p-5 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-cd-text">最近活动</h3>
              <span className="text-xs text-cd-text-tertiary">{recentActivities.length} 条</span>
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1 flex-1 items-center">
              {recentActivities.map((act) => {
                const color = CATEGORY_COLORS[act.category] || 'var(--cd-text-tertiary)'
                return (
                  <div key={act.id}
                    className="shrink-0 bg-cd-bg-secondary rounded-lg px-3 py-2.5 min-w-0 max-w-[220px] cursor-default hover:bg-cd-hover transition"
                    title={act.window_title || act.app_name}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[11px] font-mono text-cd-text-tertiary">{dayjs(act.timestamp).format('HH:mm')}</span>
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                      <span className="text-xs font-medium truncate" style={{ color }}>{act.category}</span>
                    </div>
                    <div className="text-[13px] text-cd-text truncate">{act.ai_summary || act.app_name}</div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* 右：个人节奏，占 1/3 */}
        {rhythmData.length > 0 && (
          <div className="bg-cd-card border border-cd-border rounded-xl p-5 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-cd-text">个人节奏</h3>
              {peakPeriod && <span className="text-[10px] text-cd-text-tertiary">峰值：<span className="text-cd-green font-medium">{rhythmShort[peakPeriod] || peakPeriod}</span></span>}
            </div>
            <div className="space-y-2.5 flex-1 flex flex-col justify-center">
              {rhythmData.map((item) => {
                const isPeak = item.duration_min === Math.max(...rhythmData.map(r => r.duration_min))
                const color = isPeak ? 'var(--cd-green)' : 'var(--cd-text-tertiary)'
                const barColor = isPeak ? 'bg-cd-green' : 'bg-cd-green/40'
                return (
                  <div key={item.period}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[13px] text-cd-text flex items-center gap-1.5">
                        {rhythmIcons[item.period] || '⏰'} {rhythmShort[item.period] || item.period}
                      </span>
                      <span className="text-[13px] font-semibold" style={{ color }}>
                        {item.duration_min >= 60 ? `${(item.duration_min / 60).toFixed(1)}h` : `${Math.round(item.duration_min)}m`}
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-cd-bg-secondary overflow-hidden">
                      <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${Math.max(item.percentage, 2)}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
