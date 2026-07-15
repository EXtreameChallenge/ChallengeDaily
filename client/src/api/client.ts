// 后端 API 基础 URL：优先从 Electron 主进程获取端口，兼容非 Electron 环境
let BASE_URL = 'http://127.0.0.1:58888'

// 异步初始化 BASE_URL 的 Promise（避免启动初期竞态：模块加载时端口尚未就绪）
let _baseUrlPromise: Promise<void> | null = null
function ensureBaseUrl(): Promise<void> {
  if (_baseUrlPromise) return _baseUrlPromise
  _baseUrlPromise = (async () => {
    if (typeof window !== 'undefined' && window.electronAPI?.getBackendPort) {
      try {
        const port = await window.electronAPI.getBackendPort()
        if (port) BASE_URL = `http://127.0.0.1:${port}`
      } catch {
        // 保留默认 BASE_URL
      }
    }
  })()
  return _baseUrlPromise
}

// 启动时也立即触发一次（兼容现有调用模式）
ensureBaseUrl()

// 导出供 SSE 等场景使用
export function getBaseUrl(): string { return BASE_URL }
export { getApiToken, ensureBaseUrl }

// ── 后端连接状态管理（企业级断线重连机制） ──
type BackendState = 'connected' | 'disconnected' | 'connecting'
let _backendState: BackendState = 'connecting'
const _stateListeners = new Set<(s: BackendState) => void>()

// 连续失败计数：只有连续多次失败才标记disconnected，避免单次超时误判
let _consecutiveFailures = 0
const _DISCONNECT_THRESHOLD = 3  // 连续3次失败才标记断连（从2提升到3，减少偶发超时误判）

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
function markRequestSuccess() {
  _consecutiveFailures = 0
  setBackendState('connected')
}
function markRequestFailure() {
  _consecutiveFailures++
  if (_consecutiveFailures >= _DISCONNECT_THRESHOLD) {
    setBackendState('disconnected')
  }
}

// ── API Token 管理 ──
let _apiToken = ''
let _tokenPromise: Promise<string> | null = null

async function _fetchTokenOnce(): Promise<string> {
  if (!window.electronAPI?.getApiToken) return ''
  try {
    const t = await window.electronAPI.getApiToken()
    return (t || '').trim()
  } catch {
    return ''
  }
}

async function getApiToken(): Promise<string> {
  // 有有效缓存时直接返回；空缓存不返回，继续尝试读取
  if (_apiToken) return _apiToken

  // 避免并发重复请求：但空结果不缓存，下次调用仍会重试
  if (!_tokenPromise) {
    _tokenPromise = (async () => {
      // 启动阶段 token 文件可能尚未写入，最多重试 10 次，每次 300ms
      for (let i = 0; i < 10; i++) {
        const t = await _fetchTokenOnce()
        if (t) {
          _apiToken = t
          _tokenPromise = null
          return t
        }
        if (i < 9) await new Promise(r => setTimeout(r, 300))
      }
      _tokenPromise = null
      return ''
    })()
  }
  return _tokenPromise
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
export async function request(endpoint: string, options?: RequestInit, timeoutMs = 10000, _retryCount = 0): Promise<unknown> {
  // 确保 BASE_URL 已初始化（避免启动初期端口尚未就绪导致请求失败）
  await ensureBaseUrl()
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
    // 不再每次请求都设connecting——高频轮询时会导致UI闪烁
    // 只在真正断连后才设connecting
    if (_backendState === 'disconnected') setBackendState('connecting')
    const res = await fetch(`${BASE_URL}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-API-Token': token } : {}),
      },
      signal: controller.signal,
      ...restOptions,
    })
    if (res.status === 401) {
      // Token 失效/未就绪：清除缓存，短暂等待后重试（最多 3 次）
      // 启动阶段 token 文件可能稍后写入，避免直接判定认证失败
      if (_retryCount < 3) {
        invalidateToken()
        if (_retryCount === 0) {
          // 首次 401 时给后端一点写入 token 的时间
          await new Promise(r => setTimeout(r, 500))
        }
        return request(endpoint, options, timeoutMs, _retryCount + 1)
      }
      throw new Error('认证失败，请重新启动应用')
    }
    if (!res.ok) {
      // 后端已响应但返回错误码（4xx/5xx）——后端在线，只是业务逻辑出错
      // 不应标记为 disconnected，否则会误报"后端服务断开"
      markRequestSuccess()
      throw new Error(`请求失败: ${res.status}`)
    }
    const data = await res.json()
    markRequestSuccess()
    return data
  } catch (err: unknown) {
    // 外部 signal 主动取消：不更新断连状态，向上抛出 AbortError 供调用方识别
    if (externalSignal?.aborted) {
      throw new DOMException('请求已被取消', 'AbortError')
    }
    // 累计连续失败次数，达到阈值才标记disconnected
    markRequestFailure()
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

// ── 自定义日报模板 ──
export interface CustomTemplate {
  id: number
  name: string
  content: string
}
export async function getCustomTemplates(): Promise<{ templates: CustomTemplate[] }> {
  const data = await request('/api/reports/templates')
  return data as { templates: CustomTemplate[] }
}
export async function saveCustomTemplate(name: string, content: string): Promise<{ status: string; templates: CustomTemplate[] }> {
  const data = await request('/api/reports/templates', {
    method: 'POST',
    body: JSON.stringify({ name, content }),
  })
  return data as { status: string; templates: CustomTemplate[] }
}
export async function deleteCustomTemplate(id: number): Promise<{ status: string; templates: CustomTemplate[] }> {
  const data = await request(`/api/reports/templates?id=${id}`, { method: 'DELETE' })
  return data as { status: string; templates: CustomTemplate[] }
}

/** 获取已有日报内容 */
export async function getDailyReportContent(): Promise<ReportContent> {
  const data = await request('/api/report/daily/content')
  return data as ReportContent
}

/** 番茄统计汇总（供日报番茄统计卡片渲染） */
export interface PomodoroSummary {
  date: string
  total: number
  completed: number
  total_min: number
  distractions: number
}

export async function getPomodoroSummary(date?: string): Promise<PomodoroSummary> {
  const params = date ? `?date=${date}` : ''
  return await request(`/api/report/pomodoro-summary${params}`) as PomodoroSummary
}

/** 数据可信度（供日报可信度卡片渲染） */
export interface DailyCredibility {
  date: string
  credibility_score: number
  coverage_rate: number
  missing_periods: unknown[]
  sampling_deviation: number
  level: 'high' | 'medium' | 'low'
}

export async function getDailyCredibility(): Promise<DailyCredibility> {
  return await request('/api/credibility/daily-report') as DailyCredibility
}

/** 手动截图 */
export async function captureNow(): Promise<{ ok: boolean }> {
  const data = await request('/api/capture', { method: 'POST' })
  return data as { ok: boolean }
}

/** 健康检查（轻量模式：跳过磁盘/DB/AI检查，仅确认进程存活） */
export async function healthCheck(): Promise<{ status: string }> {
  const data = await request('/api/health?quick=1', {}, 5000)
  return data as { status: string }
}

/** 启动阶段健康检查（绕过 request 状态机，不影响断连计数）
 *  用于 App.tsx 的初始轮询，避免启动阶段的多次失败被误判为"后端断开"
 */
export async function startupHealthCheck(): Promise<boolean> {
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000)
    const port = window.electronAPI?.getBackendPort
      ? await window.electronAPI.getBackendPort()
      : 58888
    const res = await fetch(`http://127.0.0.1:${port}/api/health?quick=1`, {
      signal: controller.signal,
    })
    clearTimeout(timeoutId)
    return res.ok
  } catch {
    return false
  }
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

