// ── 待办清单、周计划、月计划 ──
import { request } from './core'

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
  plan_start_min?: number | null
  sort_order?: number
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

export async function assignTodo(data: { todo_id: number; assigned_date?: string; week_start?: string; task_level?: TaskLevel; plan_start_min?: number | null }): Promise<{ status: string }> {
  return request('/api/week-plan/assign', { method: 'POST', body: JSON.stringify(data) }) as Promise<{ status: string }>
}

export async function unassignTodo(todo_id: number): Promise<{ status: string }> {
  return request('/api/week-plan/unassign', { method: 'POST', body: JSON.stringify({ todo_id }) }) as Promise<{ status: string }>
}

export async function updateTaskTime(todo_id: number, plan_start_min: number | null): Promise<{ status: string }> {
  return request('/api/week-plan/task-time', { method: 'PUT', body: JSON.stringify({ todo_id, plan_start_min }) }) as Promise<{ status: string }>
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
