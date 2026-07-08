const BASE_URL = 'http://127.0.0.1:58888'

// ── 后端连接状态管理（企业级断线重连机制） ──
type BackendState = 'connected' | 'disconnected' | 'connecting'
let _backendState: BackendState = 'connecting'
const _stateListeners = new Set<(s: BackendState) => void>()

export function getBackendState(): BackendState { return _backendState }
export function onBackendStateChange(cb: (s: BackendState) => void): () => void {
  _stateListeners.add(cb)
  return () => _stateListeners.delete(cb)
}
function setBackendState(s: BackendState) {
  if (_backendState === s) return
  _backendState = s
  _stateListeners.forEach(cb => cb(s))
}

// ── API Token 管理 ──
let _apiToken = ''
let _tokenPromise: Promise<string> | null = null

async function getApiToken(): Promise<string> {
  if (_apiToken) return _apiToken
  if (!_tokenPromise && window.electronAPI?.getApiToken) {
    _tokenPromise = window.electronAPI.getApiToken().then((t: string) => {
      _apiToken = t || ''
      _tokenPromise = null
      return _apiToken
    }).catch(() => {
      _tokenPromise = null
      return ''
    })
  }
  return _tokenPromise || ''
}

/** 清除 API Token 缓存（401 时调用，强制下次重新从磁盘读取） */
function invalidateToken() {
  _apiToken = ''
  _tokenPromise = null
}

/** 带指数退避重试的 fetch（参考 resilience4j / Polly 模式）
 * @param timeoutMs - 自定义超时时间（毫秒），默认 10000ms
 * 如果调用方在 options.signal 中传入外部 signal（如 AbortController），
 * 则该 signal 触发 abort 时也会同步中断 fetch；同时保留超时机制。
 */