// 分心热点图：24小时分心次数分布
export interface DistractionHeatmapEntry {
  hour: number
  count: number
  duration_min: number
}
export async function getDistractionHeatmap(days = 7): Promise<{ heatmap: DistractionHeatmapEntry[]; days: number }> {
  const data = await request(`/api/stats/distraction-heatmap?days=${days}`)
  return data as { heatmap: DistractionHeatmapEntry[]; days: number }
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

// ── P8-4：CSV/Excel 原始数据导出增强 ──

/** 导出历史报告（CSV / JSON） */
export async function downloadExportReports(start: string, end: string, format: 'csv' | 'json' = 'csv'): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${BASE_URL}/api/exports/reports?format=${format}&start=${start}&end=${end}`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`导出失败: HTTP ${res.status}`)
  const blob = await res.blob()
  _triggerDownload(blob, `reports_${start}_${end}.${format}`)
}

/** 导出活动明细聚合 CSV（多日期范围） */
export async function downloadExportActivitiesDetail(start: string, end: string): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${BASE_URL}/api/exports/activities-detail?start=${start}&end=${end}`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`导出失败: HTTP ${res.status}`)
  const blob = await res.blob()
  _triggerDownload(blob, `activities_detail_${start}_${end}.csv`)
}

// ── P10-3：数据导入（Toggl / RescueTime CSV） ──
export interface ImportResult {
  status: string
  source: string
  parsed: number
  inserted: number
  message?: string
  dry_run?: boolean
  sample?: Array<Record<string, unknown>>
}
export async function importTogglCsv(csv: string, dryRun = false): Promise<ImportResult> {
  return request('/api/imports/toggl', {
    method: 'POST',
    body: JSON.stringify({ csv, dry_run: dryRun }),
  }) as Promise<ImportResult>
}
export async function importRescueTimeCsv(csv: string, dryRun = false): Promise<ImportResult> {
  return request('/api/imports/rescuetime', {
    method: 'POST',
    body: JSON.stringify({ csv, dry_run: dryRun }),
  }) as Promise<ImportResult>
}

// P15-3：数据自毁（永久删除所有用户数据）
export interface WipeResult {
  status: string
  message: string
  deleted: {
    db_tables: Record<string, number>
    screenshots: number
    reports: number
  }
}

export async function wipeAllData(confirmText: string): Promise<WipeResult> {
  return request('/api/exports/wipe', {
    method: 'POST',
    body: JSON.stringify({ confirm: true, confirm_text: confirmText }),
  }) as Promise<WipeResult>
}

// ── P10-4：赛季成就 ──
export interface SeasonAchievement {
  key: string
  name: string
  desc: string
  target: number
  metric: string
  reward: string
  current: number
  progress_pct: number
  unlocked: boolean
}
export interface SeasonData {
  season_key: string
  start_date: string
  end_date: string
  achievements: SeasonAchievement[]
  unlocked_count: number
  total_count: number
}
export async function getSeason(month?: string): Promise<SeasonData> {
  const m = month ? `?month=${month}` : ''
  return request(`/api/achievements/season${m}`) as Promise<SeasonData>
}
export interface SeasonHistoryItem {
  season_key: string
  unlocked_count: number
  total_count: number
  achievements: Array<{ key: string; name: string; unlocked: boolean; current: number; target: number }>
}
export async function getSeasonHistory(months = 6): Promise<{ history: SeasonHistoryItem[] }> {
  return request(`/api/achievements/season/history?months=${months}`) as Promise<{ history: SeasonHistoryItem[] }>
}

