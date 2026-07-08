/**
 * DeepProfile — 深度画像统一页面
 * 整合原个人画像 + 深度洞察 + 个人习惯配置
 * 5个区块：基础画像 → 行为画像 → AI自我认知 → 学术框架分析 → 个人习惯配置
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  ResponsiveContainer, Tooltip,
} from 'recharts'
import { BarChart, Bar, XAxis, YAxis, Cell } from 'recharts'
import {
  getProfile, getDistilledProfile, getAppIconUrl, deleteCorrection,
  getDeepInsight, saveProfile, getProfileAnalyses, triggerProfileAnalysis,
  type ProfileData, type DistilledProfile, type DeepInsightFramework,
  type DeepInsightSummary, type ProfileAnalysisItem,
} from '../api/client'
import { useAsyncData, formatDuration } from '../components/shared'
import { useToast } from '../components/Toast'
import {
  Brain, User, Briefcase, Zap, Clock, Sunrise, Activity, Monitor,
  Tag, Wrench, Trash2, RefreshCw, Loader2, AlertCircle, Sparkles,
  BookOpen, Heart, Target, Layers, Users, Repeat, Shield,
  TrendingUp, TrendingDown, Minus, Award, Info, ChevronDown,
  ChevronUp, Save, Fingerprint, Eye, Lightbulb,
} from 'lucide-react'

const DEFAULT_ICON = import.meta.env.DEV ? '/icon.png' : './icon.png'

// ── 框架图标映射 ──
const FW_ICONS: Record<string, React.ElementType> = {
  flow_theory: Zap, deliberate_practice: Target, bloom_taxonomy: BookOpen,
  self_determination: Heart, ultradian_rhythm: Clock, deep_work: Layers,
  structural_holes: Users, zpd: TrendingUp, habit_loop: Repeat,
  psychological_capital: Shield,
  mbti_inference: Fingerprint, jungian_functions: Eye,
  big_five: Sparkles, cognitive_style: Lightbulb,
}

const FW_COLORS: Record<string, string> = {
  flow_theory: '#00B894', deliberate_practice: '#6C5CE7', bloom_taxonomy: '#A29BFE',
  self_determination: '#E54D42', ultradian_rhythm: '#00CEC9', deep_work: '#5B8DEF',
  structural_holes: '#FD79A8', zpd: '#F0A030', habit_loop: '#55EFC4',
  psychological_capital: '#635BFF',
  mbti_inference: '#6C5CE7', jungian_functions: '#00B894',
  big_five: '#FD79A8', cognitive_style: '#5B8DEF',
}

const RADAR_METRIC_KEYS: Record<string, string> = {
  flow_theory: 'flow_index', deliberate_practice: 'deliberate_ratio',
  bloom_taxonomy: 'cognitive_depth', self_determination: 'intrinsic_motivation_index',
  ultradian_rhythm: 'rhythm_alignment', deep_work: 'deep_work_ratio',
  structural_holes: 'tool_diversity', zpd: 'zpd_alignment',
  habit_loop: 'routine_stability', psychological_capital: 'psycap_index',
  mbti_inference: 'confidence', jungian_functions: 'dominant_score',
  big_five: 'openness_score', cognitive_style: 'wholist_analytic_score',
}

// ── 效率相关 ──
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
      <p className="text-sm text-cd-text font-medium">生产力：{item.raw || '未评级'}（{productivityLabel(item.value)}）</p>
    </div>
  )
}

// ── JSON 对象 ↔ "key = value" 行文本 转换 ──
function textToObj(text: string): Record<string, string> {
  if (!text.trim()) return {}
  try {
    const parsed = JSON.parse(text)
    if (typeof parsed === 'object' && parsed !== null) return parsed
  } catch { /* not JSON */ }
  const obj: Record<string, string> = {}
  text.split('\n').forEach(line => {
    const match = line.match(/^(.+?)\s*=\s*(.+)$/)
    if (match) obj[match[1].trim()] = match[2].trim()
  })
  return obj
}

function objToText(obj: unknown): string {
  if (!obj) return ''
  if (typeof obj === 'string') return obj
  if (typeof obj === 'object') {
    try {
      const entries = Object.entries(obj as Record<string, string>)
      return entries.map(([k, v]) => `${k} = ${v}`).join('\n')
    } catch { return String(obj) }
  }
  return String(obj)
}