export async function request(endpoint: string, options?: RequestInit, timeoutMs = 10000, _isRetry = false): Promise<unknown> {
  const token = await getApiToken()
  const controller = new AbortController()
  // 连接超时：后端是本地服务，默认 10 秒；生成报告等长耗时操作可自定义
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  // 若调用方提供外部 signal，则联动中断 fetch
  const externalSignal = options?.signal
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', () => controller.abort(), { once: true })
  }
  // 剥离外部 signal，避免覆盖 timeout controller（fetch 仍使用 controller.signal）
  const { signal: _stripped, ...restOptions } = options || {}
  try {
    setBackendState('connecting')
    const res = await fetch(`${BASE_URL}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-API-Token': token } : {}),
      },
      signal: controller.signal,
      ...restOptions,
    })
    if (res.status === 401) {
      // Token 失效：清除缓存，重试一次（后端可能重启生成了新 token）
      if (!_isRetry) {
        invalidateToken()
        return request(endpoint, options, 10000, true)
      }
      throw new Error('认证失败，请重新启动应用')
    }
    if (!res.ok) {
      // 后端已响应但返回错误码（4xx/5xx）——后端在线，只是业务逻辑出错
      // 不应标记为 disconnected，否则会误报"后端服务断开"
      setBackendState('connected')
      throw new Error(`请求失败: ${res.status}`)
    }
    const data = await res.json()
    setBackendState('connected')
    return data
  } catch (err: unknown) {
    // 外部 signal 主动取消：不更新断连状态，向上抛出 AbortError 供调用方识别
    if (externalSignal?.aborted) {
      throw new DOMException('请求已被取消', 'AbortError')
    }
    // 标记后端断连，触发 UI 重连提示
    setBackendState('disconnected')
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('请求超时，后端可能未响应')
    }
    if (err instanceof Error) {
      if (err.message?.includes('Failed to fetch') || err.message?.includes('NetworkError') || err.message?.includes('ECONNREFUSED')) {
        throw new Error('无法连接到后端服务，正在尝试自动重连...')
      }
      throw err
    }
    throw new Error('未知请求错误')
  } finally {
    clearTimeout(timeoutId)
  }
}

// ─── 类型定义 ────────────────────────────────────
export interface CollectorStatus {
  running: boolean
  paused: boolean
  interval_sec: number
  total_captures: number
  screenshots_size_mb: number
  ai_enabled: boolean
}

export interface TodayStats {
  date: string
  total_duration_min: number
  categories: Record<string, number>
  top_apps: Array<{ app_name: string; app_name_raw?: string; duration_min: number }>
  focus_sessions: number
  longest_focus_min: number
  total_activities?: number
  current_activity?: string | null
}

export interface VisibleWindow {
  app_name: string
  window_title: string
  is_foreground: boolean
  description?: string
  area_ratio?: number
  bounds?: {
    left: number
    top: number
    right: number
    bottom: number
    width: number
    height: number
  }
}

export interface Activity {
  id: number
  timestamp: string
  app_name: string
  app_name_raw?: string
  window_title: string
  category: string
  ai_summary: string | null
  ai_detail: string
  duration_min: number
  windows?: VisibleWindow[]
}

export interface ReportContent {
  date: string
  content: string
  template: string
}

export interface AppUsageContent {
  title: string
  duration_min: number
  percentage: number
}

export interface AppUsage {
  app_name: string
  app_name_raw: string
  category: string
  duration_min: number
  percentage: number
  /** 内容维度：同应用下不同窗口标题的时长明细 */
  contents?: AppUsageContent[]
  /** 不同窗口标题数量 */
  window_count?: number
}

export interface AppCategoryRule {
  id: number
  app_name: string
  display_name: string
  primary_category: string
  tags: string[]
  window_rules: Record<string, string>
  created_at: string
  updated_at: string
}

export interface BackendSettings {
  exclude_apps: string[]
  screenshot_interval_sec: number
  work_start_hour: number
  work_end_hour: number
  custom_report_instructions: string
  ai_api_key?: string
  ai_base_url?: string
  /** @deprecated 旧版单模型字段，保留兼容 */
  ai_model?: string
  ai_vision_model?: string
  ai_text_model?: string
  ai_enabled?: boolean
}

// ─── API 方法 ────────────────────────────────────

/** 获取采集器状态 */
export async function getStatus(): Promise<CollectorStatus> {
  const data = await request('/api/status')
  return data as CollectorStatus
}

/** 获取今日统计 */
export async function getTodayStats(): Promise<TodayStats> {
  const data = await request('/api/stats/today')
  return data as TodayStats
}

/** 获取指定日期统计 */
export async function getDateStats(date: string): Promise<TodayStats> {
  const data = await request(`/api/stats/date/${date}`)
  return data as TodayStats
}

export interface ActivityPage {
  activities: Activity[]
  pagination: {
    page: number
    per_page: number
    total: number
    total_pages: number
    has_more: boolean
  }
}

interface ActivitiesResponse {
  activities: Activity[]
  pagination?: ActivityPage['pagination']
}

/** 获取活动列表（支持分页） */
export async function getActivities(date?: string, page?: number, perPage?: number): Promise<ActivityPage> {
  const params = new URLSearchParams()
  if (date) params.set('date', date)
  if (page) params.set('page', String(page))
  if (perPage) params.set('per_page', String(perPage))
  const qs = params.toString()
  const data = await request(`/api/activities${qs ? '?' + qs : ''}`) as ActivitiesResponse
  // 兼容旧版后端（无 pagination 字段）
  if (!data.pagination) {
    return {
      activities: data.activities || [],
      pagination: { page: 1, per_page: data.activities?.length || 50, total: data.activities?.length || 0, total_pages: 1, has_more: false }
    }
  }
  return data as ActivityPage
}

/** 获取应用使用分布 */
export async function getAppUsage(date?: string): Promise<AppUsage[]> {
  const params = date ? `?date=${date}` : ''
  const data = await request(`/api/app-usage${params}`) as { apps: AppUsage[] }
  return data.apps || []
}

/** 生成日报（深度模板需要 AI 处理更长时间，单独设置 120 秒超时） */
export async function generateDailyReport(template = 'standard'): Promise<ReportContent> {
  const data = await request(`/api/report/daily?template=${template}`, {}, 120000)
  return data as ReportContent
}

/** 生成周报 */
export async function generateWeeklyReport(date?: string): Promise<ReportContent> {
  const params = date ? `?date=${date}` : ''
  const data = await request(`/api/report/weekly${params}`, {}, 120000)
  return data as ReportContent
}

/** 生成月报 */
export async function generateMonthlyReport(month?: string): Promise<ReportContent> {
  const params = month ? `?month=${month}` : ''
  const data = await request(`/api/report/monthly${params}`, {}, 120000)
  return data as ReportContent
}

/** 获取已有日报内容 */
export async function getDailyReportContent(): Promise<ReportContent> {
  const data = await request('/api/report/daily/content')
  return data as ReportContent
}

/** 手动截图 */
export async function captureNow(): Promise<{ ok: boolean }> {
  const data = await request('/api/capture', { method: 'POST' })
  return data as { ok: boolean }
}

/** 健康检查 */
export async function healthCheck(): Promise<{ status: string }> {
  const data = await request('/api/health')
  return data as { status: string }
}

/** 获取后端设置 */
export async function getSettings(): Promise<BackendSettings> {
  const data = await request('/api/settings')
  return data as BackendSettings
}

/** 更新后端设置 */
export async function updateSettings(settings: Partial<BackendSettings>): Promise<{ status: string; settings: BackendSettings }> {
  const data = await request('/api/settings', {
    method: 'POST',
    body: JSON.stringify(settings),
  })
  return data as { status: string; settings: BackendSettings }
}

/** 暂停采集器 */
export async function pauseCollector(): Promise<{ status: string; paused: boolean }> {
  const data = await request('/api/collector/pause', { method: 'POST' })
  return data as { status: string; paused: boolean }
}

/** 恢复采集器 */
export async function resumeCollector(): Promise<{ status: string; paused: boolean }> {
  const data = await request('/api/collector/resume', { method: 'POST' })
  return data as { status: string; paused: boolean }
}

/** 获取指定日期报告 */
export async function getReportByDate(date: string): Promise<ReportContent> {
  const data = await request(`/api/report/date/${date}`)
  return data as ReportContent
}

/** 获取指定日期按小时聚合数据（热力图） */
export async function getHourlyStats(date: string): Promise<{ date: string; hours: Array<{ hour: number; count: number; categories: string[] }> }> {
  const data = await request(`/api/stats/hourly?date=${date}`)
  return data as { date: string; hours: Array<{ hour: number; count: number; categories: string[] }> }
}

/** 获取最近 N 天效率趋势 */
export async function getTrendStats(days = 7): Promise<{ days: number; trend: Array<{ date: string; count: number; category_count: number; duration_min: number }> }> {
  const data = await request(`/api/stats/trend?days=${days}`)
  return data as { days: number; trend: Array<{ date: string; count: number; category_count: number; duration_min: number }> }
}

/** 获取个人节奏分析 */
export async function getRhythmStats(date?: string): Promise<{ date: string; periods: Array<{ period: string; count: number; percentage: number; duration_min: number }>; peak_period: string }> {
  const params = date ? `?date=${date}` : ''
  const data = await request(`/api/stats/rhythm${params}`)
  return data as { date: string; periods: Array<{ period: string; count: number; percentage: number; duration_min: number }>; peak_period: string }
}

export interface RecentHeatmapDay {
  date: string
  hours: number[]
  total_min: number
  peak_hour: number
  top_app: string
}

/** 获取最近 N 天热力图 + 每日摘要 */
export async function getRecentHeatmap(days = 3): Promise<{ days: number; data: RecentHeatmapDay[] }> {
  const data = await request(`/api/stats/recent-heatmap?days=${days}`)
  return data as { days: number; data: RecentHeatmapDay[] }
}

/** 测试 AI API 连接 */
export async function testAiConnection(apiKey: string, baseUrl: string, model: string): Promise<{ ok: boolean; message: string }> {
  const data = await request('/api/ai/test', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model }),
  })
  return data as { ok: boolean; message: string }
}

/** 导出活动记录 CSV（安全下载：使用 header 传 token，不暴露于 URL） */
export async function downloadExportActivities(start: string, end: string): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${BASE_URL}/api/export/activities?start=${start}&end=${end}`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`导出失败: HTTP ${res.status}`)
  const blob = await res.blob()
  _triggerDownload(blob, `activities_${start}_${end}.csv`)
}

