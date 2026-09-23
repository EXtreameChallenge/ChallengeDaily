// ── P0-4: 今日主页自然语言一句话摘要 ──
import { request } from './core'

export interface TodaySummaryStats {
  total_min: number
  total_activities: number
  top_categories: Array<{ name: string; count: number }>
  todos_total: number
  todos_completed: number
  todos_pending: number
  pomodoro_completed: number
  pomodoro_total_min: number
}

export interface TodaySummary {
  summary: string
  date: string
  stats: TodaySummaryStats
}

export async function getTodaySummary(): Promise<TodaySummary> {
  return request('/api/ai/today-summary', undefined, 15000) as Promise<TodaySummary>
}