/** 创建备份（安全下载：使用 header 传 token） */
export async function downloadBackup(): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${BASE_URL}/api/backup`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`备份失败: HTTP ${res.status}`)
  const blob = await res.blob()
  const date = formatLocalDate(new Date())
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
  const d = date || formatLocalDate(new Date())
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
  const token = await getApiToken()
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
  todo_id: number | null
  pomodoro_index: number
  total_pomodoros: number
}

// 番茄钟大小配置
export interface PomodoroSizeConfig {
  work: number       // 工作分钟
  short_break: number  // 短休息分钟
  long_break: number   // 长休息分钟
}

export const POMODORO_SIZES: Record<string, PomodoroSizeConfig> = {
  big:   { work: 25, short_break: 5, long_break: 15 },
  small: { work: 20, short_break: 10, long_break: 15 },
}
export const LONG_BREAK_INTERVAL = 4

export async function startPomodoro(data: { task?: string; duration_min?: number; category?: string; todo_id?: number | null; pomodoro_index?: number; total_pomodoros?: number; lock_level?: number; custom_blacklist?: string[] }): Promise<{ status: string; id: number; start_time: string; todo_id: number | null; duration_min: number; pomodoro_index: number; total_pomodoros: number }> {
  return request('/api/pomodoro/start', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number; start_time: string; todo_id: number | null; duration_min: number; pomodoro_index: number; total_pomodoros: number }>
}

export async function stopPomodoro(data: { id: number; status?: string; interrupted_count?: number }): Promise<{ status: string; end_time: string }> {
  return request('/api/pomodoro/stop', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; end_time: string }>
}

// ── 日报多渠道提交 ──
export interface ReportChannelConfig {
  type: 'email' | 'feishu_report' | 'dingtalk_report' | 'wecom_report'
  config: Record<string, string>
  enabled: boolean
  label?: string
}

export async function getReportChannels(): Promise<{ channels: ReportChannelConfig[] }> {
  return request('/api/report-channels/config') as Promise<{ channels: ReportChannelConfig[] }>
}

export async function saveReportChannels(channels: ReportChannelConfig[]): Promise<{ status: string }> {
  return request('/api/report-channels/config', { method: 'POST', body: JSON.stringify({ channels }) }) as Promise<{ status: string }>
}

export async function testReportChannel(type: string, config: Record<string, string>): Promise<{ success: boolean; message: string; channel: string }> {
  return request('/api/report-channels/test', { method: 'POST', body: JSON.stringify({ type, config }) }) as Promise<{ success: boolean; message: string; channel: string }>
}

export async function submitReportToChannels(report_text: string, report_date?: string): Promise<{ status: string; total: number; success: number; results: Array<{ channel: string; success: boolean; message: string }> }> {
  return request('/api/report-channels/submit', { method: 'POST', body: JSON.stringify({ report_text, report_date }) }) as Promise<{ status: string; total: number; success: number; results: Array<{ channel: string; success: boolean; message: string }> }>
}

// ── 日报质量4维评分 ──
export interface ReportQualityDimension {
  score: number
  detail: Record<string, number | boolean>
  suggestion: string
}
export interface ReportQualityResult {
  total: number
  grade: string
  dimensions: {
    completeness: ReportQualityDimension
    data_backed: ReportQualityDimension
    actionability: ReportQualityDimension
    readability: ReportQualityDimension
  }
  weights: Record<string, number>
  overall_suggestion: string
}
export async function scoreReportQuality(text: string): Promise<ReportQualityResult> {
  return request('/api/report-channels/quality', { method: 'POST', body: JSON.stringify({ text }) }) as Promise<ReportQualityResult>
}

// ── 番茄自习室 ──
export interface StudyRoomMember {
  id: string; name: string; status: string; task: string;
  started_at: string | null; today_min: number; today_count: number;
  ip: string; is_self: boolean; last_heartbeat: number;
}
export async function getStudyRoomStatus(): Promise<{ members: StudyRoomMember[]; leaderboard: StudyRoomMember[]; online_count: number; focusing_count: number }> {
  return request('/api/study-room/status') as Promise<{ members: StudyRoomMember[]; leaderboard: StudyRoomMember[]; online_count: number; focusing_count: number }>
}
export async function updateStudyRoomStatus(status: string, task: string = '', started_at: string | null = null): Promise<{ status: string }> {
  return request('/api/study-room/update', { method: 'POST', body: JSON.stringify({ status, task, started_at }) }) as Promise<{ status: string }>
}
export async function broadcastStudyRoom(): Promise<{ status: string; broadcasted: number; subnet: string }> {
  return request('/api/study-room/broadcast', { method: 'POST' }) as Promise<{ status: string; broadcasted: number; subnet: string }>
}

// ── 长期目标管理（GoalDay集大成） ──
export interface Goal {
  id: number
  title: string
  description: string
  category: 'personal' | 'work' | 'health' | 'learning' | 'finance'
  timeframe: 'yearly' | 'quarterly' | 'monthly'
  start_date: string
  target_date: string
  status: 'active' | 'completed' | 'archived'
  progress: number
  key_results: Array<{ text: string; done: boolean }>
  linked_todos: number[]
  linked_habits: number[]
  color: string
  created_at: string
  updated_at: string
}
export interface MoodEntry { date: string; mood: string }

export async function getGoals(status?: string, timeframe?: string): Promise<{ goals: Goal[] }> {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (timeframe) params.set('timeframe', timeframe)
  const qs = params.toString()
  return request(`/api/goals${qs ? '?' + qs : ''}`) as Promise<{ goals: Goal[] }>
}
export async function createGoal(data: Partial<Goal>): Promise<{ status: string; id: number }> {
  return request('/api/goals', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number }>
}
export async function updateGoal(id: number, data: Partial<Goal>): Promise<{ status: string }> {
  return request(`/api/goals/${id}`, { method: 'PUT', body: JSON.stringify(data) }) as Promise<{ status: string }>
}
export async function deleteGoal(id: number): Promise<{ status: string }> {
  return request(`/api/goals/${id}`, { method: 'DELETE' }) as Promise<{ status: string }>
}
export async function getMoodHeatmap(year?: number): Promise<{ data: MoodEntry[]; year: number | null }> {
  const qs = year ? `?year=${year}` : ''
  return request(`/api/goals/mood-heatmap${qs}`) as Promise<{ data: MoodEntry[]; year: number | null }>
}
export async function getGoalProgress(id: number): Promise<{ total_todos: number; completed_todos: number; auto_progress: number }> {
  return request(`/api/goals/${id}/progress`) as Promise<{ total_todos: number; completed_todos: number; auto_progress: number }>
}
export async function getGoalSummary(): Promise<{ goals: Array<{ id: number; title: string; category: string; timeframe: string; target_date: string; progress: number; color: string; status: string }> }> {
  return request('/api/goals/summary') as Promise<{ goals: Array<{ id: number; title: string; category: string; timeframe: string; target_date: string; progress: number; color: string; status: string }> }>
}

// ── 数据迁移导入 ──
export interface ImportPreview {
  source: string
  format: string
  total_rows: number
  sample: Array<Record<string, unknown>>
  detected_type: string
}
export interface ImportResult {
  total: number
  imported: number
  skipped: number
  errors: string[]
  dry_run?: boolean
  target_table?: string
}
export async function previewImport(source: string, format: 'json' | 'csv', data: string): Promise<ImportPreview> {
  return request('/api/data-import/preview', { method: 'POST', body: JSON.stringify({ source, format, data }) }) as Promise<ImportPreview>
}
export async function executeImport(source: string, format: 'json' | 'csv', data: string, target_table?: string, dry_run?: boolean): Promise<ImportResult> {
  return request('/api/data-import/execute', { method: 'POST', body: JSON.stringify({ source, format, data, target_table, dry_run }) }) as Promise<ImportResult>
}

// ── 规则引擎 ──
export interface Rule {
  id: number; name: string; description: string;
  trigger_type: string; trigger_params: string;
  action_type: string; action_params: string;
  enabled: number; created_at: string; last_fired_at: string | null;
}
export interface RuleEvalResult {
  rule_id: number; rule_name: string; action: string;
  params: Record<string, unknown>; message: string; triggered_at: string;
}
export async function getRules(): Promise<{ rules: Rule[]; triggers: Record<string, string>; actions: Record<string, string> }> {
  return request('/api/rules/list') as Promise<{ rules: Rule[]; triggers: Record<string, string>; actions: Record<string, string> }>
}
export async function toggleRule(id: number, enabled: boolean): Promise<{ status: string }> {
  return request('/api/rules/toggle', { method: 'POST', body: JSON.stringify({ id, enabled }) }) as Promise<{ status: string }>
}
export async function evaluateRules(): Promise<{ triggered: RuleEvalResult[]; count: number }> {
  return request('/api/rules/evaluate') as Promise<{ triggered: RuleEvalResult[]; count: number }>
}

export async function getPomodoroSessions(date?: string): Promise<{ sessions: PomodoroSession[] }> {
  const params = date ? `?date=${date}` : ''
  return request(`/api/pomodoro/sessions${params}`) as Promise<{ sessions: PomodoroSession[] }>
}

export async function getPomodoroStats(range?: string): Promise<{ stats: Array<{ d: string; cnt: number; total_min: number }>; today: { count: number; total_min: number }; streak: number }> {
  return request(`/api/pomodoro/stats?range=${range || 'week'}`) as Promise<{ stats: Array<{ d: string; cnt: number; total_min: number }>; today: { count: number; total_min: number }; streak: number }>
}

export interface PomodoroQuality {
  score: number; grade: string; total_min: number;
  completed: number; total: number; purity: number;
  completion: number; distraction_count: number;
}
export async function getPomodoroQuality(date?: string): Promise<PomodoroQuality> {
  const q = date ? `?date=${date}` : ''
  return request(`/api/pomodoro/quality${q}`) as Promise<PomodoroQuality>
}

// 番茄运行期间分心检测（前端定时调用，由后端查询前台应用分类）
export async function checkPomodoroDistraction(sessionId: number): Promise<{ is_distraction: boolean; category: string; app_name: string; distraction_count: number }> {
  return request('/api/pomodoro/distraction-check', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  }) as Promise<{ is_distraction: boolean; category: string; app_name: string; distraction_count: number }>
}

// ── P9-3：番茄钟增强 ──
export interface SmartDurationResult {
  recommended_min: number
  reason: string
  analysis: Array<{
    duration_min: number
    total: number
    completed: number
    interrupted: number
    completion_rate: number
    interrupt_rate: number
    avg_distractions: number
    score: number
  }>
}
export async function getSmartDuration(): Promise<SmartDurationResult> {
  return request('/api/pomodoro/smart-duration') as Promise<SmartDurationResult>
}

export interface PomodoroReport {
  range_days: number
  total_sessions: number
  completed_sessions?: number
  interrupted_sessions?: number
  completion_rate?: number
  total_focus_min?: number
  total_focus_hour?: number
  avg_distractions_per_session?: number
  best_period?: string | null
  best_period_completion_rate?: number | null
  period_stats?: Record<string, { total: number; completed: number; min: number; distractions: number }>
  category_stats?: Record<string, number>
  daily_trend?: Array<{ date: string; total: number; completed: number; min: number }>
  linked_task_count?: number
  linked_task_ratio?: number
  suggestions?: string[]
  message?: string
}
export async function getPomodoroReport(days = 7): Promise<PomodoroReport> {
  return request(`/api/pomodoro/report?days=${days}`) as Promise<PomodoroReport>
}

// ── P9-4：日历视图 ──
export interface CalendarDay {
  date: string
  total_min: number
  dominant_cat: string | null
  cats: Record<string, number>
  level: 0 | 1 | 2 | 3 | 4
}
export interface CalendarViewData {
  month: string
  days: CalendarDay[]
  category_totals: Record<string, number>
  legend: Array<{ cat: string; color: string }>
}
export async function getCalendarView(month?: string): Promise<CalendarViewData> {
  const m = month ? `?month=${month}` : ''
  return request(`/api/stats/calendar${m}`) as Promise<CalendarViewData>
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
  estimated_pomodoros: number
  pomodoro_size: 'big' | 'small'
  goal_id?: number | null
}

export async function getTodos(status?: string): Promise<{ todos: Todo[] }> {
  const params = status ? `?status=${status}` : ''
  return request(`/api/todos${params}`) as Promise<{ todos: Todo[] }>
}

export async function createTodo(data: { title: string; category?: string; mode?: string; target_min?: number; priority?: number; due_date?: string; task_level?: string; assigned_date?: string; week_start?: string; month_key?: string; parent_id?: number; estimated_pomodoros?: number; pomodoro_size?: string; goal_id?: number | null }): Promise<{ status: string; id: number }> {
  return request('/api/todos', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number }>
}

export async function updateTodo(id: number, data: Partial<Todo>): Promise<{ status: string }> {
  return request(`/api/todos/${id}`, { method: 'PUT', body: JSON.stringify(data) }) as Promise<{ status: string }>
}

export async function deleteTodo(id: number): Promise<{ status: string }> {
  return request(`/api/todos/${id}`, { method: 'DELETE' }) as Promise<{ status: string }>
}

// ── 每日日记 ──
export interface DiaryMedia {
  type: 'image' | 'audio' | 'link'
  url: string
  title?: string
  thumbnail?: string
  duration?: number
}
export interface Diary {
  id: number
  diary_date: string
  mood: string
  weather: string
  content: string
  tags: string
  highlights: string
  gratitude: string
  media_json: string
  font_style: string
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

// ── P8-1: 报告全文检索 ──
export interface ReportSearchResult {
  id: number
  report_date: string
  content: string
  created_at: string
  snippet: string
}

export async function searchReports(q: string, limit = 20): Promise<{ results: ReportSearchResult[]; query: string; count: number }> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  return request(`/api/report/search?${params.toString()}`) as Promise<{ results: ReportSearchResult[]; query: string; count: number }>
}

// ── P9-2: AI 主动洞察推送 ──
export interface MorningInsight {
  type: 'positive' | 'suggestion' | 'warning' | 'care' | 'fun'
  title: string
  body: string
}

export async function getMorningInsights(force = false): Promise<{ date: string; insights: MorningInsight[]; count: number }> {
  const params = force ? '?force=1' : ''
  return request(`/api/insight/morning${params}`) as Promise<{ date: string; insights: MorningInsight[]; count: number }>
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

// SSE 流式事件类型
export type ChatStreamEvent =
  | { type: 'content'; content: string }
  | { type: 'tool_call'; name: string; id: string }
  | { type: 'tool_result'; name: string; id: string; result: string }
  | { type: 'done' }
  | { type: 'error'; content: string }

// 操作确认数据
export interface ActionConfirmation {
  action: string
  data: Record<string, any>
  confirm_message: string
}

/** 流式对话：返回一个可读的SSE流 */
export async function aiChatStream(
  message: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = await getApiToken()
  // 修复：使用模块级 BASE_URL 而非未定义的 getApiPort()
  const url = `${BASE_URL}/api/ai/chat/stream`
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-API-Token': token } : {}),
    },
    body: JSON.stringify({ message }),
    signal,
  })
  if (!res.ok) {
    const errText = await res.text().catch(() => '')
    throw new Error(errText || `HTTP ${res.status}`)
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6)) as ChatStreamEvent
          onEvent(event)
        } catch {}
      }
    }
  }
}

/** 执行操作（用户确认后调用） */
export async function executeChatAction(action: string, data: Record<string, any>): Promise<{ status: string; message: string }> {
  return request('/api/ai/chat/execute', { method: 'POST', body: JSON.stringify({ action, data }) }) as Promise<{ status: string; message: string }>
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

// ── AI 教练：周复盘 / 目标点评 / 智能排程 ──

export interface WeeklyReview {
  review: string
  score: number
  highlights: string[]
  suggestions: string[]
}

export interface GoalProgressComment {
  comment: string
  encouragement: string
}

export interface ScheduleSuggestion {
  todo_id: number | null
  suggested_day: string
  suggested_time: string
  reason: string
}

export interface SmartScheduleResult {
  suggestions: ScheduleSuggestion[]
  message?: string
}

/** AI 周复盘 */
export async function aiWeeklyReview(weekStart?: string): Promise<WeeklyReview> {
  return request('/api/ai/weekly-review', {
    method: 'POST',
    body: JSON.stringify({ week_start: weekStart }),
  }, 30000) as Promise<WeeklyReview>
}

/** AI 目标进度点评 */
export async function aiGoalProgressComment(
  level: 'month' | 'week' | 'day',
  progress: number,
  tasks?: Array<Record<string, any>>,
): Promise<GoalProgressComment> {
  return request('/api/ai/goal-progress-comment', {
    method: 'POST',
    body: JSON.stringify({ level, progress, tasks }),
  }, 30000) as Promise<GoalProgressComment>
}

/** AI 智能排程 */
export async function aiSmartSchedule(): Promise<SmartScheduleResult> {
  return request('/api/ai/smart-schedule', {
    method: 'POST',
    body: JSON.stringify({}),
  }, 30000) as Promise<SmartScheduleResult>
}

// ── 习惯追踪 ──
export interface Habit {
  id: number
  name: string
  target_count: number
  period: string
  color: string
  sort_order: number
  auto_category?: string | null
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

export async function updateHabit(id: number, data: Partial<Habit>): Promise<{ status: string }> {
  return request(`/api/habits/${id}`, { method: 'PUT', body: JSON.stringify(data) }) as Promise<{ status: string }>
}

export async function autoCheckHabits(date?: string): Promise<{ status: string; auto_logged: Array<{ habit_id: number; habit_name: string; auto_category: string; minutes: number; target_count: number }>; count: number }> {
  return request('/api/habits/auto-check', { method: 'POST', body: JSON.stringify({ date }) }) as Promise<{ status: string; auto_logged: Array<{ habit_id: number; habit_name: string; auto_category: string; minutes: number; target_count: number }>; count: number }>
}

// P14-2：智能习惯推荐
export interface HabitSuggestion {
  name: string
  target_count: number
  period: string
  auto_category: string | null
  reason: string
  source: 'behavior' | 'classic'
  score: number
}

export async function getHabitRecommendations(limit?: number): Promise<{ status: string; suggestions: HabitSuggestion[] }> {
  const qs = limit ? `?limit=${limit}` : ''
  return request(`/api/habits/recommend${qs}`) as Promise<{ status: string; suggestions: HabitSuggestion[] }>
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

export async function addTodoProgress(todoId: number, minutes: number): Promise<{ status: string }> {
  return request(`/api/todos/${todoId}/add-progress`, { method: 'POST', body: JSON.stringify({ minutes }) }) as Promise<{ status: string }>
}

// 工具函数：将 Date 格式化为本地 YYYY-MM-DD 字符串（不受时区影响）
export function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// 工具函数：获取今天的本地日期字符串 YYYY-MM-DD
export function getTodayStr(): string {
  return formatLocalDate(new Date())
}

// 工具函数：将 Date 格式化为本地 YYYY-MM-DD HH:MM:SS 时间戳字符串
export function formatLocalTimestamp(d: Date): string {
  const date = formatLocalDate(d)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  const s = String(d.getSeconds()).padStart(2, '0')
  return `${date} ${h}:${m}:${s}`
}

// 工具函数：将 Date 格式化为本地 YYYY-MM 字符串
function _formatLocalMonth(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  return `${y}-${m}`
}

// 工具函数：ISO 8601 周一日期
export function getWeekStart(d: Date = new Date()): string {
  const date = new Date(d)
  const day = date.getDay() // 0=周日, 1=周一
  const diff = day === 0 ? -6 : 1 - day // 周日回到上周一
  date.setDate(date.getDate() + diff)
  return formatLocalDate(date)
}

// 工具函数：从日期字符串获取周一开始的 7 天
export function getWeekDates(weekStart: string): string[] {
  const start = new Date(weekStart + 'T00:00:00')
  const dates: string[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    dates.push(formatLocalDate(d))
  }
  return dates
}

// 工具函数：获取月份 key
export function getMonthKey(d: Date = new Date()): string {
  return _formatLocalMonth(d)
}

// ── P7-1: AI 行为教练 ──
export interface CoachAlert {
  type: 'distraction_light' | 'distraction_heavy' | 'overwork' | 'flow_protect'
  message: string
  minutes: number
  category: string
}

export interface CoachStatus {
  distraction_minutes: number
  work_minutes: number
  current_category: string
  flow_minutes: number
  in_flow: boolean
  alerts: CoachAlert[]
  urge_surfing: { quote: string } | null
  smart_break: { message: string; prev_category: string; prev_minutes: number } | null
}

export async function getCoachStatus(): Promise<CoachStatus> {
  return request('/api/coach/status', undefined, 8000) as Promise<CoachStatus>
}

export interface CoachDailySummary {
  distraction_count: number
  longest_focus_min: number
  flow_sessions: number
  total_distraction_min: number
}

export async function getCoachDailySummary(): Promise<CoachDailySummary> {
  return request('/api/coach/daily-summary') as Promise<CoachDailySummary>
}

// ── P16-1: 生物钟检测 ──
export interface Chronotype {
  type: 'early_bird' | 'night_owl' | 'intermediate'
  label: string
  icon: string
  first_active_hour: number
  last_active_hour: number
  golden_hours: string
  peak_period: string
  peak_period_short: string
  greeting: string
  valid_days: number
  analysis_days: number
}

export async function getChronotype(): Promise<Chronotype> {
  return request('/api/coach/chronotype') as Promise<Chronotype>
}

// ── P16-3: 主动智能建议 ──
export interface SmartSuggestion {
  type: string
  priority: 'high' | 'medium' | 'low'
  title: string
  detail: string
  action: string
  icon: string
}

export async function getSmartSuggestions(): Promise<{ status: string; suggestions: SmartSuggestion[]; count: number }> {
  return request('/api/coach/suggestions', undefined, 15000) as Promise<{ status: string; suggestions: SmartSuggestion[]; count: number }>
}

// ── P7-4: 桑基图（时间流动可视化） ──
export interface SankeyLink {
  source: string
  target: string
  value: number
}

export async function getSankeyData(date?: string): Promise<{ links: SankeyLink[]; nodes: string[] }> {
  const params = date ? `?date=${date}` : ''
  return request(`/api/stats/sankey${params}`) as Promise<{ links: SankeyLink[]; nodes: string[] }>
}

// ── P11-2：用户个性化偏好 ──
export interface UserPreferences {
  nickname: string
  greeting_enabled: boolean
  report_style: 'concise' | 'balanced' | 'detailed'
  encouragement_level: 'subtle' | 'warm' | 'energetic'
  disclosure_level: 'beginner' | 'intermediate' | 'expert'
  tooltip_enabled: boolean
}
export async function getPreferences(): Promise<UserPreferences> {
  const res = await request('/api/preferences') as { preferences: UserPreferences }
  return res.preferences
}
export async function updatePreferences(data: Partial<UserPreferences>): Promise<{ status: string; updated: string[] }> {
  return request('/api/preferences', {
    method: 'POST',
    body: JSON.stringify(data),
  }) as Promise<{ status: string; updated: string[] }>
}
export async function resetPreferences(): Promise<{ status: string; preferences: UserPreferences }> {
  return request('/api/preferences/reset', { method: 'POST' }) as Promise<{ status: string; preferences: UserPreferences }>
}

// ── P11-3：审计日志 ──
export interface AuditLog {
  id: number
  ts: string
  category: string
  action: string
  status: string
  detail: string | null
  duration_ms: number | null
  metadata: string | null
}
export interface AuditStats {
  total: number
  by_status: Record<string, number>
  by_category: Record<string, number>
  recent_24h_failures: number
}
export async function getAuditLogs(params?: { category?: string; status?: string; limit?: number; offset?: number }): Promise<{ logs: AuditLog[]; count: number }> {
  const qs = new URLSearchParams()
  if (params?.category) qs.set('category', params.category)
  if (params?.status) qs.set('status', params.status)
  if (params?.limit) qs.set('limit', String(params.limit))
  if (params?.offset) qs.set('offset', String(params.offset))
  const q = qs.toString()
  return request(`/api/audit/logs${q ? '?' + q : ''}`) as Promise<{ logs: AuditLog[]; count: number }>
}
export async function getAuditStats(): Promise<{ stats: AuditStats }> {
  return request('/api/audit/stats') as Promise<{ stats: AuditStats }>
}
export async function cleanupAuditLogs(): Promise<{ status: string; deleted: number }> {
  return request('/api/audit/cleanup', { method: 'POST' }) as Promise<{ status: string; deleted: number }>
}

// ── P12-1：周报/月报深度洞察 ──
export interface DeepInsights {
  weekly_stats: Array<{
    week_start: string
    week_end: string
    total_min: number
    categories: Record<string, number>
    percentages: Record<string, number>
  }>
  trends: Array<{
    category: string
    current_pct: number
    previous_pct: number
    delta: number
    direction: string
    significant: boolean
  }>
  patterns: {
    peak_hours: string[]
    low_hours: string[]
    best_category: string | null
    avg_hour_min?: number
  }
  benchmark: Array<{
    metric: string
    user_value: number
    benchmark: number
    unit: string
    status: 'above' | 'below'
    diff: number
  }>
  benchmarks_definition: Record<string, number>
}
export async function getDeepInsights(): Promise<{ status: string; insights: DeepInsights }> {
  return request('/api/report/deep-insights') as Promise<{ status: string; insights: DeepInsights }>
}

// ── P12-2：Obsidian 导出 ──
export async function exportReportAsObsidian(
  date: string,
  mode: 'standard' | 'dataview' = 'dataview'
): Promise<{ status: string; date: string; mode: string; content: string; filename: string }> {
  return request(`/api/report/export/obsidian?date=${encodeURIComponent(date)}&mode=${mode}`) as Promise<{
    status: string; date: string; mode: string; content: string; filename: string
  }>
}

// ── P12-4：宠物情绪化 ──
export type PetMood = 'idle' | 'focused' | 'flowing' | 'distracted' | 'overworked' | 'sleepy' | 'milestone'
export interface PetMoodData {
  status: string
  mood: PetMood
  focus_min: number
  focus_sessions: number
  distraction_count: number
  streak_days: number
  message: string
}
export async function getPetMood(): Promise<PetMoodData> {
  return request('/api/pet/mood') as Promise<PetMoodData>
}

// ── P13-2：习惯统计 ──
export interface HabitStats {
  habit_id: number
  streak_days: number
  completion_rate: number
  total_logs: number
  period: string
  target_count: number
  recent_trend: Array<{ date: string; logged: boolean; count: number }>
}
export async function getHabitStats(habitId: number, days = 30): Promise<{ status: string; stats: HabitStats }> {
  return request(`/api/habits/${habitId}/stats?days=${days}`) as Promise<{ status: string; stats: HabitStats }>
}

// ─── P18-1: 日历集成 ──────────────────────────────

export interface CalendarSubscription {
  id: string
  name: string
  url: string
  color: string
  enabled: boolean
  last_sync: string | null
  last_error: string | null
}

export interface CalendarEvent {
  summary: string
  start: string
  end: string
  start_timestamp: number
  end_timestamp: number
  location?: string
  description?: string
  calendar_id: string
  calendar_name: string
  calendar_color: string
}

export async function listCalendarSubscriptions(): Promise<{ subscriptions: CalendarSubscription[] }> {
  return request('/api/calendar/subscriptions') as Promise<{ subscriptions: CalendarSubscription[] }>
}

export async function addCalendarSubscription(data: { name: string; url: string; color?: string }): Promise<{ subscription: CalendarSubscription }> {
  return request('/api/calendar/subscriptions', {
    method: 'POST',
    body: JSON.stringify(data),
  }) as Promise<{ subscription: CalendarSubscription }>
}

export async function updateCalendarSubscription(subId: string, data: Partial<CalendarSubscription>): Promise<{ subscription: CalendarSubscription }> {
  return request(`/api/calendar/subscriptions/${subId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }) as Promise<{ subscription: CalendarSubscription }>
}

