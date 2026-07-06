import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
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
  getTrendStats,
  getRhythmStats,
  getAppIconUrl,
  getRecentHeatmap,
  CATEGORY_COLORS,
  type TodayStats,
  type CollectorStatus,
  type Activity,
  type RecentHeatmapDay,
} from '../api/client'
import {
  Clock, Zap, TrendingUp, Activity as ActivityIcon, Play, ArrowRight,
  Timer, Target, Flame,
} from 'lucide-react'
import dayjs from 'dayjs'
import HeroInfo from '../components/HeroInfo'

function getDisplayAppName(appName: string): string {
  const lower = appName.toLowerCase()
  const map: Record<string, string> = {
    'trae.exe': 'TRAE SOLO CN',
    'trae solo cn.exe': 'TRAE SOLO CN',
    'trae-solo-cn.exe': 'TRAE SOLO CN',
  }
  if (map[lower]) return map[lower]
  return appName.replace(/\.exe$/i, '')
}

/** 卡片标题栏：标题在左，"查看详情→" 在右 */
function CardHeader({ title, subtitle, linkTo, onNavigate }: {
  title: string
  subtitle?: string
  linkTo: string
  onNavigate: (path: string) => void
}) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-xs font-semibold text-cd-text-secondary uppercase tracking-wider">
        {title}
        {subtitle && <span className="text-cd-text-tertiary font-normal ml-1 normal-case tracking-normal">{subtitle}</span>}
      </h3>
      <button
        onClick={() => onNavigate(linkTo)}
        className="flex items-center gap-0.5 text-[11px] text-cd-text-tertiary hover:text-cd-green transition-colors group"
      >
        详情
        <ArrowRight size={10} className="opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
      </button>
    </div>
  )
}

