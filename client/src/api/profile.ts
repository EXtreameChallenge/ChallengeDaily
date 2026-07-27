// ── 用户画像、深度洞察、AI自我认知 ──
import { request } from './core'

// ─── 用户画像 ──────────────────────────────────

export interface UserProfile {
  role_desc: string
  work_style: string
  habits: string  // JSON string
  app_overrides: string  // JSON string
  custom_rules: string  // JSON string
  updated_at: string
}

export interface UserCorrection {
  id: number
  app_name: string
  correct_category: string
  correct_desc: string
  notes: string
  created_at: string
}

export interface DailyProfile {
  date: string
  daily_summary: string
  work_patterns: string  // JSON
  top_apps: string  // JSON
  focus_hours: string  // JSON
  productivity: string
  key_insights: string  // JSON
  hourly_digest: string  // JSON
  generated_at: string
}

export interface ProfileData {
  profile: UserProfile
  corrections: UserCorrection[]
}

export interface DistilledAppItem {
  app_name: string
  duration_min: number
}

export interface DistilledProfile {
  work_habits: {
    role_desc: string
    work_style: string
    peak_hours: string
    work_rhythm: string
    efficiency_pattern: string
    patterns: string[]
    focus_hours: (string | number)[]
  }
  common_software: DistilledAppItem[]
  work_content: {
    content_types: string[]
    daily_summaries: string[]
  }
  behavior_patterns: {
    behavior_tags: string[]
  }
  efficiency_trend: Array<{ date: string; productivity: string }>
}

/** 获取用户画像 + 纠正记录 */
export async function getProfile(): Promise<ProfileData> {
  return request('/api/profile') as Promise<ProfileData>
}

/** 获取聚合后的全周期用户画像 */
export async function getDistilledProfile(): Promise<DistilledProfile> {
  return request('/api/profile/distilled') as Promise<DistilledProfile>
}

/** 保存用户画像 */
export async function saveProfile(data: Partial<UserProfile>): Promise<{ ok: boolean }> {
  return request('/api/profile', {
    method: 'POST',
    body: JSON.stringify(data),
  }) as Promise<{ ok: boolean }>
}

/** 添加分类纠正 */
export async function addCorrection(data: { app_name: string; correct_category?: string; correct_desc?: string; notes?: string }): Promise<{ ok: boolean }> {
  return request('/api/profile/correction', {
    method: 'POST',
    body: JSON.stringify(data),
  }) as Promise<{ ok: boolean }>
}

/** 删除分类纠正 */
export async function deleteCorrection(id: number): Promise<{ ok: boolean }> {
  return request(`/api/profile/correction/${id}`, { method: 'DELETE' }) as Promise<{ ok: boolean }>
}

/** 获取日画像 */
export async function getDailyProfile(date: string): Promise<{ profile: DailyProfile | null }> {
  return request(`/api/profile/daily/${date}`) as Promise<{ profile: DailyProfile | null }>
}

/** 生成日画像 */
export async function generateDailyProfile(date: string, timeoutMs = 30000): Promise<{ ok: boolean; profile?: DailyProfile }> {
  return request(`/api/profile/daily/${date}/generate`, { method: 'POST' }, timeoutMs) as Promise<{ ok: boolean; profile?: DailyProfile }>
}

/** 获取周上下文（调试用） */
export async function getWeeklyContext(days = 7): Promise<{ context: string }> {
  return request(`/api/profile/weekly-context?days=${days}`) as Promise<{ context: string }>
}

// ─── DeepInsight 深度洞察 ──────────────────────────────

export interface DeepInsightFramework {
  name: string
  scholar: string
  metrics: Record<string, number | string | Record<string, number> | Array<unknown>>
}

export interface DeepInsightFinding {
  dimension: string
  verdict: 'positive' | 'negative' | 'neutral'
  detail: string
}

export interface DeepInsightSummary {
  findings: DeepInsightFinding[]
  positive_count: number
  negative_count: number
  overall: string
}

export interface DeepInsightData {
  status: string
  date: string
  data_points: number
  frameworks: Record<string, DeepInsightFramework>
  summary: DeepInsightSummary
}

/** 获取指定日期的深度洞察分析 */
export async function getDeepInsight(date?: string): Promise<DeepInsightData> {
  const params = date ? `?date=${date}` : ''
  return await request(`/api/deep-insight${params}`) as DeepInsightData
}

// ─── AI 自我认知分析（累积理解系统） ──────────────────────

export interface ProfileAnalysisItem {
  id: number
  analysis_type: string
  result_json: Record<string, unknown>
  confidence: number
  data_points: number
  created_at: string
  updated_at: string
}

export interface ProfileAnalysesResponse {
  analyses: ProfileAnalysisItem[]
}

export interface TriggerAnalysisResult {
  metrics: Record<string, unknown>
  confidence: number
  data_points: number
  error?: string
}

export interface TriggerAnalysisResponse {
  ok: boolean
  results: Record<string, TriggerAnalysisResult>
  error?: string
}

/** 获取所有 AI 自我认知分析结果 */
export async function getProfileAnalyses(): Promise<ProfileAnalysesResponse> {
  return await request('/api/profile/analysis') as ProfileAnalysesResponse
}

/** 获取特定类型的 AI 自我认知分析结果 */
export async function getProfileAnalysisByType(analysisType: string): Promise<{ analysis: ProfileAnalysisItem | null }> {
  return await request(`/api/profile/analysis/${analysisType}`) as { analysis: ProfileAnalysisItem | null }
}

/** 触发 AI 自我认知分析（后台计算+写入缓存） */
export async function triggerProfileAnalysis(types?: string[]): Promise<TriggerAnalysisResponse> {
  return await request('/api/profile/analysis/trigger', {
    method: 'POST',
    body: JSON.stringify({ types: types || ['mbti_inference', 'jungian_functions', 'big_five', 'cognitive_style'] }),
  }, 30000) as TriggerAnalysisResponse
}
