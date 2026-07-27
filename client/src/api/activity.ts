// ── 活动采集、状态、设置、健康检查 ──
import { request, getApiToken, getBaseUrl, _triggerDownload } from './core'
import type { CollectorStatus, TodayStats, Activity, ActivityPage, ActivitiesResponse, AppUsage, AppCategoryRule, BackendSettings, PomodoroSummary, DailyCredibility, ReportContent } from './types-activity'

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

/** 测试 AI API 连接 */
export async function testAiConnection(apiKey: string, baseUrl: string, model: string): Promise<{ ok: boolean; message: string }> {
  const data = await request('/api/ai/test', {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, model }),
  })
  return data as { ok: boolean; message: string }
}

// ── 导出功能 ──

/** 导出活动记录 CSV（安全下载：使用 header 传 token，不暴露于 URL） */
export async function downloadExportActivities(start: string, end: string): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${getBaseUrl()}/api/export/activities?start=${start}&end=${end}`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`导出失败: HTTP ${res.status}`)
  const blob = await res.blob()
  _triggerDownload(blob, `activities_${start}_${end}.csv`)
}

/** 导出应用使用时长 CSV（安全下载） */
export async function downloadExportAppUsage(start: string, end: string): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${getBaseUrl()}/api/export/app-usage?start=${start}&end=${end}`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`导出失败: HTTP ${res.status}`)
  const blob = await res.blob()
  _triggerDownload(blob, `app_usage_${start}_${end}.csv`)
}

/** 导出历史报告（CSV / JSON） */
export async function downloadExportReports(start: string, end: string, format: 'csv' | 'json' = 'csv'): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${getBaseUrl()}/api/exports/reports?format=${format}&start=${start}&end=${end}`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`导出失败: HTTP ${res.status}`)
  const blob = await res.blob()
  _triggerDownload(blob, `reports_${start}_${end}.${format}`)
}

/** 导出活动明细聚合 CSV（多日期范围） */
export async function downloadExportActivitiesDetail(start: string, end: string): Promise<void> {
  const token = await getApiToken()
  const res = await fetch(`${getBaseUrl()}/api/exports/activities-detail?start=${start}&end=${end}`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`导出失败: HTTP ${res.status}`)
  const blob = await res.blob()
  _triggerDownload(blob, `activities_detail_${start}_${end}.csv`)
}

// ── 活动 CRUD ──

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
  const { formatLocalDate } = await import('./utils')
  const d = date || formatLocalDate(new Date())
  const data = await request(`/api/activities/search?q=${encodeURIComponent(q)}&date=${d}`) as { activities: Activity[] }
  return data.activities || []
}

// ── 备份/恢复/通知 ──

/** 获取备份信息 */
export async function getBackupInfo(): Promise<{ db_size_mb: number; activities_count: number; reports_count: number }> {
  return request('/api/backup/info') as Promise<{ db_size_mb: number; activities_count: number; reports_count: number }>
}

/** 从备份文件恢复数据 */
export async function restoreBackup(file: File): Promise<{ status: string; restored_files: string[] }> {
  const token = await getApiToken()
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${getBaseUrl()}/api/backup/restore`, {
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

// ── 应用分类规则 ──

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
  return `${getBaseUrl()}/api/icons/${encodeURIComponent(appName)}`
}

// ── 日报简要统计 ──

export async function getPomodoroSummary(date?: string): Promise<PomodoroSummary> {
  const params = date ? `?date=${date}` : ''
  return await request(`/api/report/pomodoro-summary${params}`) as PomodoroSummary
}

export async function getDailyCredibility(): Promise<DailyCredibility> {
  return await request('/api/credibility/daily-report') as DailyCredibility
}