export async function removeCalendarSubscription(subId: string): Promise<{ ok: boolean }> {
  return request(`/api/calendar/subscriptions/${subId}`, { method: 'DELETE' }) as Promise<{ ok: boolean }>
}

export async function refreshCalendarAll(): Promise<{ refreshed: number; failed: number; total: number }> {
  return request('/api/calendar/refresh', { method: 'POST' }) as Promise<{ refreshed: number; failed: number; total: number }>
}

export async function getCalendarTodayEvents(): Promise<{ events: CalendarEvent[] }> {
  return request('/api/calendar/today') as Promise<{ events: CalendarEvent[] }>
}

export async function getCalendarUpcomingEvents(hours = 24): Promise<{ events: CalendarEvent[] }> {
  return request(`/api/calendar/upcoming?hours=${hours}`) as Promise<{ events: CalendarEvent[] }>
}

export async function getCalendarCurrentMeeting(): Promise<{ meeting: CalendarEvent | null; in_meeting: boolean }> {
  return request('/api/calendar/current-meeting') as Promise<{ meeting: CalendarEvent | null; in_meeting: boolean }>
}

// ─── P18-2: Git 集成 ───────────────────────────────

export interface GitRepository {
  path: string
  name: string
  enabled: boolean
  added_at?: string
  exists: boolean
  has_git: boolean
  status: 'ok' | 'missing' | 'not_a_repo'
}