/** 紧凑 KPI 卡片 */
function KpiCard({ label, value, sub, icon: Icon }: {
  label: string
  value: string
  sub?: string
  icon: React.ComponentType<{ size?: number; className?: string }>
}) {
  return (
    <div className="flex items-center gap-2.5 bg-cd-card border border-cd-border rounded-lg px-3 py-2.5">
      <div className="w-8 h-8 rounded-md bg-cd-green/8 flex items-center justify-center shrink-0">
        <Icon size={16} className="text-cd-green" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] text-cd-text-tertiary leading-tight">{label}</p>
        <p className="text-sm font-bold text-cd-text font-brand leading-tight mt-0.5">{value}</p>
        {sub && <p className="text-[10px] text-cd-text-tertiary leading-tight mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export default function Overview() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<TodayStats | null>(null)
  const [status, setStatus] = useState<CollectorStatus | null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [heatmapData, setHeatmapData] = useState<RecentHeatmapDay[]>([])
  const [trendData, setTrendData] = useState<Array<{ date: string; count: number; category_count: number; duration_min: number }>>([])
  const [rhythmData, setRhythmData] = useState<Array<{ period: string; count: number; percentage: number; duration_min: number }>>([])
  const [peakPeriod, setPeakPeriod] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})

  useEffect(() => {
    let isFirst = true
    const refresh = async () => {
      if (!isFirst) setRefreshing(true)
      try {
        const [s, st, actsPage] = await Promise.all([
          getTodayStats(),
          getStatus(),
          getActivities(undefined, 1, 8),
        ])
        setStats(s)
        setStatus(st)
        setActivities(actsPage.activities)

        try { setHeatmapData((await getRecentHeatmap(3)).data) } catch {}
        try { const t = await getTrendStats(7); setTrendData(t.trend) } catch {}
        try { const r = await getRhythmStats(); setRhythmData(r.periods); setPeakPeriod(r.peak_period) } catch {}
      } catch (err) {
        console.error('Failed to load stats:', err)
      } finally {
        setLoading(false)
        setRefreshing(false)
        isFirst = false
      }
    }
    refresh()
    const interval = setInterval(() => { if (!document.hidden) refresh() }, 60000)
    const onVisible = () => { if (!document.hidden) refresh() }
    document.addEventListener('visibilitychange', onVisible)
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVisible) }
  }, [])

  useEffect(() => {
    if (!stats?.top_apps?.length) return
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      await Promise.all(stats.top_apps!.slice(0, 10).map(async (app) => {
        try { map[app.app_name] = await getAppIconUrl(app.app_name) } catch { map[app.app_name] = '' }
      }))
      if (!cancelled) setIconUrls(map)
    })()
    return () => { cancelled = true }
  }, [stats?.top_apps?.map((a) => a.app_name).join('|')])

  if (loading) return <div className="animate-pulse text-cd-text-tertiary text-base p-4">加载中...</div>

  const totalMin = stats?.total_duration_min || 0
  const hours = Math.floor(totalMin / 60)
  const mins = Math.round(totalMin % 60)
  const timeStr = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
  const captureCount = status?.total_captures || 0
  const focusSessions = stats?.focus_sessions || 0
  const longestFocus = stats?.longest_focus_min || 0
  const isRecording = status?.running && !status?.paused
  const isPaused = status !== null && !status.running
  const intervalSec = status?.interval_sec || 60

  const heatmapBins = heatmapData.map((day) => {
    const cells: number[] = []
    for (let b = 0; b < 12; b++) cells.push((day.hours[2 * b] || 0) + (day.hours[2 * b + 1] || 0))
    return { ...day, cells }
  })
  const maxHeatVal = Math.max(...heatmapBins.flatMap((d) => d.cells), 1)

  const topApps = stats?.top_apps || []
  const categoryBars = stats?.categories
    ? Object.entries(stats.categories).map(([name, value]) => ({ name, value: Math.round(value) })).filter(d => d.value > 0).sort((a, b) => b.value - a.value)
    : []
  const totalCategoryMin = categoryBars.reduce((s, d) => s + d.value, 0)
  const topCategory = categoryBars[0]?.name || '-'
  const recentActivities = activities.slice(0, 8)
  const validTrend = trendData.filter(d => d.duration_min > 0)
  const isEmptyState = !stats?.total_duration_min && activities.length === 0
  const formatDur = (m: number) => m >= 60 ? `${(m / 60).toFixed(1)}h` : `${Math.round(m)}min`

  const rhythmShort: Record<string, string> = {
    '凌晨 (0-6)': '凌晨', '早晨 (6-8)': '早晨', '上午 (8-11)': '上午',
    '中午 (11-14)': '中午', '下午 (14-19)': '下午', '晚间 (19-22)': '晚间', '夜间 (22-24)': '夜间',
  }
  const rhythmIcons: Record<string, string> = {
    '凌晨 (0-6)': '🌑', '早晨 (6-8)': '🌅', '上午 (8-11)': '🌞',
    '中午 (11-14)': '🍜', '下午 (14-19)': '☀️', '晚间 (19-22)': '🌆', '夜间 (22-24)': '🌙',
  }

  const handleResume = async () => { try { await resumeCollector(); setStatus(await getStatus()) } catch {} }
  const handlePause = async () => { try { await pauseCollector(); setStatus(await getStatus()) } catch {} }

  if (isEmptyState) {
    return (
      <div className="animate-fade-in flex items-center justify-center h-full">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 rounded-2xl bg-cd-green/10 flex items-center justify-center mx-auto mb-5">
            <ActivityIcon size={40} className="text-cd-green" />
          </div>
          <h2 className="text-xl font-semibold text-cd-text mb-3 font-display">欢迎使用 <span className="font-brand font-bold">ChallengeDaily</span></h2>
          {isPaused ? (
            <>
              <p className="text-base text-cd-text-secondary mb-6">采集器已暂停，点击开始自动记录。</p>
              <button onClick={handleResume} className="inline-flex items-center gap-2 bg-cd-green text-white px-7 py-3 rounded-lg text-base font-medium hover:opacity-90 transition"><Play size={18} /> 开始记录</button>
            </>
          ) : (
            <p className="text-base text-cd-text-secondary">正在自动记录你的活动，稍等片刻即可看到数据。</p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="animate-fade-in space-y-4">
      {/* ─── Row 1: Hero 信息 ──── */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <HeroInfo todayDurationMin={stats?.total_duration_min || 0} />
        </div>
        <button
          onClick={isRecording ? handlePause : handleResume}
          className={`shrink-0 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition border mt-1 ${
            isRecording ? 'border-cd-green/20 bg-cd-green/5 text-cd-green' : 'border-cd-red/20 bg-cd-red/5 text-cd-red'
          }`}
        >
          {isRecording ? <><span className="w-1.5 h-1.5 rounded-full bg-cd-green animate-pulse-soft" /> 记录中</> : <><span className="w-1.5 h-1.5 rounded-full bg-cd-red" /> 已暂停</>}
        </button>
      </div>

      {/* ─── Row 2: KPI 指标条 ──── */}
      <div className="grid grid-cols-4 gap-3">
        <KpiCard icon={Timer} label="专注时长" value={timeStr} sub={`${captureCount} 次活动捕捉`} />
        <KpiCard icon={Target} label="深度工作" value={`${focusSessions} 次`} sub={longestFocus > 0 ? `最长 ${formatDur(longestFocus)}` : '今日暂无'} />
        <KpiCard icon={Flame} label="高效时段" value={peakPeriod ? rhythmShort[peakPeriod] || peakPeriod.split(' ')[0] : '-'} sub={`主要分类 · ${topCategory}`} />
        <KpiCard icon={TrendingUp} label="分类数" value={`${categoryBars.length} 类`} sub={categoryBars.length > 0 ? `主力 ${categoryBars[0].name}` : '暂无'} />
      </div>

      {/* ─── Row 3: 数据卡片自适应网格 ──── */}
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>

        {/* 卡片：时间分布 */}
        <div className="bg-cd-card border border-cd-border rounded-xl p-4">
          <CardHeader title="时间分布" linkTo="/timeline" onNavigate={navigate} />
          {categoryBars.length > 0 ? (
            <div className="space-y-2.5">
              {categoryBars.slice(0, 6).map((entry) => {
                const pct = totalCategoryMin > 0 ? Math.round(entry.value / totalCategoryMin * 100) : 0
                const color = CATEGORY_COLORS[entry.name] || 'var(--cd-text-tertiary)'
                return (
                  <div key={entry.name}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                        <span className="text-xs text-cd-text truncate">{entry.name}</span>
                      </div>
                      <span className="text-xs text-cd-text-tertiary shrink-0 ml-2">
                        <span className="font-brand font-semibold text-cd-text">{formatDur(entry.value)}</span>
                        <span className="text-[10px] ml-0.5 font-brand">{pct}%</span>
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-cd-bg-secondary overflow-hidden">
                      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%`, background: color }} />
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-cd-text-tertiary text-center py-4">暂无数据</p>
          )}
        </div>

        {/* 卡片：应用使用 */}
        <div className="bg-cd-card border border-cd-border rounded-xl p-4">
          <CardHeader title="应用使用" linkTo="/apps" onNavigate={navigate} />
          {topApps.length > 0 ? (
            <div className="space-y-2 overflow-y-auto max-h-[240px] pr-0.5 scrollbar-thin">
              {topApps.map((app) => {
                const pct = totalMin > 0 ? (app.duration_min / totalMin) * 100 : 0
                const iconUrl = iconUrls[app.app_name]
                const defaultIcon = import.meta.env.DEV ? '/icon.png' : './icon.png'
                return (
                  <div key={app.app_name} className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-md bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center shrink-0 overflow-hidden">
                      <img src={iconUrl || defaultIcon} alt="" className="w-4 h-4 object-contain" onError={(e) => { e.currentTarget.src = defaultIcon }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-cd-text truncate" title={app.app_name}>{getDisplayAppName(app.app_name)}</span>
                        <span className="text-[11px] font-brand font-semibold text-cd-text shrink-0 ml-2">{formatDur(app.duration_min)}</span>
                      </div>
                      <div className="h-1 rounded-full bg-cd-bg-secondary overflow-hidden mt-0.5">
                        <div className="h-full rounded-full bg-cd-green/50 transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%` }} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-xs text-cd-text-tertiary text-center py-4">暂无应用记录</p>
          )}
        </div>

        {/* 卡片：热力图 */}
        <div className="bg-cd-card border border-cd-border rounded-xl p-4">
          <CardHeader title="活动热力图" linkTo="/heatmap" onNavigate={navigate} />
          <div className="flex flex-col justify-center">
            <div className="grid grid-cols-12 gap-0.5 pl-[42px] mb-1">
              {Array.from({ length: 12 }, (_, b) => (
                <div key={b} className="text-center text-[8px] text-cd-text-tertiary font-brand">{b * 2}</div>
              ))}
            </div>
            {[...heatmapBins].reverse().map((day, di) => {
              const dayLabel = di === 0 ? 'Today' : di === 1 ? 'Yest' : dayjs(day.date).format('MM/DD')
              return (
                <div key={day.date} className="mb-1">
                  <div className="flex items-center gap-0.5">
                    <span className="text-[9px] text-cd-text-tertiary w-9 text-right shrink-0 mr-0.5 font-brand">{dayLabel}</span>
                    <div className="flex-1 grid grid-cols-12 gap-0.5">
                      {day.cells.map((val, b) => {
                        const intensity = maxHeatVal > 0 ? val / maxHeatVal : 0
                        return (
                          <div key={b}
                            className="h-4 rounded-sm cursor-default hover:scale-110 transition-transform"
                            style={{
                              background: val === 0 ? 'var(--cd-bg-tertiary)' : `rgba(99,91,255,${0.1 + intensity * 0.7})`,
                            }}
                            title={`${dayjs(day.date).format('MM/DD')} ${b * 2}:00-${b * 2 + 2}:00 · ${Math.round(val * intervalSec / 60)}分钟`}
                          />
                        )
                      })}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* 卡片：效率趋势 */}
        <div className="bg-cd-card border border-cd-border rounded-xl p-4">
          <CardHeader title="效率趋势" subtitle="7d" linkTo="/timeline" onNavigate={navigate} />
          {validTrend.length > 0 ? (
            <div className="h-[140px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--cd-border)" vertical={false} />
                  <XAxis dataKey="date" tickFormatter={(v: string) => dayjs(v).format('M/D')}
                    tick={{ fontSize: 10, fill: 'var(--cd-text-tertiary)' }} axisLine={{ stroke: 'var(--cd-border)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: 'var(--cd-text-tertiary)' }} axisLine={false} tickLine={false}
                    tickFormatter={(v: number) => `${Math.round(v / 60 * 10) / 10}h`} width={30} />
                  <Tooltip formatter={(value: number) => [value >= 60 ? `${(value / 60).toFixed(1)}h` : `${Math.round(value)}min`, '时长']}
                    labelFormatter={(label: string) => dayjs(label).format('YYYY-MM-DD')}
                    contentStyle={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderRadius: 8, fontSize: 11 }} />
                  <Line type="monotone" dataKey="duration_min" stroke="var(--cd-green)" strokeWidth={2}
                    dot={{ r: 2, fill: 'var(--cd-green)' }} activeDot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-[140px] flex items-center justify-center"><p className="text-xs text-cd-text-tertiary">数据积累中</p></div>
          )}
        </div>

        {/* 卡片：个人节奏 */}
        <div className="bg-cd-card border border-cd-border rounded-xl p-4">
          <CardHeader title="个人节奏" linkTo="/heatmap" onNavigate={navigate} />
          {rhythmData.length > 0 ? (
            <div className="space-y-1.5">
              {(() => {
                const maxHours: Record<string, number> = {
                  '凌晨 (0-6)': 6, '早晨 (6-8)': 2, '上午 (8-11)': 3,
                  '中午 (11-14)': 3, '下午 (14-19)': 5, '晚间 (19-22)': 3, '夜间 (22-24)': 2,
                }
                return rhythmData.map((item) => {
                  const maxMin = (maxHours[item.period] || 2) * 60
                  const ratio = Math.min(item.duration_min / maxMin, 1)
                  return (
                    <div key={item.period}>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[11px] text-cd-text flex items-center gap-1">
                          {rhythmIcons[item.period] || ''} {rhythmShort[item.period] || item.period}
                        </span>
                        <span className="text-[11px] font-brand font-semibold text-cd-text">
                          {item.duration_min >= 60 ? `${(item.duration_min / 60).toFixed(1)}h` : `${Math.round(item.duration_min)}m`}
                        </span>
                      </div>
                      <div className="h-1 rounded-full bg-cd-bg-secondary overflow-hidden">
                        <div className="h-full rounded-full bg-cd-purple/70 transition-all duration-500" style={{ width: `${Math.max(ratio * 100, 2)}%`, opacity: 0.4 + ratio * 0.6 }} />
                      </div>
                    </div>
                  )
                })
              })()}
            </div>
          ) : (
            <p className="text-xs text-cd-text-tertiary text-center py-4">暂无数据</p>
          )}
        </div>

        {/* 卡片：最近活动 */}
        {recentActivities.length > 0 && (
          <div className="bg-cd-card border border-cd-border rounded-xl p-4">
            <CardHeader title="最近活动" linkTo="/timeline" onNavigate={navigate} />
            <div className="space-y-1.5">
              {recentActivities.map((act) => {
                const color = CATEGORY_COLORS[act.category] || 'var(--cd-text-tertiary)'
                return (
                  <div key={act.id} className="flex items-center gap-2 py-1 border-b border-cd-border/50 last:border-0">
                    <span className="text-[10px] font-mono text-cd-text-tertiary shrink-0 w-10">{dayjs(act.timestamp).format('HH:mm')}</span>
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
                    <span className="text-[11px] font-medium shrink-0" style={{ color }}>{act.category}</span>
                    <span className="text-[11px] text-cd-text truncate">{act.ai_summary || act.app_name}</span>
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
