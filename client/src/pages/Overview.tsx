import { useState, useEffect, useMemo } from 'react'
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
  Clock, Monitor, Zap, TrendingUp, Camera, Focus, CalendarDays,
  Activity as ActivityIcon, Play, ArrowRight,
} from 'lucide-react'
import dayjs from 'dayjs'
import { RefreshIndicator } from '../components/shared'
import HeroInfo from '../components/HeroInfo'
import DistractionHeatmap from '../components/DistractionHeatmap'
import EmotionalCare from '../components/EmotionalCare'
import InfoTooltip, { METRIC_EXPLANATIONS } from '../components/InfoTooltip'

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

/** 卡片标题栏：标题在左，"更多" 在右，hover 显示箭头 */
function CardHeader({ title, subtitle, linkTo, onNavigate }: {
  title: string
  subtitle?: string
  linkTo: string
  onNavigate: (path: string) => void
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h3 className="text-sm font-semibold text-cd-text">
        {title}
        {subtitle && <span className="text-cd-text-tertiary font-normal ml-1.5">{subtitle}</span>}
      </h3>
      <button
        onClick={() => onNavigate(linkTo)}
        className="flex items-center gap-1 text-xs text-cd-text-tertiary hover:text-cd-green transition-colors group"
      >
        更多
        <ArrowRight size={12} className="opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
      </button>
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

        try {
          const heat = await getRecentHeatmap(3)
          setHeatmapData(heat.data)
        } catch { /* 热力图数据非关键 */ }

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
        setRefreshing(false)
        isFirst = false
      }
    }
    refresh()
    // 优化：从 30 秒调整为 60 秒
    // 配合 visibilitychange 事件，窗口隐藏时暂停轮询
    const interval = setInterval(() => {
      if (!document.hidden) refresh()
    }, 60000)
    // 窗口恢复可见时立即刷新
    const onVisible = () => { if (!document.hidden) refresh() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(interval)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  const topAppsKey = useMemo(() => stats?.top_apps?.map((a) => a.app_name).join('|'), [stats?.top_apps])

  useEffect(() => {
    if (!stats?.top_apps?.length) return
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      await Promise.all(
        stats.top_apps!.map(async (app) => {
          try {
            // Use raw process name for icon lookup (e.g. "chrome.exe"), not display name ("Google Chrome")
            const iconKey = app.app_name_raw || app.app_name
            map[app.app_name] = await getAppIconUrl(iconKey)
          } catch {
            map[app.app_name] = ''
          }
        }),
      )
      if (!cancelled) setIconUrls(map)
    })()
    return () => { cancelled = true }
  }, [topAppsKey])

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
  const intervalSec = status?.interval_sec || 60

  // 将 24 小时聚合为 12 个 2 小时区间
  const heatmapBins = heatmapData.map((day) => {
    const cells: number[] = []
    for (let b = 0; b < 12; b++) {
      cells.push((day.hours[2 * b] || 0) + (day.hours[2 * b + 1] || 0))
    }
    return { ...day, cells }
  })
  const maxHeatVal = Math.max(...heatmapBins.flatMap((d) => d.cells), 1)

  const topApps = stats?.top_apps || []

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

  const handlePause = async () => {
    try {
      await pauseCollector()
      const s = await getStatus()
      setStatus(s)
    } catch (err) {
      console.error('Failed to pause collector:', err)
    }
  }

  const formatDur = (m: number) => m >= 60 ? `${(m / 60).toFixed(1)}h` : `${Math.round(m)}min`

  const rhythmIcons: Record<string, string> = {
    '凌晨 (0-6)': '🌑',
    '早晨 (6-8)': '🌅',
    '上午 (8-11)': '🌞',
    '中午 (11-14)': '🍜',
    '下午 (14-19)': '☀️',
    '晚间 (19-22)': '🌆',
    '夜间 (22-24)': '🌙',
  }
  const rhythmShort: Record<string, string> = {
    '凌晨 (0-6)': '凌晨',
    '早晨 (6-8)': '早晨',
    '上午 (8-11)': '上午',
    '中午 (11-14)': '中午',
    '下午 (14-19)': '下午',
    '晚间 (19-22)': '晚间',
    '夜间 (22-24)': '夜间',
  }

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
    <div className="animate-fade-in">
      {/* ─── Hero 区域：时间日期 + AI 导语 + 关键数字 + 状态 ──── */}
      <div className="mb-8">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <HeroInfo todayDurationMin={stats?.total_duration_min || 0} />
          </div>
          <button
            onClick={isRecording ? handlePause : handleResume}
            className={`shrink-0 flex items-center gap-2 text-sm px-4 py-2 rounded-lg transition border ${
              isRecording
                ? 'border-cd-green/20 bg-cd-green/5 text-cd-green'
                : 'border-cd-red/20 bg-cd-red/5 text-cd-red'
            }`}
          >
            {isRecording ? <><span className="w-2 h-2 rounded-full bg-cd-green animate-pulse-soft" /> 正在记录</> : <><span className="w-2 h-2 rounded-full bg-cd-red" /> 已暂停</>}
          </button>
        </div>

        {/* 三个核心指标：大号衬线数字 */}
        <div className="grid grid-cols-3 gap-6 mt-6">
          <div>
            <p className="text-xs text-cd-text-tertiary uppercase tracking-widest mb-1 flex items-center gap-1">
              专注时长 <InfoTooltip {...METRIC_EXPLANATIONS.focus_min} />
            </p>
            <p className="text-3xl font-bold text-cd-text font-brand tracking-tight">{timeStr}</p>
            <p className="text-xs text-cd-text-tertiary mt-0.5"><span className="font-brand font-semibold">{captureCount}</span> 次活动捕捉</p>
          </div>
          <div>
            <p className="text-xs text-cd-text-tertiary uppercase tracking-widest mb-1 flex items-center gap-1">
              深度工作 <InfoTooltip {...METRIC_EXPLANATIONS.deep_work_hours} />
            </p>
            <p className="text-3xl font-bold text-cd-text font-brand tracking-tight">{focusSessions} <span className="text-lg font-normal text-cd-text-tertiary">次</span></p>
            <p className="text-xs text-cd-text-tertiary mt-0.5">{longestFocus > 0 ? `最长 ${formatDur(longestFocus)}` : '今日暂无'}</p>
          </div>
          <div>
            <p className="text-xs text-cd-text-tertiary uppercase tracking-widest mb-1">高效时段</p>
            <p className="text-3xl font-bold text-cd-text font-display tracking-tight">{peakPeriod ? rhythmShort[peakPeriod] || peakPeriod.split(' ')[0] : '-'}</p>
            <p className="text-xs text-cd-text-tertiary mt-0.5">主要分类 · {topCategory}</p>
          </div>
        </div>

        {/* 快捷入口：查看完整进度仪表盘 */}
        <div className="flex items-center gap-3 mt-5">
          <a href="#/dashboard" className="text-sm text-cd-green hover:underline flex items-center gap-1">
            <TrendingUp size={14} /> 查看完整进度仪表盘
          </a>
          <span className="text-cd-text-tertiary">·</span>
          <a href="#/week-plan" className="text-sm text-cd-green hover:underline flex items-center gap-1">
            <CalendarDays size={14} /> 前往周计划
          </a>
          <span className="text-cd-text-tertiary">·</span>
          <a href="#/focus" className="text-sm text-cd-green hover:underline flex items-center gap-1">
            <Focus size={14} /> 开始专注
          </a>
        </div>

        {/* P8-2：情感化设计 — 每日一句 + 里程碑庆祝 + 低谷关怀 */}
        <div className="mt-5">
          <EmotionalCare />
        </div>
      </div>

      {/* ─── 分隔线 ──── */}
      <div className="border-t border-cd-border mb-6" />

      {/* ─── 主可视化区：左 时间分布 | 右 热力图 ──── */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        {/* 左：时间分布 */}
        <div className="flex flex-col">
          <CardHeader title="时间都去哪了" linkTo="/timeline" onNavigate={navigate} />
          <div className="flex-1 bg-cd-card border border-cd-border rounded-xl p-5">
            {categoryBars.length > 0 ? (
              <div className="space-y-4">
                {categoryBars.slice(0, 5).map((entry) => {
                  const pct = totalCategoryMin > 0 ? Math.round(entry.value / totalCategoryMin * 100) : 0
                  const color = CATEGORY_COLORS[entry.name] || 'var(--cd-text-tertiary)'
                  return (
                    <div key={entry.name}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
                          <span className="text-sm text-cd-text truncate">{entry.name}</span>
                        </div>
                        <span className="text-sm text-cd-text-tertiary shrink-0 ml-3">
                          <span className="font-brand font-semibold text-cd-text">{formatDur(entry.value)}</span>
                          <span className="text-xs ml-1 font-brand">{pct}%</span>
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-cd-bg-secondary overflow-hidden">
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
        </div>

        {/* 右：3天热力图 */}
        <div className="flex flex-col">
          <CardHeader title="近三天活动热力图" linkTo="/heatmap" onNavigate={navigate} />
          <div className="flex-1 bg-cd-card border border-cd-border rounded-xl p-4 flex flex-col justify-center">
            <div className="grid grid-cols-12 gap-1 pl-[52px] mb-1.5">
              {Array.from({ length: 12 }, (_, b) => (
                <div key={b} className="text-center text-[9px] text-cd-text-tertiary font-brand">{b * 2}</div>
              ))}
            </div>
            {[...heatmapBins].reverse().map((day, di) => {
              const dayLabel = di === 0 ? 'Today' : di === 1 ? 'Yesterday' : dayjs(day.date).format('MM/DD')
              return (
                <div key={day.date} className="mb-2">
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-cd-text-tertiary w-11 text-right shrink-0 mr-1 font-brand">
                      {dayLabel}
                    </span>
                    <div className="flex-1 grid grid-cols-12 gap-1">
                      {day.cells.map((val, b) => {
                        const intensity = maxHeatVal > 0 ? val / maxHeatVal : 0
                        const startH = b * 2
                        const cellMin = Math.round(val * intervalSec / 60)
                        return (
                          <div key={b}
                            className="h-5 rounded-sm transition-all hover:scale-110 cursor-default"
                            style={{
                              background: val === 0
                                ? 'var(--cd-bg-tertiary)'
                                : `rgba(99,91,255,${0.1 + intensity * 0.7})`,
                            }}
                            title={`${dayjs(day.date).format('MM/DD')} ${startH}:00-${startH + 2}:00 · ${cellMin}分钟 · ${val}次活动`}
                          />
                        )
                      })}
                    </div>
                  </div>
                  <div className="pl-[52px] mt-1 flex items-center gap-2 text-[10px] text-cd-text-tertiary">
                    <span>总 <span className="text-cd-text font-brand font-semibold">{formatDur(day.total_min)}</span></span>
                    <span>·</span>
                    <span>峰值 <span className="text-cd-text font-brand font-semibold">{day.peak_hour >= 0 ? `${day.peak_hour}:00` : '-'}</span></span>
                    <span>·</span>
                    <span>主力 <span className="text-cd-text font-medium">{day.top_app ? getDisplayAppName(day.top_app) : '-'}</span></span>
                  </div>
                </div>
              )
            })}
            <div className="flex items-center gap-1 mt-1 pl-[52px]">
              <span className="text-[10px] text-cd-text-tertiary">Less</span>
              {[0, 0.25, 0.5, 0.75, 1].map((v, i) => (
                <div key={i} className="w-3.5 h-3 rounded-sm"
                  style={{ background: v === 0 ? 'var(--cd-bg-tertiary)' : `rgba(99,91,255,${0.1 + v * 0.7})` }} />
              ))}
              <span className="text-[10px] text-cd-text-tertiary">More</span>
            </div>
          </div>
        </div>
      </div>

      {/* ─── 下方区域：应用 Top 5 + 效率趋势 + 个人节奏 ──── */}
      <div className="grid grid-cols-3 gap-6">
        {/* 左：应用使用 */}
        <div className="col-span-1 flex flex-col">
          <CardHeader title="应用使用" linkTo="/apps" onNavigate={navigate} />
          <div className="flex-1 bg-cd-card border border-cd-border rounded-xl p-5 min-h-0 overflow-hidden">
            {topApps.length > 0 ? (
              <div className="space-y-2.5 overflow-y-auto max-h-[280px] pr-1 scrollbar-thin">
                {topApps.map((app, idx) => {
                  const pct = totalMin > 0 ? (app.duration_min / totalMin) * 100 : 0
                  const iconUrl = iconUrls[app.app_name]
                  const defaultIcon = import.meta.env.DEV ? '/icon.png' : './icon.png'
                  const displayName = getDisplayAppName(app.app_name)
                  return (
                    <div key={app.app_name} className="flex items-center gap-2.5">
                      <div className="w-7 h-7 rounded-md bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center shrink-0 overflow-hidden">
                        <img src={iconUrl || defaultIcon} alt="" className="w-5 h-5 object-contain" onError={(e) => { e.currentTarget.src = defaultIcon }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-xs text-cd-text truncate" title={app.app_name}>{displayName}</span>
                          <span className="text-xs font-brand font-semibold text-cd-text shrink-0 ml-2">{formatDur(app.duration_min)}</span>
                        </div>
                        <div className="h-1.5 rounded-full bg-cd-bg-secondary overflow-hidden">
                          <div className="h-full rounded-full bg-cd-green/60 transition-all duration-500" style={{ width: `${Math.max(pct, 2)}%` }} />
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
        </div>

        {/* 中：效率趋势 */}
        <div className="col-span-1 flex flex-col">
          <CardHeader title="效率趋势" subtitle="7d" linkTo="/timeline" onNavigate={navigate} />
          <div className="flex-1 bg-cd-card border border-cd-border rounded-xl p-5 min-h-[220px]">
            {validTrend.length > 0 ? (
              <div className="h-full min-h-[180px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--cd-border)" vertical={false} />
                    <XAxis dataKey="date" tickFormatter={(v: string) => dayjs(v).format('M/D')}
                      tick={{ fontSize: 11, fill: 'var(--cd-text-tertiary)' }} axisLine={{ stroke: 'var(--cd-border)' }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--cd-text-tertiary)' }} axisLine={false} tickLine={false}
                      tickFormatter={(v: number) => `${Math.round(v / 60 * 10) / 10}h`} width={36} />
                    <Tooltip formatter={(value: number) => [value >= 60 ? `${(value / 60).toFixed(1)}h` : `${Math.round(value)}min`, '时长']}
                      labelFormatter={(label: string) => dayjs(label).format('YYYY-MM-DD')}
                      contentStyle={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderRadius: 8, fontSize: 12 }} />
                    <Line type="monotone" dataKey="duration_min" stroke="var(--cd-green)" strokeWidth={2}
                      dot={{ r: 3, fill: 'var(--cd-green)' }} activeDot={{ r: 5 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-full min-h-[180px] flex items-center justify-center">
                <p className="text-sm text-cd-text-tertiary">数据积累中</p>
              </div>
            )}
          </div>
        </div>

        {/* 右：个人节奏 */}
        <div className="col-span-1 flex flex-col">
          <CardHeader title="个人节奏" linkTo="/heatmap" onNavigate={navigate} />
          <div className="flex-1 bg-cd-card border border-cd-border rounded-xl p-5">
            {rhythmData.length > 0 ? (
              <div className="space-y-3">
                {(() => {
                  // 用每个时段的理论最大时长作为进度条参考，避免单时段有数据时显示满格
                  const maxHours: Record<string, number> = {
                    '凌晨 (0-6)': 6, '早晨 (6-8)': 2, '上午 (8-11)': 3,
                    '中午 (11-14)': 3, '下午 (14-19)': 5, '晚间 (19-22)': 3, '夜间 (22-24)': 2,
                  }
                  return rhythmData.map((item) => {
                    const maxMin = (maxHours[item.period] || 2) * 60
                    const ratio = Math.min(item.duration_min / maxMin, 1)
                    const widthPct = Math.max(ratio * 100, 2)
                    return (
                      <div key={item.period}>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-sm text-cd-text flex items-center gap-2">
                            {rhythmIcons[item.period] || '⏰'} {rhythmShort[item.period] || item.period}
                          </span>
                          <span className="text-sm font-brand font-semibold text-cd-text">
                            {item.duration_min >= 60 ? `${(item.duration_min / 60).toFixed(1)}h` : `${Math.round(item.duration_min)}m`}
                          </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-cd-bg-secondary overflow-hidden">
                          <div
                            className="h-full rounded-full bg-cd-purple transition-all duration-500"
                            style={{ width: `${widthPct}%`, opacity: 0.4 + ratio * 0.6 }}
                          />
                        </div>
                      </div>
                    )
                  })
                })()}
              </div>
            ) : (
              <p className="text-sm text-cd-text-tertiary text-center py-8">暂无数据</p>
            )}
          </div>
        </div>
      </div>

      {/* ─── 分心热点图（AI 视觉专注教练） ──── */}
      <div className="mt-6">
        <DistractionHeatmap />
      </div>

      {/* ─── 最近活动（底部，更轻量的展示） ──── */}
      {recentActivities.length > 0 && (
        <div className="mt-6 pt-6 border-t border-cd-border">
          <CardHeader title="最近活动" linkTo="/timeline" onNavigate={navigate} />
          <div className="flex gap-2.5 overflow-x-auto pb-1">
            {recentActivities.map((act) => {
              const color = CATEGORY_COLORS[act.category] || 'var(--cd-text-tertiary)'
              return (
                <div key={act.id}
                  className="shrink-0 bg-cd-bg-secondary/50 border border-cd-border/50 rounded-lg px-3.5 py-2.5 min-w-0 max-w-[200px] cursor-default hover:bg-cd-hover transition">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[11px] font-mono text-cd-text-tertiary">{dayjs(act.timestamp).format('HH:mm')}</span>
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
                    <span className="text-xs font-medium truncate" style={{ color }}>{act.category}</span>
                  </div>
                  <div className="text-[13px] text-cd-text truncate">{act.ai_summary || act.app_name}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
