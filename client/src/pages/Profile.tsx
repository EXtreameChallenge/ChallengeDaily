import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  getProfile,
  getDistilledProfile,
  getAppIconUrl,
  deleteCorrection,
  type ProfileData,
  type DistilledProfile,
} from '../api/client'
import { useAsyncData, formatDuration } from '../components/shared'
import { useToast } from '../components/Toast'
import {
  Brain,
  User,
  Briefcase,
  Zap,
  Clock,
  Sunrise,
  Activity,
  Monitor,
  Tag,
  Wrench,
  Trash2,
  RefreshCw,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  Cell,
} from 'recharts'

const DEFAULT_ICON = import.meta.env.DEV ? '/icon.png' : './icon.png'

function productivityValue(p: string): number {
  const s = String(p || '').trim().toLowerCase()
  if (/^(高|a|优|优秀|高产出|高效|很好|较好)/.test(s)) return 3
  if (/^(中|b|良|良好|一般|普通)/.test(s)) return 2
  if (/^(低|c|差|较差|低效|不好)/.test(s)) return 1
  return 0
}

function productivityLabel(v: number): string {
  if (v >= 3) return '高'
  if (v >= 2) return '中'
  if (v >= 1) return '低'
  return '未评级'
}

function EfficiencyTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: { date: string; value: number; raw: string } }> }) {
  if (!active || !payload?.length) return null
  const item = payload[0].payload
  return (
    <div className="bg-cd-card border border-cd-border rounded-lg px-3 py-2 shadow-sm">
      <p className="text-xs text-cd-text-tertiary mb-0.5">{item.date}</p>
      <p className="text-sm text-cd-text font-medium">
        生产力：{item.raw || '未评级'}（{productivityLabel(item.value)}）
      </p>
    </div>
  )
}