export interface GitCodeReport {
  date: string
  repositories: Array<{
    name: string
    path: string
    commit_count: number
    files_changed: number
    insertions: number
    deletions: number
    subjects: string[]
    by_extension: Record<string, { files: number; insertions: number; deletions: number }>
    error?: string
  }>
  total_commits: number
  total_files_changed: number
  total_insertions: number
  total_deletions: number
  summary: string
}

export async function listGitRepositories(): Promise<{ repositories: GitRepository[] }> {
  return request('/api/git/repositories') as Promise<{ repositories: GitRepository[] }>
}

export async function addGitRepository(data: { path: string; name?: string; enabled?: boolean }): Promise<{ repository: GitRepository }> {
  return request('/api/git/repositories', {
    method: 'POST',
    body: JSON.stringify(data),
  }) as Promise<{ repository: GitRepository }>
}

export async function removeGitRepository(path: string): Promise<{ ok: boolean }> {
  return request('/api/git/repositories', {
    method: 'DELETE',
    body: JSON.stringify({ path }),
  }) as Promise<{ ok: boolean }>
}

export async function getGitCodeReport(date?: string): Promise<GitCodeReport> {
  const q = date ? `?date=${encodeURIComponent(date)}` : ''
  return request(`/api/git/code-report${q}`) as Promise<GitCodeReport>
}

