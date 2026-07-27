// ── 集成功能：Webhook、成就、目标、习惯、日历、Git、基准、本地模型、记忆等 ──
import { request, getApiToken, getBaseUrl, _triggerDownload } from './core'
import { formatLocalDate } from './utils'

// ── Agent / Webhook 类型 ──────────────────────────

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
  const res = await fetch(`${getBaseUrl()}/api/backup`, {
    headers: token ? { 'X-API-Token': token } : {},
  })
  if (!res.ok) throw new Error(`备份失败: HTTP ${res.status}`)
  const blob = await res.blob()
  const date = formatLocalDate(new Date())
  _triggerDownload(blob, `xiaohei_backup_${date}.zip`)
}

// ── 数据校准 / 健康度 ──────────────────────────────

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
  return request('/api/study-room/broadcast', { method: 'POST' }, 20000) as Promise<{ status: string; broadcasted: number; subnet: string }>
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
export interface ImportResultV2 {
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
export async function executeImport(source: string, format: 'json' | 'csv', data: string, target_table?: string, dry_run?: boolean): Promise<ImportResultV2> {
  return request('/api/data-import/execute', { method: 'POST', body: JSON.stringify({ source, format, data, target_table, dry_run }) }) as Promise<ImportResultV2>
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

// ── 「今日完成」自动卡片 ──
export interface DailyCardData {
  date: string
  todos_completed: { id: number; title: string; category: string; completed_at: string; priority: number }[]
  todos_count: number
  habits_logged: { habit_id: number; name: string; count: number; color: string; category: string }[]
  habits_count: number
  pomodoro_sessions: { id: number; task: string; category: string; duration_min: number; status: string; start_time: string; end_time: string }[]
  pomodoro_count: number
  pomodoro_total_min: number
  pomodoro_quality: any
  activity_categories: Record<string, number>
  activity_total_min: number
  activity_first_ts: string | null
  activity_last_ts: string | null
  achievements_unlocked: { code: string; name: string; description: string; icon: string; unlocked_at: string }[]
  achievements_count: number
  summary: {
    total_tasks: number
    total_focus_min: number
    total_work_min: number
    total_habits: number
    total_achievements: number
    productivity_score: number
    grade: string
  }
}

export async function getDailyCard(date?: string): Promise<DailyCardData> {
  const d = date || new Date().toISOString().slice(0, 10)
  return request(`/api/daily-card?date=${d}`) as Promise<DailyCardData>
}

export async function getDailyCardText(date?: string): Promise<{ date: string; text: string; summary: any }> {
  const d = date || new Date().toISOString().slice(0, 10)
  return request(`/api/daily-card/text?date=${d}`) as Promise<{ date: string; text: string; summary: any }>
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

// ─── 记忆系统（向量检索 / 事实抽取） ─────────────────────────

/** 记忆条目 */
export interface MemoryItem {
  id: string
  content: string
  source_type?: string
  source_id?: string
  title?: string
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

/** 记忆搜索结果条目 */
export interface MemorySearchResult {
  id: string
  content: string
  title?: string
  source?: string
  source_type?: string
  score?: number
  snippet?: string
  metadata?: Record<string, unknown>
  created_at?: string
}

/** 向量化状态 */
export interface MemoryStatus {
  total: number
  indexed: number
  pending: number
  progress_pct?: number
  last_index?: string | null
  indexing?: boolean
  [key: string]: unknown
}

/** 搜索记忆（语义检索） */
export async function searchMemory(query: string, limit: number = 10): Promise<{ results: MemorySearchResult[]; query?: string; count?: number }> {
  const data = await request('/api/memory/search', {
    method: 'POST',
    body: JSON.stringify({ query, limit }),
  }) as { results?: MemorySearchResult[]; query?: string; count?: number }
  // 兼容直接返回数组的后端实现
  if (Array.isArray(data as unknown)) {
    return { results: data as unknown as MemorySearchResult[] }
  }
  return { results: data?.results || [], query: data?.query, count: data?.count }
}

/** 获取向量化状态 */
export async function getMemoryStatus(): Promise<MemoryStatus> {
  return request('/api/memory/status') as Promise<MemoryStatus>
}

/** 获取记忆列表 */
export async function getMemoryList(limit: number = 50): Promise<{ memories: MemoryItem[]; total?: number }> {
  const data = await request(`/api/memory/list?limit=${limit}`) as { memories?: MemoryItem[]; total?: number }
  // 兼容直接返回数组的后端实现
  if (Array.isArray(data as unknown)) {
    return { memories: data as unknown as MemoryItem[] }
  }
  return { memories: data?.memories || [], total: data?.total }
}

/** 删除记忆条目 */
export async function deleteMemory(id: string): Promise<{ status: string }> {
  return request(`/api/memory/${encodeURIComponent(id)}`, { method: 'DELETE' }) as Promise<{ status: string }>
}

/** 手动触发向量化索引 */
export async function triggerIndexing(source?: string): Promise<{ status: string; indexed?: number; [k: string]: unknown }> {
  const body = source ? JSON.stringify({ source }) : '{}'
  return request('/api/memory/index', {
    method: 'POST',
    body,
  }) as Promise<{ status: string; indexed?: number; [k: string]: unknown }>
}

/** 手动触发事实抽取 */
export async function triggerExtraction(): Promise<{ status: string; extracted?: number; [k: string]: unknown }> {
  return request('/api/memory/extract', {
    method: 'POST',
    body: '{}',
  }) as Promise<{ status: string; extracted?: number; [k: string]: unknown }>
}

/** 上传 OPML 文件至幕布导入接口（multipart/form-data） */
export async function uploadOpmlFile(file: File): Promise<{ status: string; imported?: number; skipped?: number; [k: string]: unknown }> {
  const token = await getApiToken()
  const formData = new FormData()
  formData.append('file', file)
  const res = await fetch(`${getBaseUrl()}/api/mubu/import-opml`, {
    method: 'POST',
    headers: token ? { 'X-API-Token': token } : {},
    body: formData,
  })
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
    throw new Error(errData.error || 'OPML 导入失败')
  }
  return res.json()
}