// ── 指标名称映射 ──
const METRIC_LABELS: Record<string, string> = {
  flow_index: '心流指数', focus_continuity: '专注连续性', context_switch_cost: '切换代价',
  flow_minutes: '心流时长', switch_count: '切换次数', longest_focus_min: '最长专注',
  deliberate_ratio: '刻意练习比', comfort_zone_ratio: '舒适区占比',
  learning_zone_min: '学习区时长', comfort_zone_min: '舒适区时长',
  skill_accumulation_hours: '技能累积', years_to_expert: '距专家水平',
  cognitive_depth: '认知深度', higher_order_ratio: '高阶思维比',
  dominant_level: '主导层级', dominant_level_name: '主导层级',
  autonomy_score: '自主性', competence_score: '胜任感', relatedness_score: '归属感',
  intrinsic_motivation_index: '内在动机', autonomous_min: '自主时长', reactive_min: '响应时长',
  social_min: '社交时长', rhythm_alignment: '节律对齐', rest_adequacy: '休息充足度',
  afternoon_crash_risk: '午后崩溃风险', longest_streak_min: '最长连续',
  rest_periods: '休息次数', ideal_rest_periods: '理想休息',
  deep_work_ratio: '深度工作比', shallow_work_ratio: '浅层工作比',
  deep_work_min: '深度工作时长', shallow_work_min: '浅层工作时长',
  tool_diversity: '工具多样性', cross_domain_index: '跨域指数',
  knowledge_bridging: '知识桥接', unique_apps: '应用数', unique_categories: '分类数',
  top_app: '主要应用', top_app_pct: '主要应用%',
  challenge_match_ratio: '挑战匹配比', zpd_alignment: 'ZPD对齐', zpd_min: 'ZPD时长',
  habit_consistency: '习惯一致性', routine_stability: '常规稳定性', consecutive_days: '连续天数',
  hope_score: '希望', efficacy_score: '自我效能', resilience_score: '韧性',
  optimism_score: '乐观', psycap_index: 'PsyCap指数',
  // 新框架指标
  ei_score: 'E/I 维度', sn_score: 'S/N 维度', tf_score: 'T/F 维度', jp_score: 'J/P 维度',
  mbti_type: 'MBTI 类型', confidence: '置信度',
  ei_label: 'E/I 偏好', sn_label: 'S/N 偏好', tf_label: 'T/F 偏好', jp_label: 'J/P 偏好',
  se_score: 'Se 外向感觉', si_score: 'Si 内向感觉', ne_score: 'Ne 外向直觉',
  ni_score: 'Ni 内向直觉', te_score: 'Te 外向思考', ti_score: 'Ti 内向思考',
  fe_score: 'Fe 外向情感', fi_score: 'Fi 内向情感',
  dominant_function: '主导功能', dominant_score: '主导功能得分',
  function_stack: '功能栈',
  openness_score: '开放性(O)', conscientiousness_score: '尽责性(C)',
  extraversion_score: '外向性(E)', agreeableness_score: '宜人性(A)',
  neuroticism_score: '神经质(N)',
  wholist_analytic_score: '整体-分析', verbal_imager_score: '言语-表象',
  reflective_impulsive_score: '反思-冲动',
  wa_label: '整体/分析型', vi_label: '言语/表象型', ri_label: '反思/冲动型',
}

function _metricLabel(key: string): string { return METRIC_LABELS[key] || key }

function _formatVal(key: string, val: unknown): string {
  if (typeof val !== 'number' && typeof val !== 'string') return String(val)
  const v = Number(val)
  if (isNaN(v)) return String(val)
  if (key.includes('ratio') || key.includes('_pct')) return `${(v * 100).toFixed(1)}%`
  if (key.includes('_score') || key.includes('_index')) return `${Math.round(v)}/100`
  if (key === 'cognitive_depth') return `${v}/6`
  if (key === 'tool_diversity') return v.toFixed(2)
  if (key.includes('_min')) return `${v.toFixed(0)}分钟`
  if (key.includes('_hours')) return `${v.toFixed(1)}小时`
  if (key === 'years_to_expert') return v ? `${v}年` : '—'
  return String(v)
}

// ── AI 自我认知格式化函数 ──
function formatMbtiContent(analysis?: ProfileAnalysisItem): string | null {
  if (!analysis?.result_json) return null
  const r = analysis.result_json
  const type = String(r.mbti_type || '----')
  const ei = String(r.ei_label || '')
  const sn = String(r.sn_label || '')
  const tf = String(r.tf_label || '')
  const jp = String(r.jp_label || '')
  const conf = typeof r.confidence === 'number' ? `${(r.confidence * 100).toFixed(0)}%` : ''
  return `推断类型：${type}（${ei} · ${sn} · ${tf} · ${jp}）${conf ? ` · 置信度 ${conf}` : ''}`
}

function formatJungianContent(analysis?: ProfileAnalysisItem): string | null {
  if (!analysis?.result_json) return null
  const r = analysis.result_json
  const dominant = String(r.dominant_function || '')
  const stack = Array.isArray(r.function_stack) ? (r.function_stack as string[]).slice(0, 3).join(' > ') : ''
  return dominant ? `主导功能：${dominant}${stack ? ` · 功能栈：${stack}` : ''}` : null
}

