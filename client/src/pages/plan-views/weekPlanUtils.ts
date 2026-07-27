// ── 常量 ──
export const PRIORITY_COLORS = ['#ef4444', '#f59e0b', '#F0C040', '#10b981', '#6b7280']
export const MODE_LABELS: Record<string, string> = { timer: '计时', goal: '目标', habit: '习惯' }
export const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
export const DAILY_LIMIT = 180 // 负载警示阈值（分钟）
// GitHub 风格热力色阶（5 级）
export const HEAT_COLORS = ['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353']

export type ViewMode = 'year' | 'month' | 'week' | 'day'

export const VIEW_TABS: { key: ViewMode; emoji: string; label: string }[] = [
  { key: 'year', emoji: '📅', label: '年计划' },
  { key: 'month', emoji: '📆', label: '月计划' },
  { key: 'week', emoji: '📋', label: '周计划' },
  { key: 'day', emoji: '✅', label: '日计划' },
]

// ── 热力色函数 ──
export function monthHeatColor(rate: number): string {
  if (rate <= 0) return 'var(--cd-bg-tertiary)'
  if (rate <= 0.3) return '#0e4429'
  if (rate <= 0.6) return '#006d32'
  if (rate <= 0.9) return '#26a641'
  return '#39d353'
}

export function heatColor(min: number): string {
  if (min <= 0) return HEAT_COLORS[0]
  if (min < 60) return HEAT_COLORS[1]
  if (min < 120) return HEAT_COLORS[2]
  if (min < 200) return HEAT_COLORS[3]
  return HEAT_COLORS[4]
}

// ── 本地日期工具（不受时区影响，每次调用动态计算）──
export function getTodayStr(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function formatLocalDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function formatLocalMonth(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function fmtDate(d: string) {
  const dt = new Date(d + 'T00:00:00')
  return `${dt.getMonth() + 1}/${dt.getDate()}`
}

export function isWeekend(d: string) {
  const day = new Date(d + 'T00:00:00').getDay()
  return day === 0 || day === 6
}

export function dayMin(todos: { target_min: number }[]) {
  return todos.reduce((s, t) => s + (t.target_min || 0), 0)
}

// ISO 周序号
export function getISOWeek(dateStr: string): number {
  const d = new Date(dateStr + 'T00:00:00')
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = (t.getUTCDay() + 6) % 7
  t.setUTCDate(t.getUTCDate() - dayNum + 3)
  const firstThursday = new Date(Date.UTC(t.getUTCFullYear(), 0, 4))
  return 1 + Math.round(((t.getTime() - firstThursday.getTime()) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7)
}

// 生成某年的 53 个周一日期（覆盖整年）
export function getYearWeekStarts(year: number, getWeekStartFn: (d: Date) => string): string[] {
  const weeks: string[] = []
  let cur = getWeekStartFn(new Date(year, 0, 1))
  for (let i = 0; i < 53; i++) {
    weeks.push(cur)
    const d = new Date(cur + 'T00:00:00')
    d.setDate(d.getDate() + 7)
    cur = formatLocalDate(d)
  }
  return weeks
}

// HH:MM 格式
export function fmtHM(min: number): string {
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}