export default function Profile() {
  const toast = useToast()
  const [deletingIds, setDeletingIds] = useState<Set<number>>(new Set())
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})

  const {
    data: profileData,
    loading: profileLoading,
    error: profileError,
    refresh: refreshProfile,
  } = useAsyncData<ProfileData>(() => getProfile(), [])

  const {
    data: distilled,
    loading: distilledLoading,
    error: distilledError,
    refresh: refreshDistilled,
  } = useAsyncData<DistilledProfile>(() => getDistilledProfile(), [])

  const commonSoftware = distilled?.common_software || []
  const commonSoftwareKey = useMemo(() => commonSoftware.map(a => a.app_name).join('|'), [commonSoftware])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      const results = await Promise.allSettled(
        commonSoftware.map(app => getAppIconUrl(app.app_name).then(url => ({ app_name: app.app_name, url })))
      )
      for (const r of results) {
        if (r.status === 'fulfilled') map[r.value.app_name] = r.value.url
      }
      if (!cancelled) setIconUrls(map)
    })()
    return () => { cancelled = true }
  }, [commonSoftwareKey])

  const handleDeleteCorrection = useCallback(async (id: number) => {
    setDeletingIds(prev => new Set(prev).add(id))
    try {
      await deleteCorrection(id)
      toast.success('已删除纠正记录')
      refreshProfile()
    } catch {
      toast.error('删除失败')
    } finally {
      setDeletingIds(prev => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }, [refreshProfile, toast])

  const refreshAll = useCallback(() => {
    refreshProfile()
    refreshDistilled()
  }, [refreshProfile, refreshDistilled])

  const loading = profileLoading || distilledLoading
  const error = profileError || distilledError

  if (loading && !profileData && !distilled) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-cd-green" size={28} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="animate-fade-in max-w-4xl mx-auto">
        <div className="bg-cd-card border border-cd-border rounded-xl p-8 text-center">
          <AlertCircle size={40} className="text-cd-red mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-cd-text mb-2">加载失败</h2>
          <p className="text-sm text-cd-text-secondary mb-4">{error}</p>
          <button
            onClick={refreshAll}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cd-green text-white text-sm hover:opacity-90 transition"
          >
            <RefreshCw size={14} /> 重试
          </button>
        </div>
      </div>
    )
  }

  const workHabits = distilled?.work_habits
  const contentTypes = distilled?.work_content?.content_types || []
  const behaviorTags = distilled?.behavior_patterns?.behavior_tags || []
  const efficiencyTrend = (distilled?.efficiency_trend || []).slice().reverse()
  const corrections = profileData?.corrections || []

  const chartData = efficiencyTrend.map(d => ({
    date: d.date,
    value: productivityValue(d.productivity),
    raw: d.productivity,
  }))

  const maxDuration = Math.max(...commonSoftware.map(a => a.duration_min), 1)

  return (
    <div className="animate-fade-in max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-cd-text font-display flex items-center gap-2">
            <Brain size={26} className="text-cd-green" /> 个人画像
          </h1>
          <p className="text-sm text-cd-text-secondary mt-1">
            基于全周期数据聚合的工作画像 · {efficiencyTrend.length} 天趋势
          </p>
        </div>
        <button
          onClick={refreshAll}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cd-green/10 text-cd-green text-sm hover:bg-cd-green/20 transition disabled:opacity-50"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          刷新
        </button>
      </div>

      {/* Top summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <SummaryCard icon={User} label="角色 / 岗位" value={workHabits?.role_desc || '未设置'} />
        <SummaryCard icon={Briefcase} label="工作风格" value={workHabits?.work_style || '未设置'} />
        <SummaryCard icon={Zap} label="效率模式" value={workHabits?.efficiency_pattern || '暂无数据'} />
      </div>

      {/* Work habits */}
      <section className="bg-cd-card border border-cd-border rounded-xl p-5">
        <h2 className="text-base font-semibold text-cd-text mb-4 flex items-center gap-2">
          <Clock size={18} className="text-cd-green" /> 工作习惯
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <InfoBlock icon={Sunrise} label="作息规律" value={workHabits?.work_rhythm || '暂无数据'} />
          <InfoBlock icon={Activity} label="活跃高峰" value={workHabits?.peak_hours || '暂无数据'} />
        </div>
        <div className="mt-5">
          <div className="text-sm font-medium text-cd-text mb-3 flex items-center gap-2">
            <Activity size={14} className="text-cd-green" /> 效率趋势
          </div>
          {chartData.length === 0 ? (
            <p className="text-sm text-cd-text-tertiary">暂无效率趋势数据</p>
          ) : (
            <div className="h-44">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <XAxis
                    dataKey="date"
                    tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 11 }}
                    tickFormatter={(v: string) => v.slice(5)}
                    axisLine={{ stroke: 'var(--cd-border)' }}
                    tickLine={{ stroke: 'var(--cd-border)' }}
                  />
                  <YAxis hide domain={[0, 3]} />
                  <Tooltip content={<EfficiencyTooltip />} cursor={{ fill: 'var(--cd-hover)' }} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, index) => {
                      const color = entry.value === 3 ? 'var(--cd-green)' : entry.value === 2 ? 'var(--cd-yellow)' : entry.value === 1 ? 'var(--cd-red)' : 'var(--cd-border)'
                      return <Cell key={`cell-${index}`} fill={color} />
                    })}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </section>

      {/* Common software */}
      <section className="bg-cd-card border border-cd-border rounded-xl p-5">
        <h2 className="text-base font-semibold text-cd-text mb-4 flex items-center gap-2">
          <Monitor size={18} className="text-cd-green" /> 常用软件
        </h2>
        {commonSoftware.length === 0 ? (
          <p className="text-sm text-cd-text-tertiary">暂无软件使用数据</p>
        ) : (
          <div className="space-y-3">
            {commonSoftware.map((app, idx) => (
              <div key={app.app_name} className="flex items-center gap-3">
                <span className="w-6 text-center text-sm text-cd-text-tertiary font-mono shrink-0">
                  {idx + 1}
                </span>
                <div className="w-9 h-9 rounded-lg bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center shrink-0 overflow-hidden">
                  <img
                    src={iconUrls[app.app_name] || DEFAULT_ICON}
                    alt=""
                    className="w-6 h-6 object-contain"
                    onError={(e) => { e.currentTarget.src = DEFAULT_ICON }}
                  />
                </div>
                <span className="flex-1 text-sm font-medium text-cd-text truncate">{app.app_name}</span>
                <span className="text-sm text-cd-text-secondary shrink-0">{formatDuration(app.duration_min)}</span>
                <div className="w-24 h-2 bg-cd-bg-secondary rounded-full overflow-hidden shrink-0">
                  <div
                    className="h-full bg-cd-green rounded-full"
                    style={{ width: `${(app.duration_min / maxDuration) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Work content types */}
      <section className="bg-cd-card border border-cd-border rounded-xl p-5">
        <h2 className="text-base font-semibold text-cd-text mb-4 flex items-center gap-2">
          <Tag size={18} className="text-cd-green" /> 工作内容类型
        </h2>
        {contentTypes.length === 0 ? (
          <p className="text-sm text-cd-text-tertiary">暂无工作内容类型数据</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {contentTypes.map(type => (
              <span
                key={type}
                className="px-3 py-1.5 rounded-full bg-cd-green/10 text-cd-green text-sm font-medium"
              >
                {type}
              </span>
            ))}
          </div>
        )}
      </section>

      {/* Behavior patterns */}
      <section className="bg-cd-card border border-cd-border rounded-xl p-5">
        <h2 className="text-base font-semibold text-cd-text mb-4 flex items-center gap-2">
          <Activity size={18} className="text-cd-green" /> 行为模式特征
        </h2>
        {behaviorTags.length === 0 ? (
          <p className="text-sm text-cd-text-tertiary">暂无行为模式数据</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {behaviorTags.map((tag, i) => (
              <div key={i} className="flex items-start gap-2 bg-cd-bg-secondary rounded-lg px-3 py-2">
                <span className="text-cd-green mt-0.5 text-sm">•</span>
                <span className="text-sm text-cd-text">{tag}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Corrections */}
      <section className="bg-cd-card border border-cd-border rounded-xl p-5">
        <h2 className="text-base font-semibold text-cd-text mb-4 flex items-center gap-2">
          <Wrench size={18} className="text-cd-green" /> 分类纠正记录
        </h2>
        {corrections.length === 0 ? (
          <p className="text-sm text-cd-text-tertiary">暂无纠正记录</p>
        ) : (
          <div className="space-y-2">
            {corrections.map((c) => (
              <div
                key={c.id}
                className="flex items-center gap-3 bg-cd-bg-secondary rounded-lg px-3 py-2"
              >
                <span className="text-sm font-medium text-cd-text shrink-0">{c.app_name}</span>
                <span className="text-cd-text-tertiary text-sm shrink-0">→</span>
                <span className="text-sm text-cd-green font-medium shrink-0">
                  {c.correct_category || '重新分类'}
                </span>
                {c.correct_desc && (
                  <span className="text-sm text-cd-text-secondary truncate flex-1 min-w-0">
                    {c.correct_desc}
                  </span>
                )}
                <button
                  onClick={() => handleDeleteCorrection(c.id)}
                  disabled={deletingIds.has(c.id)}
                  className="text-cd-text-tertiary hover:text-cd-red transition p-1 shrink-0 disabled:opacity-50"
                  title="删除"
                >
                  {deletingIds.has(c.id) ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Trash2 size={14} />
                  )}
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function SummaryCard({ icon: Icon, label, value }: {
  icon: React.ElementType<{ size?: number | string; className?: string }>
  label: string
  value: string
}) {
  return (
    <div className="bg-cd-card border border-cd-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="text-cd-green" />
        <span className="text-sm text-cd-text-secondary">{label}</span>
      </div>
      <p className="text-base font-medium text-cd-text line-clamp-2" title={value}>
        {value || '—'}
      </p>
    </div>
  )
}

function InfoBlock({ icon: Icon, label, value }: {
  icon: React.ElementType<{ size?: number | string; className?: string }>
  label: string
  value: string
}) {
  return (
    <div className="bg-cd-bg-secondary rounded-lg p-3 border border-cd-border/50">
      <div className="flex items-center gap-2 mb-1">
        <Icon size={14} className="text-cd-green" />
        <span className="text-sm text-cd-text-secondary">{label}</span>
      </div>
      <p className="text-base font-medium text-cd-text">{value || '—'}</p>
    </div>
  )
}
