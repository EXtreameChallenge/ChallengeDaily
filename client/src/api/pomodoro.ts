// ── 番茄钟：会话、统计、质量、分心检测、智能时长 ──
import { request } from './core'
import { POMODORO_SIZES, LONG_BREAK_INTERVAL } from './constants'

// 重新导出常量，方便从本模块导入
export { POMODORO_SIZES, LONG_BREAK_INTERVAL }

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

export async function startPomodoro(data: { task?: string; duration_min?: number; category?: string; todo_id?: number | null; pomodoro_index?: number; total_pomodoros?: number; lock_level?: number; custom_blacklist?: string[] }): Promise<{ status: string; id: number; start_time: string; todo_id: number | null; duration_min: number; pomodoro_index: number; total_pomodoros: number }> {
  return request('/api/pomodoro/start', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string; id: number; start_time: string; todo_id: number | null; duration_min: number; pomodoro_index: number; total_pomodoros: number }>
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
