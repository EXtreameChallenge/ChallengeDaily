import { useState } from 'react'
import dayjs from 'dayjs'
import {
  getHealthCoverage,
  getHealthSystemEvents,
  getSamplingDeviation,
  type HealthCoverage,
  type HealthSystemEvents,
  type SamplingDeviation,
  type SystemSession,
} from '../api/client'
import { useAsyncData, ApiErrorDisplay, formatDuration } from '../components/shared'

export default function Health() {
  const [selectedDate, setSelectedDate] = useState(dayjs().format('YYYY-MM-DD'))

  const { data, loading, error, refresh } = useAsyncData<{
    coverage: HealthCoverage
    events: HealthSystemEvents
    sampling: SamplingDeviation
  }>(
    async () => {
      const [coverage, events, sampling] = await Promise.all([
        getHealthCoverage(selectedDate),
        getHealthSystemEvents(selectedDate),
        getSamplingDeviation(selectedDate),
      ])
      return { coverage, events, sampling }
    },
    [selectedDate],
  )

  const coverage = data?.coverage
  const events = data?.events
  const sampling = data?.sampling

  return (
    <div className="animate-fade-in space-y-5">
      {/* ─── 标题 + 日期选择 ──────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-cd-text">数据校准</h1>
          <p className="text-[11px] text-cd-text-tertiary mt-0.5">
            将应用采集时长与 Windows 系统权威数据源（开关机/登录事件）对比，识别漏采时段与采样偏差。
          </p>
        </div>
        <input
          type="date"
          value={selectedDate}
          max={dayjs().format('YYYY-MM-DD')}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
        />
      </div>

      {error && <ApiErrorDisplay error={error} onRetry={refresh} />}

      {loading ? (
        <div className="text-cd-text-tertiary animate-pulse py-12 text-center">正在读取 Windows 系统事件日志...</div>
      ) : !coverage ? null : (
        <>
          {/* ─── 顶部：三张核心校准卡片 ──────────────────── */}
          <div className="grid grid-cols-3 gap-4">
            <SystemUptimeCard coverage={coverage} />
            <CollectedCard coverage={coverage} />
            <CoverageCard coverage={coverage} />
          </div>

          {/* ─── 会话时间条 ──────────────────── */}
          <SessionTimeline coverage={coverage} />

          {/* ─── 漏采时段列表 ──────────────────── */}
          <MissingPeriodsCard coverage={coverage} />

          {/* ─── 采样间隔分布 ──────────────────── */}
          {sampling && <SamplingDeviationCard sampling={sampling} />}

          {/* ─── 系统事件原始列表 ──────────────────── */}
          {events && <SystemEventsCard events={events} />}
        </>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
// 子组件：系统运行时长卡片
// ═══════════════════════════════════════════════════════════════════
function SystemUptimeCard({ coverage }: { coverage: HealthCoverage }) {
  const sys = coverage.system
  const uptimeMin = sys.total_uptime_min
  const currentUptimeH = Math.floor(sys.current_uptime_sec / 3600)
  const currentUptimeM = Math.floor((sys.current_uptime_sec % 3600) / 60)

  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-cd-text-tertiary">系统运行时长</span>
        <span className="text-[10px] text-cd-text-tertiary bg-cd-bg px-2 py-0.5 rounded">
          Windows 权威
        </span>
      </div>
      <div className="text-2xl font-bold text-cd-text font-brand">
        {formatDuration(uptimeMin)}
      </div>
      <div className="mt-3 space-y-1 text-[11px] text-cd-text-tertiary">
        <div className="flex justify-between">
          <span>当前已开机</span>
          <span className="text-cd-text-secondary font-brand">
            {currentUptimeH}h {currentUptimeM}m
          </span>
        </div>
        <div className="flex justify-between">
          <span>开机次数</span>
          <span className="text-cd-text-secondary">{sys.boot_count}</span>
        </div>
        <div className="flex justify-between">
          <span>关机次数</span>
          <span className="text-cd-text-secondary">{sys.shutdown_count}</span>
        </div>
        <div className="flex justify-between">
          <span>异常断电</span>
          <span className={sys.crash_count > 0 ? 'text-cd-red' : 'text-cd-text-secondary'}>
            {sys.crash_count}
          </span>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
// 子组件：采集时长卡片
// ═══════════════════════════════════════════════════════════════════
function CollectedCard({ coverage }: { coverage: HealthCoverage }) {
  const c = coverage.collected
  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-cd-text-tertiary">应用采集时长</span>
        <span className="text-[10px] text-cd-text-tertiary bg-cd-bg px-2 py-0.5 rounded">
          ChallengeDaily
        </span>
      </div>
      <div className="text-2xl font-bold text-cd-text font-brand">
        {formatDuration(c.total_app_usage_min)}
      </div>
      <div className="mt-3 space-y-1 text-[11px] text-cd-text-tertiary">
        <div className="flex justify-between">
          <span>采集次数</span>
          <span className="text-cd-text-secondary font-brand">{c.total_activities}</span>
        </div>
        <div className="flex justify-between">
          <span>采集器运行</span>
          <span className="text-cd-text-secondary font-brand">
            {formatDuration(c.collector_running_min)}
          </span>
        </div>
        <div className="flex justify-between">
          <span>首次采集</span>
          <span className="text-cd-text-secondary">
            {c.first_activity_time ? dayjs(c.first_activity_time).format('HH:mm:ss') : '—'}
          </span>
        </div>
        <div className="flex justify-between">
          <span>最近采集</span>
          <span className="text-cd-text-secondary">
            {c.last_activity_time ? dayjs(c.last_activity_time).format('HH:mm:ss') : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
// 子组件：覆盖率卡片（核心校准指标）
// ═══════════════════════════════════════════════════════════════════
function CoverageCard({ coverage }: { coverage: HealthCoverage }) {
  const gap = coverage.gap
  const pct = gap.coverage_pct
  // 颜色：>=80 绿，50-80 黄，<50 红
  const color = pct >= 80 ? 'text-cd-green' : pct >= 50 ? 'text-cd-gold' : 'text-cd-red'
  const ringColor = pct >= 80 ? 'var(--cd-green)' : pct >= 50 ? 'var(--cd-gold)' : 'var(--cd-red)'

  // 圆环参数
  const radius = 32
  const circ = 2 * Math.PI * radius
  const offset = circ - (pct / 100) * circ

  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-cd-text-tertiary">采集覆盖率</span>
        <span className="text-[10px] text-cd-text-tertiary bg-cd-bg px-2 py-0.5 rounded">
          核心校准
        </span>
      </div>
      <div className="flex items-center gap-4">
        <svg width="80" height="80" viewBox="0 0 80 80" className="shrink-0">
          <circle cx="40" cy="40" r={radius} fill="none" stroke="var(--cd-border)" strokeWidth="6" />
          <circle
            cx="40" cy="40" r={radius}
            fill="none" stroke={ringColor} strokeWidth="6"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            strokeLinecap="round"
            transform="rotate(-90 40 40)"
            className="transition-all duration-700"
          />
          <text
            x="40" y="40"
            textAnchor="middle" dominantBaseline="central"
            className={`text-[15px] font-bold font-brand ${color}`}
          >
            {pct}%
          </text>
        </svg>
        <div className="flex-1 space-y-1 text-[11px]">
          <div className="flex justify-between">
            <span className="text-cd-text-tertiary">漏采时长</span>
            <span className={`font-brand font-medium ${color}`}>
              {formatDuration(gap.missing_min)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-cd-text-tertiary">漏采时段数</span>
            <span className="text-cd-text-secondary font-brand">
              {gap.missing_periods.length}
            </span>
          </div>
          <div className="mt-2 pt-2 border-t border-cd-border text-[10px] text-cd-text-tertiary leading-relaxed">
            覆盖率 = 采集时长 ÷ 系统时长。{'\n'}
            ≥80% 数据可信，50-80% 建议补录，&lt;50% 数据不可用。
          </div>
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
// 子组件：会话时间条
// ═══════════════════════════════════════════════════════════════════
function SessionTimeline({ coverage }: { coverage: HealthCoverage }) {
  const sessions = coverage.system.sessions
  if (sessions.length === 0) {
    return (
      <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-4">
        <h2 className="text-sm font-semibold text-cd-text mb-2">系统会话段</h2>
        <div className="text-[11px] text-cd-text-tertiary">当天无系统会话记录</div>
      </div>
    )
  }

  // 计算当天的时间范围（00:00 - 24:00）
  const dayStart = dayjs(coverage.date + ' 00:00:00')
  const dayEnd = dayjs(coverage.date + ' 23:59:59')
  const dayRangeSec = 24 * 3600

  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-cd-text">系统会话时间条</h2>
        <span className="text-[10px] text-cd-text-tertiary">
          共 {sessions.length} 段 · 总时长 {formatDuration(coverage.system.total_uptime_min)}
        </span>
      </div>

      {/* 时间条容器 */}
      <div className="relative h-10 bg-cd-bg rounded-lg overflow-hidden border border-cd-border">
        {sessions.map((s, i) => {
          const sStart = dayjs(s.start)
          const sEnd = dayjs(s.end)
          // 计算相对当天的偏移比例
          const startSec = Math.max(0, sStart.diff(dayStart, 'second'))
          const endSec = Math.min(dayRangeSec, sEnd.diff(dayStart, 'second'))
          const leftPct = (startSec / dayRangeSec) * 100
          const widthPct = Math.max(0.5, ((endSec - startSec) / dayRangeSec) * 100)
          return (
            <div
              key={i}
              className="absolute top-0 bottom-0 bg-cd-green/40 border-r border-cd-green/60 flex items-center justify-center"
              style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
              title={`${sStart.format('HH:mm')} - ${sEnd.format('HH:mm')} · ${formatDuration(s.duration_sec / 60)}`}
            >
              {widthPct > 8 && (
                <span className="text-[9px] text-cd-green font-brand">
                  {sStart.format('HH:mm')}-{sEnd.format('HH:mm')}
                </span>
              )}
            </div>
          )
        })}
      </div>

      {/* 时间轴刻度 */}
      <div className="flex justify-between mt-1 text-[9px] text-cd-text-tertiary font-brand">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>24:00</span>
      </div>

      {/* 会话列表 */}
      <div className="mt-3 space-y-1.5">
        {sessions.map((s, i) => (
          <SessionRow key={i} session={s} index={i} />
        ))}
      </div>
    </div>
  )
}

function SessionRow({ session, index }: { session: SystemSession; index: number }) {
  const start = dayjs(session.start)
  const end = dayjs(session.end)
  const durMin = session.duration_sec / 60
  const truncatedStart = session.truncated_start ? '← 截断到 00:00' : ''
  const truncatedEnd = session.truncated_end ? '→ 截断到 24:00' : ''

  return (
    <div className="flex items-center gap-3 text-[11px] py-1.5 px-2 rounded hover:bg-cd-hover transition-colors">
      <span className="text-cd-text-tertiary font-brand w-6">#{index + 1}</span>
      <span className="text-cd-green font-brand">
        {start.format('HH:mm')} → {end.format('HH:mm')}
      </span>
      <span className="text-cd-text-secondary font-brand">
        {formatDuration(durMin)}
      </span>
      <span className="text-[9px] text-cd-text-tertiary bg-cd-bg px-1.5 py-0.5 rounded">
        {session.type === 'boot_session' ? '开机会话' : '登录会话'}
      </span>
      {truncatedStart && <span className="text-[9px] text-cd-gold">{truncatedStart}</span>}
      {truncatedEnd && <span className="text-[9px] text-cd-gold">{truncatedEnd}</span>}
      <span className="ml-auto text-[9px] text-cd-text-tertiary">{session.source}</span>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
// 子组件：漏采时段列表
// ═══════════════════════════════════════════════════════════════════
const REASON_LABEL: Record<string, string> = {
  no_activities: '整段无采集',
  before_first_activity: '首次采集前',
  after_last_activity: '末次采集后',
  sampling_gap: '采样间隔过大',
}

const REASON_COLOR: Record<string, string> = {
  no_activities: 'text-cd-red',
  before_first_activity: 'text-cd-gold',
  after_last_activity: 'text-cd-gold',
  sampling_gap: 'text-cd-red',
}

function MissingPeriodsCard({ coverage }: { coverage: HealthCoverage }) {
  const periods = coverage.gap.missing_periods

  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-cd-text">漏采时段</h2>
        <span className="text-[10px] text-cd-text-tertiary">
          共 {periods.length} 段 · 总时长 {formatDuration(coverage.gap.missing_min)}
        </span>
      </div>

      {periods.length === 0 ? (
        <div className="text-[11px] text-cd-green py-3 text-center">
          ✓ 无漏采时段，数据完整
        </div>
      ) : (
        <div className="space-y-1">
          {periods.map((p, i) => {
            const dur = p.duration_min ?? 0
            const start = dayjs(p.start)
            const end = dayjs(p.end)
            const label = REASON_LABEL[p.reason] || p.reason
            const color = REASON_COLOR[p.reason] || 'text-cd-text-secondary'
            return (
              <div
                key={i}
                className="flex items-center gap-3 text-[11px] py-1.5 px-2 rounded hover:bg-cd-hover transition-colors"
              >
                <span className="text-cd-text-tertiary font-brand w-6">#{i + 1}</span>
                <span className={`${color} font-brand`}>
                  {start.format('HH:mm')} → {end.format('HH:mm')}
                </span>
                <span className="text-cd-text-secondary font-brand">
                  {formatDuration(dur)}
                </span>
                <span className={`text-[9px] px-1.5 py-0.5 rounded bg-cd-bg ${color}`}>
                  {label}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
// 子组件：采样偏差卡片
// ═══════════════════════════════════════════════════════════════════
function SamplingDeviationCard({ sampling }: { sampling: SamplingDeviation }) {
  const s = sampling.interval_stats
  const expected = sampling.expected_interval_sec
  const dev = sampling.deviation
  const intervals = sampling.intervals || []

  // 间隔分布直方图：分桶 0-60 / 60-120 / 120-300 / 300-600 / 600+
  const buckets = [
    { label: '0-60s', min: 0, max: 60, count: 0, color: 'bg-cd-green' },
    { label: '60-120s', min: 60, max: 120, count: 0, color: 'bg-cd-green/70' },
    { label: '2-5min', min: 120, max: 300, count: 0, color: 'bg-cd-gold' },
    { label: '5-10min', min: 300, max: 600, count: 0, color: 'bg-cd-gold/70' },
    { label: '>10min', min: 600, max: Infinity, count: 0, color: 'bg-cd-red' },
  ]
  for (const v of intervals) {
    for (const b of buckets) {
      if (v >= b.min && v < b.max) {
        b.count++
        break
      }
    }
  }
  const maxBucket = Math.max(1, ...buckets.map((b) => b.count))

  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-cd-text">采样间隔分布</h2>
        <span className="text-[10px] text-cd-text-tertiary">
          期望间隔 {expected}s · 共 {sampling.interval_count} 个间隔
        </span>
      </div>

      {/* 统计指标 */}
      <div className="grid grid-cols-5 gap-2 mb-4">
        <StatBox label="最小" value={`${s.min_sec}s`} />
        <StatBox label="P50" value={`${s.p50_sec}s`} highlight={s.p50_sec <= expected} />
        <StatBox label="P95" value={`${s.p95_sec}s`} highlight={s.p95_sec <= expected * 2} />
        <StatBox label="平均" value={`${s.avg_sec}s`} highlight={s.avg_sec <= expected} />
        <StatBox label="最大" value={`${s.max_sec}s`} highlight={s.max_sec <= expected * 2} />
      </div>

      {/* 直方图 */}
      <div className="mb-4">
        <div className="text-[10px] text-cd-text-tertiary mb-2">间隔分布直方图</div>
        <div className="flex items-end gap-2 h-20">
          {buckets.map((b, i) => (
            <div key={i} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-[9px] text-cd-text-tertiary font-brand">{b.count}</span>
              <div
                className={`w-full rounded-t ${b.color} transition-all`}
                style={{ height: `${(b.count / maxBucket) * 100}%`, minHeight: b.count > 0 ? '4px' : '0' }}
              />
              <span className="text-[9px] text-cd-text-tertiary">{b.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 偏差汇总 */}
      <div className="grid grid-cols-3 gap-2 pt-3 border-t border-cd-border">
        <div className="text-center">
          <div className="text-base font-bold text-cd-text font-brand">{dev.over_60s_count}</div>
          <div className="text-[10px] text-cd-text-tertiary">超 60s 次数</div>
        </div>
        <div className="text-center">
          <div className="text-base font-bold text-cd-gold font-brand">{dev.over_300s_count}</div>
          <div className="text-[10px] text-cd-text-tertiary">超 5min 次数</div>
        </div>
        <div className="text-center">
          <div className="text-base font-bold text-cd-red font-brand">{dev.missed_estimates}</div>
          <div className="text-[10px] text-cd-text-tertiary">漏采估算次数</div>
        </div>
      </div>

      <div className="mt-3 text-[10px] text-cd-text-tertiary leading-relaxed">
        说明：采样间隔应接近 {expected}s（约 {Math.round(expected / 60)}min 一次）。
        P50 ≤ {expected}s 表示多数采样正常；P95 偏大说明存在偶发漏采；
        &gt;5min 次数过多会显著影响应用切换时长的精度。
      </div>
    </div>
  )
}

function StatBox({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="bg-cd-bg rounded-lg p-2 text-center">
      <div className={`text-sm font-bold font-brand ${highlight ? 'text-cd-green' : 'text-cd-text'}`}>
        {value}
      </div>
      <div className="text-[9px] text-cd-text-tertiary mt-0.5">{label}</div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════
// 子组件：系统事件列表
// ═══════════════════════════════════════════════════════════════════
const EVENT_TYPE_LABEL: Record<string, { label: string; color: string }> = {
  boot: { label: '开机', color: 'text-cd-green' },
  shutdown: { label: '关机', color: 'text-cd-gold' },
  crash: { label: '异常断电', color: 'text-cd-red' },
  login: { label: '登录', color: 'text-cd-text-secondary' },
  logout: { label: '注销', color: 'text-cd-text-tertiary' },
}

function SystemEventsCard({ events }: { events: HealthSystemEvents }) {
  // 合并 boot_events 和 login_events 按时间排序
  type Ev = { timestamp: string; type: string; source: string; username?: string }
  const all: Ev[] = [
    ...events.boot_events.map((e) => ({ ...e, source: e.source || '' })),
    ...events.login_events.map((e) => ({ ...e, source: 'login' })),
  ].sort((a, b) => a.timestamp.localeCompare(b.timestamp))

  const uptimeH = Math.floor(events.uptime_sec / 3600)
  const uptimeM = Math.floor((events.uptime_sec % 3600) / 60)

  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-cd-text">系统事件原始日志</h2>
        <span className="text-[10px] text-cd-text-tertiary">
          来自 Windows Event Log
        </span>
      </div>

      {/* 当前开机信息 */}
      <div className="mb-3 px-3 py-2 bg-cd-bg rounded-lg text-[11px] flex items-center gap-4">
        <span className="text-cd-text-tertiary">当前开机时间</span>
        <span className="text-cd-green font-brand">
          {events.current_boot_time ? dayjs(events.current_boot_time).format('YYYY-MM-DD HH:mm:ss') : '—'}
        </span>
        <span className="text-cd-text-tertiary">已运行</span>
        <span className="text-cd-text font-brand">{uptimeH}h {uptimeM}m</span>
      </div>

      {all.length === 0 ? (
        <div className="text-[11px] text-cd-text-tertiary py-3 text-center">
          当天无系统事件记录
        </div>
      ) : (
        <div className="space-y-1 max-h-60 overflow-y-auto">
          {all.map((e, i) => {
            const info = EVENT_TYPE_LABEL[e.type] || { label: e.type, color: 'text-cd-text-secondary' }
            return (
              <div
                key={i}
                className="flex items-center gap-3 text-[11px] py-1.5 px-2 rounded hover:bg-cd-hover transition-colors"
              >
                <span className={`font-brand ${info.color}`}>{info.label}</span>
                <span className="text-cd-text-secondary font-brand">
                  {dayjs(e.timestamp).format('HH:mm:ss')}
                </span>
                {e.username && (
                  <span className="text-cd-text-tertiary">@{e.username}</span>
                )}
                <span className="ml-auto text-[9px] text-cd-text-tertiary">{e.source}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