export async function getGitWeeklyReport(endDate?: string): Promise<{
  total_commits: number
  active_days: number
  by_date: Record<string, number>
  by_type: Record<string, number>
  authors: Record<string, number>
  start_date: string
  end_date: string
  repositories_count: number
}> {
  const q = endDate ? `?end_date=${encodeURIComponent(endDate)}` : ''
  return request(`/api/git/weekly-report${q}`) as Promise<any>
}

// ─── P18-3: 匿名群组对比 ───────────────────────────

export interface BenchmarkMetric {
  key: string
  label: string
  unit: string
  user_value: number
  benchmark_p50: number
  benchmark_p75: number
  percentile: number
  higher_better: boolean
  verdict: string
}

export interface BenchmarkResult {
  occupation: string
  occupation_label: string
  metrics: BenchmarkMetric[]
  overall_percentile: number
  overall_summary: string
  days: number
  user_metrics: {
    daily_focus_minutes: number
    deep_work_ratio: number
    meeting_ratio: number
    distraction_ratio: number
    streak_days: number
  }
}

export interface BenchmarkProfile {
  occupation: string
  anonymous_id: string
  group_code: string
  created_at: string
  updated_at?: string
}

export interface GroupLeaderboardEntry {
  anonymous_id: string
  name: string
  daily_focus_minutes: number
  deep_work_ratio: number
  streak_days: number
  score: number
  updated_at: string
}

