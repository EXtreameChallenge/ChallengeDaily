// ── AI 对话、教练、周复盘、智能排程 ──
import { request, getApiToken, getBaseUrl } from './core'

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
  const url = `${getBaseUrl()}/api/ai/chat/stream`
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
