/* P53+P58: TypeScript 类型收窄工具 + 通用辅助函数
 * 消除重复的类型检查和工具函数
 */

// ── P53: 类型守卫 ──
export function isNonEmpty<T>(arr: T[] | null | undefined): arr is T[] {
  return Array.isArray(arr) && arr.length > 0
}

export function isString(v: unknown): v is string {
  return typeof v === 'string'
}

export function isNumber(v: unknown): v is number {
  return typeof v === 'number' && !isNaN(v)
}

export function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

export function hasKey<T extends object>(obj: T, key: PropertyKey): key is keyof T {
  return key in obj
}

export function safeString(v: unknown, fallback = ''): string {
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  return fallback
}

export function safeNumber(v: unknown, fallback = 0): number {
  if (typeof v === 'number' && !isNaN(v)) return v
  if (typeof v === 'string') {
    const n = parseFloat(v)
    return isNaN(n) ? fallback : n
  }
  return fallback
}

export function safeArray<T>(v: T[] | null | undefined): T[] {
  return Array.isArray(v) ? v : []
}

// ── P58: 通用辅助函数 ──
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}秒`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}分钟`
  const hours = Math.floor(minutes / 60)
  const remMinutes = minutes % 60
  if (remMinutes === 0) return `${hours}小时`
  return `${hours}小时${remMinutes}分钟`
}

export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`
}

export function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen - 3) + '...'
}

export function debounce<T extends (...args: never[]) => void>(fn: T, delayMs: number): T {
  let timer: ReturnType<typeof setTimeout> | null = null
  return ((...args: Parameters<T>) => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => fn(...args), delayMs)
  }) as T
}

export function throttle<T extends (...args: never[]) => void>(fn: T, delayMs: number): T {
  let lastRun = 0
  return ((...args: Parameters<T>) => {
    const now = Date.now()
    if (now - lastRun >= delayMs) {
      lastRun = now
      fn(...args)
    }
  }) as T
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function retry<T>(
  fn: () => Promise<T>,
  maxAttempts = 3,
  delayMs = 1000
): Promise<T> {
  return fn().catch(async (err) => {
    if (maxAttempts <= 1) throw err
    await sleep(delayMs)
    return retry(fn, maxAttempts - 1, delayMs * 2)
  })
}