function formatCognitiveStyleContent(analysis?: ProfileAnalysisItem): string | null {
  if (!analysis?.result_json) return null
  const r = analysis.result_json
  const wa = String(r.wa_label || '')
  const vi = String(r.vi_label || '')
  const ri = String(r.ri_label || '')
  return `${wa} · ${vi} · ${ri}`
}

function formatBigFiveContent(analysis?: ProfileAnalysisItem): string | null {
  if (!analysis?.result_json) return null
  const r = analysis.result_json
  const o = typeof r.openness_score === 'number' ? r.openness_score : 0
  const c = typeof r.conscientiousness_score === 'number' ? r.conscientiousness_score : 0
  const e = typeof r.extraversion_score === 'number' ? r.extraversion_score : 0
  const a = typeof r.agreeableness_score === 'number' ? r.agreeableness_score : 0
  const n = typeof r.neuroticism_score === 'number' ? r.neuroticism_score : 0
  return `O:${o} · C:${c} · E:${e} · A:${a} · N:${n}`
}

// ══════════════════════════════════════════════════════════════
// 主组件
// ══════════════════════════════════════════════════════════════
export default function DeepProfile() {
  const toast = useToast()
  const navigate = useNavigate()
  const [expandedFw, setExpandedFw] = useState<string | null>(null)
  const [activeSection, setActiveSection] = useState(0)

  // ── 个人画像数据 ──
  const {
    data: profileData, loading: profileLoading, error: profileError, refresh: refreshProfile,
  } = useAsyncData<ProfileData>(() => getProfile(), [])

  const {
    data: distilled, loading: distilledLoading, error: distilledError, refresh: refreshDistilled,
  } = useAsyncData<DistilledProfile>(() => getDistilledProfile(), [])

  // ── 深度洞察数据 ──
  const { data: insight, loading: insightLoading, error: insightError, refresh: refreshInsight } = useAsyncData(
    () => getDeepInsight(), []
  )

  // ── AI 自我认知数据 ──
  const { data: analysesData, loading: analysesLoading, refresh: refreshAnalyses } = useAsyncData(
    () => getProfileAnalyses(), []
  )
  const [analysisTriggering, setAnalysisTriggering] = useState(false)

  // ── 将 analyses 数组转为 type → result 的映射 ──
  const analysisMap = useMemo(() => {
    const map: Record<string, ProfileAnalysisItem> = {}
    for (const a of analysesData?.analyses || []) {
      map[a.analysis_type] = a
    }
    return map
  }, [analysesData])

  // ── 触发分析 ──
  const handleTriggerAnalysis = useCallback(async () => {
    setAnalysisTriggering(true)
    try {
      await triggerProfileAnalysis()
      toast.success('AI 自我认知分析完成')
      refreshAnalyses()
    } catch {
      toast.error('分析触发失败')
    } finally {
      setAnalysisTriggering(false)
    }
  }, [refreshAnalyses, toast])

  // ── 个人习惯配置 ──
  const [roleDesc, setRoleDesc] = useState('')
  const [workStyle, setWorkStyle] = useState('')
  const [habits, setHabits] = useState('')
  const [appOverrides, setAppOverrides] = useState('')
  const [customRules, setCustomRules] = useState('')
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileSaved, setProfileSaved] = useState(false)

  // ── 删除纠正中的 ID ──
  const [deletingIds, setDeletingIds] = useState<Set<number>>(new Set())

  // ── 应用图标 ──
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})

  // ── 从 profileData 加载习惯配置 ──
  useEffect(() => {
    if (!profileData?.profile) return
    setRoleDesc(profileData.profile.role_desc || '')
    setWorkStyle(profileData.profile.work_style || '')
    setAppOverrides(objToText(profileData.profile.app_overrides || ''))
    setHabits(objToText(profileData.profile.habits || ''))
    setCustomRules(profileData.profile.custom_rules || '')
  }, [profileData])

  // ── 加载应用图标 ──
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

  // ── 删除纠正 ──
  const handleDeleteCorrection = useCallback(async (id: number) => {
    setDeletingIds(prev => new Set(prev).add(id))
    try {
      await deleteCorrection(id)
      toast.success('已删除纠正记录')
      refreshProfile()
    } catch {
      toast.error('删除失败')
    } finally {
      setDeletingIds(prev => { const next = new Set(prev); next.delete(id); return next })
    }
  }, [refreshProfile, toast])

  // ── 保存习惯配置 ──
  const handleSaveHabits = async () => {
    setProfileSaving(true)
    try {
      await saveProfile({
        role_desc: roleDesc,
        work_style: workStyle,
        habits: textToObj(habits),
        app_overrides: textToObj(appOverrides),
        custom_rules: customRules,
      })
      setProfileSaved(true)
      setTimeout(() => setProfileSaved(false), 2000)
      toast.success('习惯配置已保存')
    } catch {
      toast.error('保存失败')
    } finally {
      setProfileSaving(false)
    }
  }

  // ── 刷新所有 ──
  const refreshAll = useCallback(() => {
    refreshProfile()
    refreshDistilled()
    refreshInsight()
    refreshAnalyses()
  }, [refreshProfile, refreshDistilled, refreshInsight, refreshAnalyses])

  // ── 派生数据 ──
  const loading = profileLoading || distilledLoading || insightLoading
  const error = profileError || distilledError

  const workHabits = distilled?.work_habits
  const contentTypes = distilled?.work_content?.content_types || []
  const behaviorTags = distilled?.behavior_patterns?.behavior_tags || []
  const efficiencyTrend = (distilled?.efficiency_trend || []).slice().reverse()
  const corrections = profileData?.corrections || []

  const frameworks = insight?.frameworks || {}
  const summary = insight?.summary
  const fwEntries = Object.entries(frameworks) as [string, DeepInsightFramework][]

  const chartData = efficiencyTrend.map(d => ({
    date: d.date, value: productivityValue(d.productivity), raw: d.productivity,
  }))

  const maxDuration = Math.max(...commonSoftware.map(a => a.duration_min), 1)

  // ── 雷达图数据 ──
  const radarData = fwEntries.map(([id, fw]) => {
    const key = RADAR_METRIC_KEYS[id]
    let value = 0
    if (key && fw.metrics) {
      const raw = fw.metrics[key]
      if (id === 'bloom_taxonomy') value = Math.round((raw / 6) * 100)
      else if (id === 'deep_work' || id === 'deliberate_practice') value = Math.round(raw * 100)
      else if (id === 'ultradian_rhythm' || id === 'habit_loop') value = Math.round(raw * 100)
      else if (id === 'structural_holes') value = Math.round(Math.min(raw / 4, 1) * 100)
      else value = raw ?? 0
    }
    return { name: fw.name?.replace(/理论|分类|节律|洞|资本/g, '').trim() || id, value, id }
  }).filter(d => d.value > 0)

  // ── 区块导航标签 ──
  const SECTIONS = [
    { label: '基础画像', icon: User },
    { label: '行为画像', icon: Activity },
    { label: 'AI 自我认知', icon: Fingerprint },
    { label: '学术框架', icon: Brain },
    { label: '习惯配置', icon: Wrench },
  ]

  // ── 加载态 ──
  if (loading && !profileData && !distilled && !insight) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="animate-spin text-cd-green" size={28} />
      </div>
    )
  }

  // ── 错误态 ──
  if (error) {
    return (
      <div className="animate-fade-in max-w-4xl mx-auto">
        <div className="bg-cd-card border border-cd-border rounded-xl p-8 text-center">
          <AlertCircle size={40} className="text-cd-red mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-cd-text mb-2">加载失败</h2>
          <p className="text-sm text-cd-text-secondary mb-4">{error}</p>
          <button onClick={refreshAll} className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-cd-green text-white text-sm hover:opacity-90 transition">
            <RefreshCw size={14} /> 重试
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="animate-fade-in max-w-6xl mx-auto space-y-6">
      {/* ── 标题栏 ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-cd-text font-display flex items-center gap-2">
            <Brain size={26} className="text-cd-green" /> 深度画像
          </h1>
          <p className="text-sm text-cd-text-secondary mt-1">
            全周期数据聚合 + 学术框架量化 + AI 累积理解 · {efficiencyTrend.length} 天趋势 · {insight?.data_points || 0} 个数据点
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

      {/* ── 区块导航 ── */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {SECTIONS.map((sec, i) => (
          <button
            key={sec.label}
            onClick={() => {
              setActiveSection(i)
              document.getElementById(`section-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${
              activeSection === i
                ? 'bg-cd-green/10 text-cd-green border border-cd-green/20'
                : 'bg-cd-bg-secondary text-cd-text-secondary border border-cd-border hover:bg-cd-hover'
            }`}
          >
            <sec.icon size={14} />
            {sec.label}
          </button>
        ))}
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          区块 1：基础画像
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div id="section-0" className="space-y-4">
        <SectionHeader icon={User} title="基础画像" subtitle="角色、风格、效率与作息" />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SummaryCard icon={User} label="角色 / 岗位" value={workHabits?.role_desc || '未设置'} />
          <SummaryCard icon={Briefcase} label="工作风格" value={workHabits?.work_style || '未设置'} />
          <SummaryCard icon={Zap} label="效率模式" value={workHabits?.efficiency_pattern || '暂无数据'} />
        </div>

        <section className="bg-cd-card border border-cd-border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-cd-text mb-4 flex items-center gap-2">
            <Clock size={16} className="text-cd-green" /> 工作习惯
          </h3>
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
                    <XAxis dataKey="date" tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 11 }} tickFormatter={(v: string) => v.slice(5)} axisLine={{ stroke: 'var(--cd-border)' }} tickLine={{ stroke: 'var(--cd-border)' }} />
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
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          区块 2：行为画像
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div id="section-1" className="space-y-4">
        <SectionHeader icon={Activity} title="行为画像" subtitle="软件、内容与行为模式" />

        {/* 常用软件 */}
        <section className="bg-cd-card border border-cd-border rounded-xl p-3.5">
          <h3 className="text-sm font-semibold text-cd-text mb-2.5 flex items-center gap-2">
            <Monitor size={16} className="text-cd-green" /> 常用软件
          </h3>
          {commonSoftware.length === 0 ? (
            <p className="text-sm text-cd-text-tertiary">暂无软件使用数据</p>
          ) : (
            <div className="space-y-1.5">
              {commonSoftware.map((app, idx) => (
                <div key={app.app_name} className="flex items-center gap-2">
                  <span className="w-5 text-center text-xs text-cd-text-tertiary font-mono shrink-0">{idx + 1}</span>
                  <div className="w-7 h-7 rounded-md bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center shrink-0 overflow-hidden">
                    <img src={iconUrls[app.app_name] || DEFAULT_ICON} alt="" className="w-5 h-5 object-contain" onError={(e) => { e.currentTarget.src = DEFAULT_ICON }} />
                  </div>
                  <span className="flex-1 text-sm font-medium text-cd-text truncate">{app.app_name}</span>
                  <span className="text-xs text-cd-text-secondary shrink-0 tabular-nums">{formatDuration(app.duration_min)}</span>
                  <div className="w-20 h-1.5 bg-cd-bg-secondary rounded-full overflow-hidden shrink-0">
                    <div className="h-full bg-cd-green rounded-full" style={{ width: `${(app.duration_min / maxDuration) * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 工作内容类型 + 行为模式 双栏 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <section className="bg-cd-card border border-cd-border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
              <Tag size={16} className="text-cd-green" /> 工作内容类型
            </h3>
            {contentTypes.length === 0 ? (
              <p className="text-sm text-cd-text-tertiary">暂无数据</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {contentTypes.map(type => (
                  <span key={type} className="px-3 py-1.5 rounded-full bg-cd-green/10 text-cd-green text-sm font-medium">{type}</span>
                ))}
              </div>
            )}
          </section>

          <section className="bg-cd-card border border-cd-border rounded-xl p-5">
            <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
              <Activity size={16} className="text-cd-green" /> 行为模式特征
            </h3>
            {behaviorTags.length === 0 ? (
              <p className="text-sm text-cd-text-tertiary">暂无数据</p>
            ) : (
              <div className="space-y-2">
                {behaviorTags.map((tag, i) => (
                  <div key={i} className="flex items-start gap-2 bg-cd-bg-secondary rounded-lg px-3 py-2">
                    <span className="text-cd-green mt-0.5 text-sm">•</span>
                    <span className="text-sm text-cd-text">{tag}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* 分类纠正 */}
        <section className="bg-cd-card border border-cd-border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
            <Wrench size={16} className="text-cd-green" /> 分类纠正记录
          </h3>
          {corrections.length === 0 ? (
            <p className="text-sm text-cd-text-tertiary">暂无纠正记录</p>
          ) : (
            <div className="space-y-2">
              {corrections.map((c) => (
                <div key={c.id} className="flex items-center gap-3 bg-cd-bg-secondary rounded-lg px-3 py-2">
                  <span className="text-sm font-medium text-cd-text shrink-0">{c.app_name}</span>
                  <span className="text-cd-text-tertiary text-sm shrink-0">→</span>
                  <span className="text-sm text-cd-green font-medium shrink-0">{c.correct_category || '重新分类'}</span>
                  {c.correct_desc && <span className="text-sm text-cd-text-secondary truncate flex-1 min-w-0">{c.correct_desc}</span>}
                  <button onClick={() => handleDeleteCorrection(c.id)} disabled={deletingIds.has(c.id)} className="text-cd-text-tertiary hover:text-cd-red transition p-1 shrink-0 disabled:opacity-50" title="删除">
                    {deletingIds.has(c.id) ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          区块 3：AI 自我认知
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div id="section-2" className="space-y-4">
        <SectionHeader icon={Fingerprint} title="AI 自我认知" subtitle="基于累积数据的心理学推断，越用越懂你" />

        <div className="bg-gradient-to-br from-purple-500/10 via-indigo-500/10 to-blue-500/10 dark:from-[#1E1E2E] dark:to-[#252538] border border-cd-border rounded-xl p-6">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center shrink-0">
              <Fingerprint size={24} className="text-purple-400" />
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold text-cd-text mb-2">累积理解系统</h3>
              <p className="text-sm text-cd-text-secondary leading-relaxed">
                AI 会从不远之处开始理解你——而非每次从零开始。基于你的工作行为数据、习惯配置和历史分析，
                系统会逐步构建对你 MBTI 人格类型、荣格认知功能、大五人格维度和认知风格的推断。
                每次分析都会在前次理解基础上加深，形成真正的"认知积累"。
              </p>
            </div>
            <button
              onClick={handleTriggerAnalysis}
              disabled={analysisTriggering}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/20 text-purple-400 text-sm font-medium hover:bg-purple-500/30 transition disabled:opacity-50 shrink-0"
              title="触发 AI 自我认知分析"
            >
              {analysisTriggering ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {analysisTriggering ? '分析中...' : '触发分析'}
            </button>
          </div>

          {/* 四维度卡片 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-5">
            <CognitionCard
              icon={Fingerprint}
              title="MBTI 人格推断"
              color="#6C5CE7"
              placeholder="根据工作模式、决策风格、注意力偏好推断你的 MBTI 类型"
              content={formatMbtiContent(analysisMap.mbti_inference)}
              confidence={analysisMap.mbti_inference?.confidence}
              dataPoints={analysisMap.mbti_inference?.data_points}
              updatedAt={analysisMap.mbti_inference?.updated_at}
            />
            <CognitionCard
              icon={Eye}
              title="荣格八维功能"
              color="#00B894"
              placeholder="分析你的信息获取（S/N）和决策方式（T/F）的偏好强度"
              content={formatJungianContent(analysisMap.jungian_functions)}
              confidence={analysisMap.jungian_functions?.confidence}
              dataPoints={analysisMap.jungian_functions?.data_points}
              updatedAt={analysisMap.jungian_functions?.updated_at}
            />
            <CognitionCard
              icon={Lightbulb}
              title="认知风格"
              color="#5B8DEF"
              placeholder="基于专注模式、切换频率和创新行为分析认知加工风格"
              content={formatCognitiveStyleContent(analysisMap.cognitive_style)}
              confidence={analysisMap.cognitive_style?.confidence}
              dataPoints={analysisMap.cognitive_style?.data_points}
              updatedAt={analysisMap.cognitive_style?.updated_at}
            />
            <CognitionCard
              icon={Sparkles}
              title="大五人格维度"
              color="#FD79A8"
              placeholder="从工作节奏、社交模式、任务完成度等推断 OCEAN 五维度"
              content={formatBigFiveContent(analysisMap.big_five)}
              confidence={analysisMap.big_five?.confidence}
              dataPoints={analysisMap.big_five?.data_points}
              updatedAt={analysisMap.big_five?.updated_at}
            />
          </div>

          <div className="mt-4 text-center">
            <p className="text-xs text-cd-text-tertiary">
              {analysesData?.analyses?.length
                ? `已有 ${analysesData.analyses.length} 项分析结果 · 点击"触发分析"可更新`
                : '点击"触发分析"生成首次结果 · 分析结果会随使用持续优化'}
            </p>
          </div>
        </div>
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          区块 4：学术框架分析
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div id="section-3" className="space-y-4">
        <SectionHeader icon={Brain} title="学术框架分析" subtitle="14 大心理学/教育学/社会学框架量化指标" />

        {insight?.status === 'no_data' ? (
          <div className="bg-cd-card border border-cd-border rounded-xl p-8 text-center">
            <Brain size={40} className="text-cd-text-tertiary mx-auto mb-3" />
            <p className="text-sm text-cd-text-secondary">今天还没有活动记录，开始工作后即可查看深度洞察分析</p>
          </div>
        ) : (
          <>
            {/* 综合发现 */}
            {summary && summary.findings && summary.findings.length > 0 && (
              <div className="bg-cd-card rounded-xl border border-cd-border p-5">
                <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
                  <Award size={16} className="text-cd-gold" /> 综合发现
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {summary.findings.map((f, i) => (
                    <div key={i} className={`flex items-start gap-2 p-3 rounded-lg border ${
                      f.verdict === 'positive' ? 'bg-cd-green/5 border-cd-green/20' :
                      f.verdict === 'negative' ? 'bg-cd-red/5 border-cd-red/20' :
                      'bg-cd-bg-secondary border-cd-border'
                    }`}>
                      {f.verdict === 'positive' ? <TrendingUp size={16} className="text-cd-green shrink-0 mt-0.5" /> :
                       f.verdict === 'negative' ? <TrendingDown size={16} className="text-cd-red shrink-0 mt-0.5" /> :
                       <Minus size={16} className="text-cd-text-tertiary shrink-0 mt-0.5" />}
                      <div>
                        <div className="text-xs font-medium text-cd-text">{f.dimension}</div>
                        <div className="text-xs text-cd-text-secondary mt-0.5">{f.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 雷达图 */}
            {radarData.length >= 3 && (
              <div className="bg-cd-card rounded-xl border border-cd-border p-5">
                <h3 className="text-sm font-semibold text-cd-text mb-4 flex items-center gap-2">
                  <Info size={16} className="text-cd-blue" /> 全维度雷达图
                </h3>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                      <PolarGrid stroke="var(--cd-border)" />
                      <PolarAngleAxis dataKey="name" tick={{ fill: 'var(--cd-text-secondary)', fontSize: 11 }} />
                      <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 9 }} />
                      <Radar name="指标值" dataKey="value" stroke="var(--cd-green)" fill="var(--cd-green)" fillOpacity={0.15} strokeWidth={2} />
                      <Tooltip
                        contentStyle={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderRadius: '8px', fontSize: 12 }}
                        formatter={(value: number) => [`${value}`, '得分']}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* 框架卡片 */}
            <div className="space-y-3">
              {fwEntries.map(([id, fw]) => {
                const Icon = FW_ICONS[id] || Brain
                const color = FW_COLORS[id] || '#6C5CE7'
                const isExpanded = expandedFw === id
                const metrics = fw.metrics || {}
                const metricEntries = Object.entries(metrics).filter(([, v]) => typeof v === 'number' || typeof v === 'string')

                return (
                  <div key={id} className="bg-cd-card rounded-xl border border-cd-border overflow-hidden transition-all">
                    <button
                      onClick={() => setExpandedFw(isExpanded ? null : id)}
                      className="w-full flex items-center gap-3 p-4 hover:bg-cd-hover transition-colors text-left"
                    >
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ background: `${color}15`, color }}>
                        <Icon size={18} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-cd-text">{fw.name}</div>
                        <div className="text-xs text-cd-text-tertiary">{fw.scholar}</div>
                      </div>
                      <div className="hidden sm:flex items-center gap-4">
                        {metricEntries.slice(0, 3).map(([key, val]) => (
                          <div key={key} className="text-right">
                            <div className="text-xs text-cd-text-tertiary">{_metricLabel(key)}</div>
                            <div className="text-sm font-semibold text-cd-text">{_formatVal(key, val)}</div>
                          </div>
                        ))}
                      </div>
                      {isExpanded ? <ChevronUp size={16} className="text-cd-text-tertiary" /> : <ChevronDown size={16} className="text-cd-text-tertiary" />}
                    </button>

                    {isExpanded && (
                      <div className="px-4 pb-4 border-t border-cd-border pt-3">
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                          {metricEntries.map(([key, val]) => (
                            <MetricCard key={key} label={_metricLabel(key)} value={_formatVal(key, val)} color={color} />
                          ))}
                        </div>
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
                        {id === 'bloom_taxonomy' && metrics.bloom_distribution && (
                          <div className="mt-3">
                            <div className="text-xs text-cd-text-tertiary mb-1">认知层级分布</div>
                            <div className="flex gap-2 flex-wrap">
                              {Object.entries(metrics.bloom_distribution as Record<string, number>).map(([level, min]) => (
                                <span key={level} className="text-xs bg-cd-bg-secondary px-2 py-0.5 rounded">{level}: {min}分钟</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {id === 'structural_holes' && metrics.category_distribution && (
                          <div className="mt-3">
                            <div className="text-xs text-cd-text-tertiary mb-1">分类时间分布</div>
                            <div className="flex gap-2 flex-wrap">
                              {Object.entries(metrics.category_distribution as Record<string, number>).map(([cat, min]) => (
                                <span key={cat} className="text-xs bg-cd-bg-secondary px-2 py-0.5 rounded">{cat}: {min}分钟</span>
                              ))}
                            </div>
                          </div>
                        )}
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

            {/* 学术引用 */}
            <div className="bg-cd-card rounded-xl border border-cd-border p-5">
              <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-2">
                <BookOpen size={16} className="text-cd-purple" /> 学术引用
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {fwEntries.map(([id, fw]) => (
                  <div key={id} className="text-xs text-cd-text-tertiary flex items-start gap-1.5">
                    <span className="text-cd-text-secondary font-medium shrink-0">{fw.scholar}</span>
                    <span>— {fw.name}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          区块 5：个人习惯配置
          ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div id="section-4" className="space-y-4">
        <SectionHeader icon={Wrench} title="个人习惯配置" subtitle="帮助 AI 更理解你的工作方式，仅保存在本地" />

        <div className="bg-cd-card border border-cd-border rounded-xl p-5 space-y-4">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">角色 / 岗位描述</label>
            <textarea value={roleDesc} onChange={(e) => setRoleDesc(e.target.value)} rows={2}
              placeholder="例如：全栈开发工程师，主要负责后端服务与内部工具开发"
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">工作风格 / 作息</label>
            <textarea value={workStyle} onChange={(e) => setWorkStyle(e.target.value)} rows={2}
              placeholder="例如：上午 10 点到 12 点专注编码，下午开会较多，晚上 8 点后不处理工作"
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">常用软件实际用途</label>
            <textarea value={appOverrides} onChange={(e) => setAppOverrides(e.target.value)} rows={3}
              placeholder={`例如：\nCursor = 开发 IDE\nObsidian = 个人知识管理\nFigma = 产品原型设计`}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">特定场景行为说明</label>
            <textarea value={habits} onChange={(e) => setHabits(e.target.value)} rows={3}
              placeholder="例如：看到我在微信和浏览器之间切换，通常是在查找资料或确认需求"
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1 flex items-center gap-1">
              <Sparkles size={12} /> 偏好分析规则
            </label>
            <textarea value={customRules} onChange={(e) => setCustomRules(e.target.value)} rows={3}
              placeholder={`例如：请优先按「开发 / 会议 / 沟通 / 文档」归类；遇到无法判断的应用时，标记为「其他」并注明原因`}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
            />
          </div>

          <div className="text-xs text-cd-text-tertiary space-y-1">
            <p>• 这些信息会作为 AI 分析上下文的补充，提升分类和日报的准确度</p>
            <p>• 内容仅保存在本地数据库，不会上传到任何服务器</p>
            <p>• 配置会被累积理解系统使用，帮助 AI 更准确地判断你的工作模式</p>
          </div>

          <button
            onClick={handleSaveHabits}
            disabled={profileSaving}
            className={`w-full py-2.5 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
              profileSaved
                ? 'bg-cd-green-light text-cd-green'
                : 'bg-cd-green hover:bg-cd-green-dark text-white'
            } disabled:opacity-60`}
          >
            {profileSaving ? <><Loader2 size={14} className="animate-spin" /> 保存中...</> :
             profileSaved ? '已保存' :
             <><Save size={14} /> 保存习惯配置</>}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── 子组件 ──

function SectionHeader({ icon: Icon, title, subtitle }: { icon: React.ElementType<{ size?: number | string; className?: string }>; title: string; subtitle: string }) {
  return (
    <div className="flex items-center gap-2 pt-2">
      <Icon size={18} className="text-cd-green" />
      <div>
        <h2 className="text-base font-semibold text-cd-text">{title}</h2>
        <p className="text-xs text-cd-text-tertiary">{subtitle}</p>
      </div>
    </div>
  )
}

function SummaryCard({ icon: Icon, label, value }: { icon: React.ElementType<{ size?: number | string; className?: string }>; label: string; value: string }) {
  return (
    <div className="bg-cd-card border border-cd-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon size={16} className="text-cd-green" />
        <span className="text-sm text-cd-text-secondary">{label}</span>
      </div>
      <p className="text-base font-medium text-cd-text line-clamp-2" title={value}>{value || '—'}</p>
    </div>
  )
}

function InfoBlock({ icon: Icon, label, value }: { icon: React.ElementType<{ size?: number | string; className?: string }>; label: string; value: string }) {
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

function MetricCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-cd-bg-secondary rounded-lg p-2.5 border border-cd-border/50">
      <div className="text-[10px] text-cd-text-tertiary mb-0.5">{label}</div>
      <div className="text-sm font-semibold text-cd-text" style={{ color }}>{value}</div>
    </div>
  )
}

function CognitionCard({ icon: Icon, title, color, placeholder, content, confidence, dataPoints, updatedAt }: {
  icon: React.ElementType<{ size?: number | string; className?: string }>; title: string; color: string; placeholder: string; content: string | null;
  confidence?: number; dataPoints?: number; updatedAt?: string;
}) {
  return (
    <div className="bg-cd-bg-secondary/50 rounded-xl p-4 border border-cd-border/50">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: `${color}20`, color }}>
          <Icon size={14} />
        </div>
        <span className="text-sm font-semibold text-cd-text">{title}</span>
        {confidence !== undefined && confidence > 0 && (
          <span className="ml-auto text-[10px] text-cd-text-tertiary bg-cd-bg-secondary px-1.5 py-0.5 rounded">
            {(confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>
      {content ? (
        <div>
          <p className="text-sm text-cd-text">{content}</p>
          {(dataPoints !== undefined || updatedAt) && (
            <p className="text-[10px] text-cd-text-tertiary mt-1.5">
              {dataPoints !== undefined && `${dataPoints} 个数据点`}
              {updatedAt && ` · 更新于 ${updatedAt.slice(0, 16)}`}
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs text-cd-text-tertiary italic">{placeholder}</p>
      )}
    </div>
  )
}