export async function listBenchmarkOccupations(): Promise<{ occupations: Array<{ key: string; label: string }> }> {
  return request('/api/benchmark/occupations') as Promise<{ occupations: Array<{ key: string; label: string }> }>
}

export async function getBenchmarkProfile(): Promise<BenchmarkProfile> {
  return request('/api/benchmark/profile') as Promise<BenchmarkProfile>
}

export async function updateBenchmarkProfile(data: { occupation?: string; group_code?: string }): Promise<BenchmarkProfile> {
  return request('/api/benchmark/profile', {
    method: 'PUT',
    body: JSON.stringify(data),
  }) as Promise<BenchmarkProfile>
}

export async function compareBenchmark(days = 7): Promise<BenchmarkResult> {
  return request(`/api/benchmark/compare?days=${days}`) as Promise<BenchmarkResult>
}

export async function listBenchmarkGroups(): Promise<{ groups: any[] }> {
  return request('/api/benchmark/groups') as Promise<{ groups: any[] }>
}

export async function createBenchmarkGroup(name: string): Promise<{ group: any }> {
  return request('/api/benchmark/groups', {
    method: 'POST',
    body: JSON.stringify({ name }),
  }) as Promise<{ group: any }>
}

export async function joinBenchmarkGroup(code: string, name?: string): Promise<{ group: any }> {
  return request(`/api/benchmark/groups/${code}/join`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  }) as Promise<{ group: any }>
}

