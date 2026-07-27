// ── 核心活动类型定义 ──

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

export interface ActivitiesResponse {
  activities: Activity[]
  pagination?: ActivityPage['pagination']
}

/** 番茄统计汇总（供日报番茄统计卡片渲染） */
export interface PomodoroSummary {
  date: string
  total: number
  completed: number
  total_min: number
  distractions: number
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
