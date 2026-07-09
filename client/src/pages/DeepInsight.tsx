/**
 * DeepInsight — 基于学术框架的深度分析页面
 * 展示10大心理学/教育学/社会学框架的量化指标
 */
import { useState, useEffect } from 'react'
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts'
import { getDeepInsight, type DeepInsightFramework, type DeepInsightSummary } from '../api/client'
import { useAsyncData, ApiErrorDisplay } from '../components/shared'
import {
  Brain,
  Zap,
  Target,
  BookOpen,
  Heart,
  Clock,
  Layers,
  Users,
  Repeat,
  Shield,
  TrendingUp,
  TrendingDown,
  Minus,
  RefreshCw,
  Award,
  Info,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'

// ── 框架图标映射 ──
const FW_ICONS: Record<string, React.ElementType> = {
  flow_theory: Zap,
  deliberate_practice: Target,
  bloom_taxonomy: BookOpen,
  self_determination: Heart,
  ultradian_rhythm: Clock,
  deep_work: Layers,
  structural_holes: Users,
  zpd: TrendingUp,
  habit_loop: Repeat,
  psychological_capital: Shield,
}

// ── 雷达图颜色 ──
const FW_COLORS: Record<string, string> = {
  flow_theory: '#00B894',
  deliberate_practice: '#6C5CE7',
  bloom_taxonomy: '#A29BFE',
  self_determination: '#E54D42',
  ultradian_rhythm: '#00CEC9',
  deep_work: '#5B8DEF',
  structural_holes: '#FD79A8',
  zpd: '#F0A030',
  habit_loop: '#55EFC4',
  psychological_capital: '#635BFF',
}

// ── 关键指标选取（每个框架取1-2个核心指标用于雷达图） ──
const RADAR_METRIC_KEYS: Record<string, string> = {
  flow_theory: 'flow_index',
  deliberate_practice: 'deliberate_ratio',
  bloom_taxonomy: 'cognitive_depth',
  self_determination: 'intrinsic_motivation_index',
  ultradian_rhythm: 'rhythm_alignment',
  deep_work: 'deep_work_ratio',
  structural_holes: 'tool_diversity',
  zpd: 'zpd_alignment',
  habit_loop: 'routine_stability',
  psychological_capital: 'psycap_index',
}

export default function DeepInsight() {
  const [expandedFw, setExpandedFw] = useState<string | null>(null)

  const { data: insight, loading, error, refresh } = useAsyncData(
    () => getDeepInsight(),
    []
  )

  const frameworks = insight?.frameworks || {}
  const summary = insight?.summary
  const fwEntries = Object.entries(frameworks) as [string, DeepInsightFramework][]

  // ── 雷达图数据 ──
  const radarData = fwEntries.map(([id, fw]) => {
    const key = RADAR_METRIC_KEYS[id]
    let value = 0
    if (key && fw.metrics) {
      const raw = fw.metrics[key]
      // 归一化到 0-100
      if (id === 'bloom_taxonomy') {
        value = Math.round((Number(raw) / 6) * 100) // cognitive_depth: 1-6 → 0-100
      } else if (id === 'deep_work' || id === 'deliberate_practice') {
        value = Math.round(Number(raw) * 100) // ratio: 0-1 → 0-100
      } else if (id === 'ultradian_rhythm' || id === 'habit_loop') {
        value = Math.round(Number(raw) * 100) // 0-1 → 0-100
      } else if (id === 'structural_holes') {
        value = Math.round(Math.min(Number(raw) / 4, 1) * 100) // Shannon diversity, max ~4
      } else {
        value = Number(raw) || 0
      }
    }
    return { name: fw.name?.replace(/理论|分类|节律|洞|资本/g, '').trim() || id, value, id }
  }).filter(d => d.value > 0)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <Brain size={40} className="text-cd-green mx-auto mb-3 animate-pulse" />
          <p className="text-cd-text-secondary">正在计算学术框架指标...</p>
        </div>
      </div>
    )
  }

  if (error || insight?.status === 'no_data') {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center max-w-md">
          <Brain size={48} className="text-cd-text-tertiary mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-cd-text mb-2">暂无数据</h2>
          <p className="text-cd-text-secondary text-sm">
            {typeof error === 'string' ? error : (error as unknown as Error)?.message || '今天还没有活动记录，开始工作后即可查看深度洞察分析'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* ── 标题栏 ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-cd-text flex items-center gap-2">
            <Brain className="text-cd-green" size={24} />
            深度洞察
          </h1>
          <p className="text-sm text-cd-text-secondary mt-1">
            基于心理学/教育学/社会学学术框架的量化分析 · {insight?.data_points || 0} 条数据点
          </p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cd-green/10 text-cd-green text-sm hover:bg-cd-green/20 transition-colors"
        >
          <RefreshCw size={14} />
          刷新
        </button>
      </div>

      {/* ── 综合发现 ── */}
      {summary && summary.findings && summary.findings.length > 0 && (
        <div className="bg-cd-card rounded-xl border border-cd-border p-5">
          <h2 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
            <Award size={16} className="text-cd-gold" />
            综合发现
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {summary.findings.map((f, i) => (
              <div
                key={i}
                className={`flex items-start gap-2 p-3 rounded-lg border ${
                  f.verdict === 'positive' ? 'bg-cd-green/5 border-cd-green/20' :
                  f.verdict === 'negative' ? 'bg-cd-red/5 border-cd-red/20' :
                  'bg-cd-bg-secondary border-cd-border'
                }`}
              >
                {f.verdict === 'positive' ? (
                  <TrendingUp size={16} className="text-cd-green shrink-0 mt-0.5" />
                ) : f.verdict === 'negative' ? (
                  <TrendingDown size={16} className="text-cd-red shrink-0 mt-0.5" />
                ) : (
                  <Minus size={16} className="text-cd-text-tertiary shrink-0 mt-0.5" />
                )}
                <div>
                  <div className="text-xs font-medium text-cd-text">{f.dimension}</div>
                  <div className="text-xs text-cd-text-secondary mt-0.5">{f.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── 雷达图 ── */}
      {radarData.length >= 3 && (
        <div className="bg-cd-card rounded-xl border border-cd-border p-5">
          <h2 className="text-sm font-semibold text-cd-text mb-4 flex items-center gap-2">
            <Info size={16} className="text-cd-blue" />
            全维度雷达图
          </h2>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                <PolarGrid stroke="var(--cd-border)" />
                <PolarAngleAxis
                  dataKey="name"
                  tick={{ fill: 'var(--cd-text-secondary)', fontSize: 11 }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 100]}
                  tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 9 }}
                />
                <Radar
                  name="指标值"
                  dataKey="value"
                  stroke="var(--cd-green)"
                  fill="var(--cd-green)"
                  fillOpacity={0.15}
                  strokeWidth={2}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--cd-card)',
                    border: '1px solid var(--cd-border)',
                    borderRadius: '8px',
                    fontSize: 12,
                  }}
                  formatter={(value: number) => [`${value}`, '得分']}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── 10大框架指标卡片 ── */}
      <div className="space-y-3">
        {fwEntries.map(([id, fw]) => {
          const Icon = FW_ICONS[id] || Brain
          const color = FW_COLORS[id] || '#6C5CE7'
          const isExpanded = expandedFw === id
          const metrics = fw.metrics || {}
          const metricEntries = Object.entries(metrics).filter(
            ([, v]) => typeof v === 'number' || typeof v === 'string'
          )

          return (
            <div
              key={id}
              className="bg-cd-card rounded-xl border border-cd-border overflow-hidden transition-all"
            >
              {/* 框架头部 */}
              <button
                onClick={() => setExpandedFw(isExpanded ? null : id)}
                className="w-full flex items-center gap-3 p-4 hover:bg-cd-hover transition-colors text-left"
              >
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ background: `${color}15`, color }}
                >
                  <Icon size={18} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-cd-text">{fw.name}</div>
                  <div className="text-xs text-cd-text-tertiary">{fw.scholar}</div>
                </div>
                {/* 核心指标预览 */}
                <div className="hidden sm:flex items-center gap-4">
                  {metricEntries.slice(0, 3).map(([key, val]) => (
                    <div key={key} className="text-right">
                      <div className="text-xs text-cd-text-tertiary">{_metricLabel(key)}</div>
                      <div className="text-sm font-semibold text-cd-text">
                        {_formatVal(key, val)}
                      </div>
                    </div>
                  ))}
                </div>
                {isExpanded ? (
                  <ChevronUp size={16} className="text-cd-text-tertiary" />
                ) : (
                  <ChevronDown size={16} className="text-cd-text-tertiary" />
                )}
              </button>

              {/* 展开详情 */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-cd-border pt-3">
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                    {metricEntries.map(([key, val]) => (
                      <MetricCard key={key} label={_metricLabel(key)} value={_formatVal(key, val)} color={color} />
                    ))}
                  </div>
                  {/* 心流段详情 */}
                  {id === 'flow_theory' && metrics.flow_segments_detail && (
                    <div className="mt-3">
                      <div className="text-xs text-cd-text-tertiary mb-1">心流时段</div>
                      <div className="space-y-1">
                        {(metrics.flow_segments_detail as Array<{category: string; duration_min: number; apps: string[]}>).map((seg, i) => (
                          <div key={i} className="text-xs text-cd-text-secondary bg-cd-bg-secondary px-2 py-1 rounded">
                            {seg.category} · {seg.duration_min}分钟 · {seg.apps.join('、')}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {/* 布鲁姆分布 */}
                  {id === 'bloom_taxonomy' && metrics.bloom_distribution && (
                    <div className="mt-3">
                      <div className="text-xs text-cd-text-tertiary mb-1">认知层级分布</div>
                      <div className="flex gap-2 flex-wrap">
                        {Object.entries(metrics.bloom_distribution as Record<string, number>).map(([level, min]) => (
                          <span key={level} className="text-xs bg-cd-bg-secondary px-2 py-0.5 rounded">
                            {level}: {min}分钟
                          </span>
                        ))}
                      </div>
                      <div className="text-xs text-cd-text-secondary mt-1">
                        主导层级：{String(metrics.dominant_level_name || `L${metrics.dominant_level}`)}
                      </div>
                    </div>
                  )}
                  {/* 分类分布 */}
                  {id === 'structural_holes' && metrics.category_distribution && (
                    <div className="mt-3">
                      <div className="text-xs text-cd-text-tertiary mb-1">分类时间分布</div>
                      <div className="flex gap-2 flex-wrap">
                        {Object.entries(metrics.category_distribution as Record<string, number>).map(([cat, min]) => (
                          <span key={cat} className="text-xs bg-cd-bg-secondary px-2 py-0.5 rounded">
                            {cat}: {min}分钟
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {/* 习惯模式 */}
                  {id === 'habit_loop' && metrics.detected_patterns && (
                    <div className="mt-3">
                      <div className="text-xs text-cd-text-tertiary mb-1">检测到的模式</div>
                      <div className="space-y-1">
                        {(metrics.detected_patterns as Array<{hour: number; category: string; duration_min: number}>).map((p, i) => (
                          <div key={i} className="text-xs text-cd-text-secondary bg-cd-bg-secondary px-2 py-1 rounded">
                            {p.hour}:00 → {p.category}（{p.duration_min}分钟）
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* ── 学术引用 ── */}
      <div className="bg-cd-card rounded-xl border border-cd-border p-5">
        <h2 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
          <BookOpen size={16} className="text-cd-purple" />
          学术引用
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {fwEntries.map(([id, fw]) => (
            <div key={id} className="text-xs text-cd-text-tertiary flex items-start gap-1.5">
              <span className="text-cd-text-secondary font-medium shrink-0">{fw.scholar}</span>
              <span>— {fw.name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── 指标卡片 ──
function MetricCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-cd-bg-secondary rounded-lg p-2.5 border border-cd-border/50">
      <div className="text-[10px] text-cd-text-tertiary mb-0.5">{label}</div>
      <div className="text-sm font-semibold text-cd-text" style={{ color }}>{value}</div>
    </div>
  )
}

// ── 指标名称映射 ──
const METRIC_LABELS: Record<string, string> = {
  flow_index: '心流指数',
  focus_continuity: '专注连续性',
  context_switch_cost: '切换代价',
  flow_minutes: '心流时长',
  switch_count: '切换次数',
  longest_focus_min: '最长专注',
  deliberate_ratio: '刻意练习比',
  comfort_zone_ratio: '舒适区占比',
  learning_zone_min: '学习区时长',
  comfort_zone_min: '舒适区时长',
  skill_accumulation_hours: '技能累积',
  years_to_expert: '距专家水平',
  cognitive_depth: '认知深度',
  higher_order_ratio: '高阶思维比',
  dominant_level: '主导层级',
  dominant_level_name: '主导层级',
  autonomy_score: '自主性',
  competence_score: '胜任感',
  relatedness_score: '归属感',
  intrinsic_motivation_index: '内在动机',
  autonomous_min: '自主时长',
  reactive_min: '响应时长',
  social_min: '社交时长',
  rhythm_alignment: '节律对齐',
  rest_adequacy: '休息充足度',
  afternoon_crash_risk: '午后崩溃风险',
  longest_streak_min: '最长连续',
  rest_periods: '休息次数',
  ideal_rest_periods: '理想休息',
  deep_work_ratio: '深度工作比',
  shallow_work_ratio: '浅层工作比',
  deep_work_min: '深度工作时长',
  shallow_work_min: '浅层工作时长',
  tool_diversity: '工具多样性',
  cross_domain_index: '跨域指数',
  knowledge_bridging: '知识桥接',
  unique_apps: '应用数',
  unique_categories: '分类数',
  top_app: '主要应用',
  top_app_pct: '主要应用%',
  challenge_match_ratio: '挑战匹配比',
  zpd_alignment: 'ZPD对齐',
  zpd_min: 'ZPD时长',
  habit_consistency: '习惯一致性',
  routine_stability: '常规稳定性',
  consecutive_days: '连续天数',
  hope_score: '希望',
  efficacy_score: '自我效能',
  resilience_score: '韧性',
  optimism_score: '乐观',
  psycap_index: 'PsyCap指数',
}

function _metricLabel(key: string): string {
  return METRIC_LABELS[key] || key
}

function _formatVal(key: string, val: unknown): string {
  if (typeof val !== 'number' && typeof val !== 'string') return String(val)
  const v = Number(val)
  if (isNaN(v)) return String(val)
  // 百分比类
  if (key.includes('ratio') || key.includes('_pct')) return `${(v * 100).toFixed(1)}%`
  if (key.includes('_score') || key.includes('_index')) return `${Math.round(v)}/100`
  if (key === 'cognitive_depth') return `${v}/6`
  if (key === 'tool_diversity') return v.toFixed(2)
  if (key.includes('_min')) return `${v.toFixed(0)}分钟`
  if (key.includes('_hours')) return `${v.toFixed(1)}小时`
  if (key === 'years_to_expert') return v ? `${v}年` : '—'
  return String(v)
}