export async function leaveBenchmarkGroup(code: string): Promise<{ ok: boolean }> {
  return request(`/api/benchmark/groups/${code}/leave`, { method: 'POST' }) as Promise<{ ok: boolean }>
}

export async function getBenchmarkGroupLeaderboard(code: string): Promise<{
  code: string
  name: string
  members_count: number
  leaderboard: GroupLeaderboardEntry[]
}> {
  return request(`/api/benchmark/groups/${code}/leaderboard`) as Promise<any>
}

export async function exportBenchmarkMetrics(): Promise<any> {
  return request('/api/benchmark/export') as Promise<any>
}

// ─── P18-4: 本地小模型降级 ─────────────────────────

export interface LocalModelConfig {
  enabled: boolean
  base_url: string
  vision_model: string
  text_model: string
  fallback_to_rules: boolean
  auto_fallback: boolean
  timeout_sec: number
}

export interface LocalModelStatus {
  config: LocalModelConfig
  health: {
    available: boolean
    base_url: string
    models?: string[]
    model_count?: number
    error?: string
    cached?: boolean
  }
}

export async function getLocalModelStatus(): Promise<LocalModelStatus> {
  return request('/api/local-model/status') as Promise<LocalModelStatus>
}

export async function getLocalModelConfig(): Promise<LocalModelConfig> {
  return request('/api/local-model/config') as Promise<LocalModelConfig>
}

export async function updateLocalModelConfig(data: Partial<LocalModelConfig>): Promise<LocalModelConfig> {
  return request('/api/local-model/config', {
    method: 'PUT',
    body: JSON.stringify(data),
  }) as Promise<LocalModelConfig>
}

export async function listLocalModels(): Promise<{ models: Array<{ name: string; size_mb: number; modified_at: string }> }> {
  return request('/api/local-model/models') as Promise<{ models: Array<{ name: string; size_mb: number; modified_at: string }> }>
}

export async function testLocalModel(type: 'text' | 'vision' = 'text'): Promise<{ ok: boolean; type: string; result: any }> {
  return request('/api/local-model/test', {
    method: 'POST',
    body: JSON.stringify({ type }),
  }) as Promise<{ ok: boolean; type: string; result: any }>
}

