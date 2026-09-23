// ── P0-1: AI 从当日活动时间线提取待办 ──
import { request } from './core'

export interface ExtractedTodo {
  title: string
  priority: 'high' | 'medium' | 'low'
  due_hint: string
  source_activity_id: number | null
  confidence: number
}

export interface ExtractTodosResult {
  todos: ExtractedTodo[]
  date: string
  activity_count: number
  message?: string
}

/** 调用 AI 从当日活动时间线中提取待办事项 */
export async function extractTodos(date?: string): Promise<ExtractTodosResult> {
  const body = date ? JSON.stringify({ date }) : '{}'
  // AI 推理可能耗时较长，给 30s 超时
  return request('/api/ai/extract-todos', { method: 'POST', body }, 30000) as Promise<ExtractTodosResult>
}

/** 确认将选中的 AI 提取待办写入 todos 表 */
export async function confirmExtractedTodos(todos: ExtractedTodo[]): Promise<{ status: string; inserted: number; ids: number[] }> {
  return request('/api/ai/extract-todos/confirm', { method: 'POST', body: JSON.stringify({ todos }) }) as Promise<{ status: string; inserted: number; ids: number[] }>
}
