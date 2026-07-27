// ── 统计数据：热力图、趋势、节奏、日历视图、桑基图 ──
import { request } from './core'

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
