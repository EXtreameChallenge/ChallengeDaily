// ── 工具函数：日期格式化、周计算 ──

/** 将 Date 格式化为本地 YYYY-MM-DD 字符串（不受时区影响） */
export function formatLocalDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 获取今天的本地日期字符串 YYYY-MM-DD */
export function getTodayStr(): string {
  return formatLocalDate(new Date())
}

/** 将 Date 格式化为本地 YYYY-MM-DD HH:MM:SS 时间戳字符串 */
export function formatLocalTimestamp(d: Date): string {
  const date = formatLocalDate(d)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  const s = String(d.getSeconds()).padStart(2, '0')
  return `${date} ${h}:${m}:${s}`
}

/** 将 Date 格式化为本地 YYYY-MM 字符串 */
function _formatLocalMonth(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  return `${y}-${m}`
}

/** ISO 8601 周一日期 */
export function getWeekStart(d: Date = new Date()): string {
  const date = new Date(d)
  const day = date.getDay() // 0=周日, 1=周一
  const diff = day === 0 ? -6 : 1 - day // 周日回到上周一
  date.setDate(date.getDate() + diff)
  return formatLocalDate(date)
}

/** 从日期字符串获取周一开始的 7 天 */
export function getWeekDates(weekStart: string): string[] {
  const start = new Date(weekStart + 'T00:00:00')
  const dates: string[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    dates.push(formatLocalDate(d))
  }
  return dates
}

/** 获取月份 key */
export function getMonthKey(d: Date = new Date()): string {
  return _formatLocalMonth(d)
}
