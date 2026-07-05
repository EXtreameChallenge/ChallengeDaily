import { useRef, useEffect, useState, useCallback } from 'react'
import { CATEGORIES } from '../api/client'
import { AlertCircle, RefreshCw } from 'lucide-react'

// ── ToggleSwitch 开关组件 ──

interface ToggleSwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  'aria-label'?: string
}

export function ToggleSwitch({ checked, onChange, disabled, ...rest }: ToggleSwitchProps) {
  return (
    <button
      onClick={() => !disabled && onChange(!checked)}
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      className={`relative w-10 h-5 rounded-full transition-colors ${
        checked ? 'bg-cd-green' : 'bg-cd-border'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      {...rest}
    >
      <span
        className="absolute top-0.5 w-4 h-4 rounded-full bg-cd-card shadow-sm transition-all"
        style={{ left: checked ? '22px' : '2px' }}
      />
    </button>
  )
}

// ── formatDuration 时长格式化 ──

export function formatDuration(minutes: number): string {
  if (minutes >= 60) {
    const h = Math.floor(minutes / 60)
    const m = Math.round(minutes % 60)
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }
  return `${Math.round(minutes)}min`
}

// ── CategoryFilter 分类筛选 ──

interface CategoryFilterProps {
  selected: string
  onChange: (category: string) => void
  /** 自定义分类列表，默认使用 CATEGORIES */
  categories?: string[]
}

export function CategoryFilter({ selected, onChange, categories }: CategoryFilterProps) {
  const allCategories = ['全部', ...(categories || CATEGORIES)]
  return (
    <div className="flex gap-2 flex-wrap">
      {allCategories.map((cat) => (
        <button
          key={cat}
          onClick={() => onChange(cat)}
          className={`px-3 py-1 rounded-full text-xs transition-colors ${
            selected === cat
              ? 'bg-cd-green text-white'
              : 'bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover'
          }`}
        >
          {cat}
        </button>
      ))}
    </div>
  )
}

// ── useTimeout 安全 setTimeout Hook ──

export function useTimeout(callback: () => void, delay: number | null) {
  const savedCallback = useRef(callback)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    if (delay === null) return
    timerRef.current = setTimeout(() => savedCallback.current(), delay)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [delay])
}

// ── ApiErrorDisplay 统一 API 错误展示 ──

interface ApiErrorDisplayProps {
  error: string
  onRetry?: () => void
}

export function ApiErrorDisplay({ error, onRetry }: ApiErrorDisplayProps) {
  return (
    <div className="card text-center py-10">
      <AlertCircle size={32} className="text-cd-red mx-auto mb-3" />
      <p className="text-sm text-cd-text-secondary mb-3">{error}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
        >
          <RefreshCw size={12} />
          重试
        </button>
      )}
    </div>
  )
}

// ── useAsyncData 异步数据加载 Hook ──

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  refreshInterval?: number,
): AsyncState<T> & { refresh: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null })
  const mountedRef = useRef(true)

  const load = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }))
    try {
      const data = await fetcher()
      if (mountedRef.current) {
        setState({ data, loading: false, error: null })
      }
    } catch (err: unknown) {
      if (mountedRef.current) {
        const message = err instanceof Error ? err.message : '加载失败'
        setState(prev => ({ ...prev, loading: false, error: message }))
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    mountedRef.current = true
    load()
    let intervalId: ReturnType<typeof setInterval> | undefined
    if (refreshInterval) {
      intervalId = setInterval(load, refreshInterval)
    }
    return () => {
      mountedRef.current = false
      if (intervalId) clearInterval(intervalId)
    }
  }, [load, refreshInterval])

  return { ...state, refresh: load }
}