/** 导出应用使用时长 CSV（安全下载） */
export async function downloadExportAppUsage(start: string, end: string): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${BASE_URL}/api/export/app-usage?start=${start}&end=${end}`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`导出失败: HTTP ${res.status}`)
  const blob = await res.blob()
  _triggerDownload(blob, `app_usage_${start}_${end}.csv`)
}

/** 创建备份（安全下载：使用 header 传 token） */
export async function downloadBackup(): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${BASE_URL}/api/backup`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`备份失败: HTTP ${res.status}`)
  const blob = await res.blob()
  const date = new Date().toISOString().slice(0, 10)
  _triggerDownload(blob, `xiaohei_backup_${date}.zip`)
}

/** 通用 Blob 下载触发器 */
function _triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** 更新活动记录（分类/摘要） */
export async function updateActivity(id: number, data: { category?: string; summary?: string }): Promise<{ status: string; id: number }> {
  const result = await request(`/api/activities/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return result as { status: string; id: number }
}

/** 删除活动记录（软删除，支持 undo） */
export async function deleteActivity(id: number): Promise<{ status: string; id: number; deleted: boolean }> {
  const result = await request(`/api/activities/${id}`, { method: 'DELETE' })
  return result as { status: string; id: number; deleted: boolean }
}

/** 撤销删除活动记录 */
export async function undoDeleteActivity(id: number): Promise<{ status: string; id: number; restored: boolean }> {
  const result = await request(`/api/activities/${id}/undo`, { method: 'POST' })
  return result as { status: string; id: number; restored: boolean }
}

/** 手动补录活动记录 */
export async function createActivity(data: {
  timestamp: string
  category: string
  summary?: string
  app_name?: string
  window_title?: string
  duration_min?: number
}): Promise<{ status: string }> {
  const result = await request('/api/activities', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return result as { status: string }
}

/** 搜索活动记录 */
export async function searchActivities(q: string, date?: string): Promise<Activity[]> {
  const d = date || new Date().toISOString().slice(0, 10)
  const data = await request(`/api/activities/search?q=${encodeURIComponent(q)}&date=${d}`) as { activities: Activity[] }
  return data.activities || []
}

// ─── Agent / Webhook 类型 ──────────────────────────

export interface Webhook {
  id: string
  name: string
  url: string
  type: 'feishu' | 'dingtalk' | 'wecom' | 'custom'
  events: string[]
  enabled: boolean
  created_at: string
}

/** 获取 Webhook 列表 */
export async function getWebhooks(): Promise<Webhook[]> {
  const data = await request('/api/webhooks') as { webhooks: Webhook[] }
  return data.webhooks || []
}

/** 添加 Webhook */
export async function addWebhook(wh: { url: string; name?: string; type?: string; events?: string[] }): Promise<Webhook> {
  const data = await request('/api/webhooks', {
    method: 'POST',
    body: JSON.stringify(wh),
  }) as { webhook: Webhook }
  return data.webhook
}

/** 删除 Webhook */
export async function deleteWebhook(id: string): Promise<{ status: string }> {
  return request(`/api/webhooks/${id}`, { method: 'DELETE' }) as Promise<{ status: string }>
}

/** 测试 Webhook */
export async function testWebhook(id: string): Promise<{ ok: boolean; message: string }> {
  return request(`/api/webhooks/${id}/test`, { method: 'POST' }) as Promise<{ ok: boolean; message: string }>
}

/** 启用/禁用 Webhook */
export async function toggleWebhook(id: string): Promise<{ status: string; enabled: boolean }> {
  return request(`/api/webhooks/${id}/toggle`, { method: 'POST' }) as Promise<{ status: string; enabled: boolean }>
}

/** 手动触发自动日报 + Webhook 推送 */
export async function triggerAutoReport(): Promise<{ status: string; report_generated: boolean; webhooks_pushed: number }> {
  return request('/api/agent/auto-report', { method: 'POST' }) as Promise<{ status: string; report_generated: boolean; webhooks_pushed: number }>
}

/** 获取自动日报配置 */
export type AutoReportConfig = { enabled: boolean; auto_time: string; auto_push: boolean }
export async function getAutoReportConfig(): Promise<AutoReportConfig> {
  return request('/api/auto-report/config') as Promise<AutoReportConfig>
}

/** 更新自动日报配置 */
export async function updateAutoReportConfig(config: { enabled?: boolean; auto_time?: string; auto_push?: boolean }): Promise<{ status: string; config: AutoReportConfig }> {
  return request('/api/auto-report/config', {
    method: 'POST',
    body: JSON.stringify(config),
  }) as Promise<{ status: string; config: AutoReportConfig }>
}

/** 获取备份信息 */
export async function getBackupInfo(): Promise<{ db_size_mb: number; activities_count: number; reports_count: number }> {
  return request('/api/backup/info') as Promise<{ db_size_mb: number; activities_count: number; reports_count: number }>
}

/** 从备份文件恢复数据 */
export async function restoreBackup(file: File): Promise<{ status: string; restored_files: string[] }> {
  const token = _apiToken
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${BASE_URL}/api/backup/restore`, {
    method: 'POST',
    headers: token ? { 'X-API-Token': token } : {},
    body: formData,
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
    throw new Error(data.error || '恢复失败')
  }
  return res.json()
}

/** 获取未读通知列表 */
export async function getNotifications(): Promise<{ notifications: Array<{ id: number; title: string; body: string; type: string; timestamp: string }> }> {
  return request('/api/notifications') as Promise<{ notifications: Array<{ id: number; title: string; body: string; type: string; timestamp: string }> }>
}

// ─── 应用分类规则 ──────────────────────────────────

/** 获取所有应用分类规则 */
export async function getAppRules(): Promise<{ rules: AppCategoryRule[] }> {
  return request('/api/app-rules') as Promise<{ rules: AppCategoryRule[] }>
}

/** 获取所有已记录应用及其规则 */
export async function getKnownApps(): Promise<{ apps: { app_name: string; rule?: AppCategoryRule }[] }> {
  return request('/api/app-rules/known') as Promise<{ apps: { app_name: string; rule?: AppCategoryRule }[] }>
}

/** 创建或更新应用分类规则 */
export async function updateAppRule(rule: Partial<AppCategoryRule> & { app_name: string }): Promise<{ status: string; rule: AppCategoryRule }> {
  return request('/api/app-rules', {
    method: 'POST',
    body: JSON.stringify(rule),
  }) as Promise<{ status: string; rule: AppCategoryRule }>
}

/** 删除应用分类规则 */
export async function deleteAppRule(appName: string): Promise<{ status: string; deleted: boolean }> {
  return request(`/api/app-rules/${encodeURIComponent(appName)}`, { method: 'DELETE' }) as Promise<{ status: string; deleted: boolean }>
}

/** 获取应用图标 URL（图标不敏感，无需 token） */
export async function getAppIconUrl(appName: string): Promise<string> {
  return `${BASE_URL}/api/icons/${encodeURIComponent(appName)}`
}

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

// ─── 分类配色映射 ────────────────────────────────
export const CATEGORY_COLORS: Record<string, string> = {
  '开发': '#00B894',
  '会议': '#E54D42',
  '沟通': '#5B8DEF',
  '文档': '#A29BFE',
  '测试': '#F0A030',
  '设计': '#FD79A8',
  '运维': '#00CEC9',
  '数据分析': '#55EFC4',
  '学习': '#6C5CE7',
  '管理': '#B2BEC3',
  '产品': '#635BFF',
  '生活': '#F0C040',
  '其他': '#9999B0',
}

/** 12大分类 */
export const CATEGORIES = [
  '开发', '会议', '沟通', '文档', '测试', '设计',
  '运维', '数据分析', '学习', '管理', '产品', '生活',
]

// ─── 数据校准 / 健康度 ──────────────────────────────

export interface SystemSession {
  start: string
  end: string
  raw_start?: string
  raw_end?: string
  duration_sec: number
  type: 'boot_session' | 'login_session'
  source: string
  truncated_start?: boolean
  truncated_end?: boolean
}

export interface HealthCoverage {
  date: string
  system: {
    total_uptime_min: number
    current_uptime_sec: number
    boot_count: number
    shutdown_count: number
    crash_count: number
    sessions: SystemSession[]
  }
  collected: {
    total_app_usage_min: number
    total_activities: number
    first_activity_time: string | null
    last_activity_time: string | null
    collector_running_min: number
  }
  gap: {
    missing_min: number
    coverage_pct: number
    missing_periods: Array<{
      start: string
      end: string
      reason: string
      duration_min?: number
    }>
  }
}

export interface HealthSystemEvents {
  date: string
  boot_events: Array<{ timestamp: string; event_type: string; source: string }>
  login_events: Array<{ timestamp: string; event_type: string; username: string }>
  sessions: SystemSession[]
  current_boot_time: string | null
  uptime_sec: number
}

export interface SamplingDeviation {
  date: string
  sample_count: number
  interval_count: number
  interval_stats: {
    min_sec: number
    max_sec: number
    avg_sec: number
    p50_sec: number
    p95_sec: number
  }
  expected_interval_sec: number
  deviation: {
    over_60s_count: number
    over_300s_count: number
    missed_estimates: number
  }
  intervals: number[]
}

export async function getHealthCoverage(date?: string): Promise<HealthCoverage> {
  const params = date ? `?date=${date}` : ''
  return await request(`/api/health/coverage${params}`) as HealthCoverage
}

export async function getHealthSystemEvents(date?: string): Promise<HealthSystemEvents> {
  const params = date ? `?date=${date}` : ''
  return await request(`/api/health/system-events${params}`) as HealthSystemEvents
}

export async function getSamplingDeviation(date?: string): Promise<SamplingDeviation> {
  const params = date ? `?date=${date}` : ''
  return await request(`/api/health/sampling-deviation${params}`) as SamplingDeviation
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

// ── 番茄钟 ──
export interface PomodoroSession {
  id: number
  start_time: string
  end_time: string | null
  duration_min: number
  task: string
  category: string
  status: 'running' | 'completed' | 'interrupted'
  interrupted_count: number
}

export async function startPomodoro(data: { task?: string; duration_min?: number; category?: string; todo_id?: number | null }): Promise<{ status: string; id: number; start_time: string }> {
  return request('/api/pomodoro/start', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number; start_time: string }>
}

export async function stopPomodoro(data: { id: number; status?: string; interrupted_count?: number }): Promise<{ status: string; end_time: string }> {
  return request('/api/pomodoro/stop', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; end_time: string }>
}

export async function getPomodoroSessions(date?: string): Promise<{ sessions: PomodoroSession[] }> {
  const params = date ? `?date=${date}` : ''
  return request(`/api/pomodoro/sessions${params}`) as Promise<{ sessions: PomodoroSession[] }>
}

export async function getPomodoroStats(range?: string): Promise<{ stats: Array<{ d: string; cnt: number; total_min: number }>; today: { count: number; total_min: number }; streak: number }> {
  return request(`/api/pomodoro/stats?range=${range || 'week'}`) as Promise<{ stats: Array<{ d: string; cnt: number; total_min: number }>; today: { count: number; total_min: number }; streak: number }>
}

// ── 待办清单 ──
export interface Todo {
  id: number
  title: string
  category: string
  mode: 'timer' | 'goal' | 'habit'
  target_min: number
  repeat_type: string
  repeat_days: string
  due_date: string | null
  priority: number
  status: 'pending' | 'in_progress' | 'completed' | 'archived'
  progress_min: number
  pomodoro_count: number
  created_at: string
  completed_at: string | null
}

export async function getTodos(status?: string): Promise<{ todos: Todo[] }> {
  const params = status ? `?status=${status}` : ''
  return request(`/api/todos${params}`) as Promise<{ todos: Todo[] }>
}

export async function createTodo(data: { title: string; category?: string; mode?: string; target_min?: number; priority?: number; due_date?: string }): Promise<{ status: string; id: number }> {
  return request('/api/todos', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number }>
}

export async function updateTodo(id: number, data: Partial<Todo>): Promise<{ status: string }> {
  return request(`/api/todos/${id}`, { method: 'PUT', body: JSON.stringify(data) }) as Promise<{ status: string }>
}

export async function deleteTodo(id: number): Promise<{ status: string }> {
  return request(`/api/todos/${id}`, { method: 'DELETE' }) as Promise<{ status: string }>
}

// ── 每日日记 ──
export interface Diary {
  id: number
  diary_date: string
  mood: string
  weather: string
  content: string
  tags: string
  highlights: string
  gratitude: string
  created_at: string
  updated_at: string
}

export async function getDiary(diaryDate: string): Promise<{ diary: Diary | null }> {
  return request(`/api/diaries/${diaryDate}`) as Promise<{ diary: Diary | null }>
}

export async function saveDiary(data: Partial<Diary>): Promise<{ status: string; diary_date: string }> {
  return request('/api/diaries', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; diary_date: string }>
}

export async function getDiaries(limit?: number): Promise<{ diaries: Diary[]; dates: string[] }> {
  return request(`/api/diaries/list?limit=${limit || 30}`) as Promise<{ diaries: Diary[]; dates: string[] }>
}

// ── 成就系统 ──
export interface Achievement {
  id: number
  code: string
  name: string
  description: string
  icon: string
  unlocked_at: string | null
}

export async function getAchievements(): Promise<{ achievements: Achievement[] }> {
  return request('/api/achievements') as Promise<{ achievements: Achievement[] }>
}

export async function checkAchievements(): Promise<{ unlocked: Array<{ code: string; name: string; icon: string }> }> {
  return request('/api/achievements/check', { method: 'POST' }) as Promise<{ unlocked: Array<{ code: string; name: string; icon: string }> }>
}

export async function getQuote(): Promise<{ quote: string }> {
  return request('/api/achievements/quote') as Promise<{ quote: string }>
}

// ── 倒数日 ──
export interface Countdown {
  id: number
  title: string
  target_date: string
  color: string
  created_at: string
}

export async function getCountdowns(): Promise<{ countdowns: Countdown[] }> {
  return request('/api/countdowns') as Promise<{ countdowns: Countdown[] }>
}

export async function createCountdown(data: { title: string; target_date: string; color?: string }): Promise<{ status: string; id: number }> {
  return request('/api/countdowns', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number }>
}

export async function deleteCountdown(id: number): Promise<{ status: string }> {
  return request(`/api/countdowns/${id}`, { method: 'DELETE' }) as Promise<{ status: string }>
}

// ── AI对话 ──
export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export async function aiChat(message: string, signal?: AbortSignal): Promise<{ reply: string; role: string }> {
  return request('/api/ai/chat', { method: 'POST', body: JSON.stringify({ message }), signal }, 30000) as Promise<{ reply: string; role: string }>
}

export async function getChatHistory(): Promise<{ history: ChatMessage[] }> {
  return request('/api/ai/chat/history') as Promise<{ history: ChatMessage[] }>
}

export async function clearChatHistory(): Promise<{ status: string }> {
  return request('/api/ai/chat/clear', { method: 'DELETE' }) as Promise<{ status: string }>
}

// ── 习惯追踪 ──
export interface Habit {
  id: number
  name: string
  target_count: number
  period: string
  color: string
  sort_order: number
}

export interface HabitLog {
  id: number
  habit_id: number
  log_date: string
  count: number
}

export async function getHabits(): Promise<{ habits: Habit[]; logs: HabitLog[] }> {
  return request('/api/habits') as Promise<{ habits: Habit[]; logs: HabitLog[] }>
}

export async function createHabit(data: { name: string; target_count?: number; period?: string; color?: string }): Promise<{ status: string; id: number }> {
  return request('/api/habits', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number }>
}

export async function logHabit(habitId: number, logDate?: string, count?: number): Promise<{ status: string }> {
  return request(`/api/habits/${habitId}/log`, { method: 'POST', body: JSON.stringify({ log_date: logDate, count }) }) as Promise<{ status: string }>
}

export async function deleteHabit(id: number): Promise<{ status: string }> {
  return request(`/api/habits/${id}`, { method: 'DELETE' }) as Promise<{ status: string }>
}

// ── 导出 ──
export function getExportExcelUrl(date?: string): string {
  const d = date || new Date().toISOString().substring(0, 10)
  return `${BASE_URL}/api/exports/excel?date=${d}`
}

export function getExportJsonUrl(date?: string): string {
  const d = date || new Date().toISOString().substring(0, 10)
  return `${BASE_URL}/api/exports/json?date=${d}`
}

// ── 周计划（月/周/日三级层级 + 拖拽分配 + 番茄数据条） ──

export type TaskLevel = 'month' | 'week' | 'day'

export interface TodoV2 extends Todo {
  parent_id: number | null
  task_level: TaskLevel
  assigned_date: string | null
  week_start: string | null
  month_key: string | null
  color: string
}

export interface MonthTask extends TodoV2 {
  children: TodoV2[]
  total_target_min: number
  total_progress_min: number
  progress_pct: number
}

export interface MonthPlanData {
  month_key: string
  month_tasks: MonthTask[]
  title: string
  goal: string
}

export interface WeekPlanData {
  week_start: string
  dates: string[]
  week_tasks: TodoV2[]
  day_tasks: Record<string, TodoV2[]>
  title: string
  goal: string
}

export interface WeekPlanStats {
  week_start: string
  dates: string[]
  daily_focus: Array<{ date: string; focus_min: number }>
  total_focus_min: number
  deep_focus_min: number
  interrupt_count: number
  total_tasks: number
  completed_tasks: number
  completion_rate: number
  streak_days: number
}

export interface MonthPlanStats {
  month_key: string
  total_focus_min: number
  deep_focus_min: number
  interrupt_count: number
  total_tasks: number
  completed_tasks: number
  completion_rate: number
}

export async function getMonthPlan(monthKey: string): Promise<MonthPlanData> {
  return request(`/api/week-plan/month/${monthKey}`) as Promise<MonthPlanData>
}

export async function getWeekPlan(weekStart: string): Promise<WeekPlanData> {
  return request(`/api/week-plan/week/${weekStart}`) as Promise<WeekPlanData>
}

export async function getUnassignedTodos(): Promise<{ todos: TodoV2[] }> {
  return request('/api/week-plan/unassigned') as Promise<{ todos: TodoV2[] }>
}

export async function assignTodo(data: { todo_id: number; assigned_date?: string; week_start?: string; task_level?: TaskLevel }): Promise<{ status: string }> {
  return request('/api/week-plan/assign', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string }>
}

export async function unassignTodo(todo_id: number): Promise<{ status: string }> {
  return request('/api/week-plan/unassign', { method: 'POST', body: JSON.stringify({ todo_id }) }) as Promise<{ status: string }>
}

export async function splitTask(data: { parent_id: number; title: string; week_start: string; task_level?: TaskLevel; category?: string; mode?: string; target_min?: number; priority?: number }): Promise<{ status: string; id: number }> {
  return request('/api/week-plan/split', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number }>
}

export async function updatePlanMeta(data: { plan_type: 'month' | 'week'; plan_key: string; title?: string; goal?: string }): Promise<{ status: string }> {
  return request('/api/week-plan/meta', { method: 'PUT', body: JSON.stringify(data) }) as Promise<{ status: string }>
}

export async function getWeekPlanStats(weekStart: string): Promise<WeekPlanStats> {
  return request(`/api/week-plan/stats?range=week&date=${weekStart}`) as Promise<WeekPlanStats>
}

export async function getMonthPlanStats(monthKey: string): Promise<MonthPlanStats> {
  return request(`/api/week-plan/stats?range=month&date=${monthKey}`) as Promise<MonthPlanStats>
}

export async function getTodayTodos(): Promise<{ todos: TodoV2[]; date: string }> {
  return request('/api/week-plan/today') as Promise<{ todos: TodoV2[]; date: string }>
}

// 工具函数：ISO 8601 周一日期
export function getWeekStart(d: Date = new Date()): string {
  const date = new Date(d)
  const day = date.getDay() // 0=周日, 1=周一
  const diff = day === 0 ? -6 : 1 - day // 周日回到上周一
  date.setDate(date.getDate() + diff)
  return date.toISOString().substring(0, 10)
}

// 工具函数：从日期字符串获取周一开始的 7 天
export function getWeekDates(weekStart: string): string[] {
  const start = new Date(weekStart)
  const dates: string[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    dates.push(d.toISOString().substring(0, 10))
  }
  return dates
}

// 工具函数：获取月份 key
export function getMonthKey(d: Date = new Date()): string {
  return d.toISOString().substring(0, 7)
}
