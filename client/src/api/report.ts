// ── 报告生成、质量评分、搜索、Obsidian 导出 ──
import { request } from './core'
import type { ReportContent } from './types-activity'

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
