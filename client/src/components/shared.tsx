import { useRef, useEffect, useState, useCallback } from 'react'
import { CATEGORIES, onBackendStateChange } from '../api/client'
import { AlertCircle, RefreshCw, Loader2 } from 'lucide-react'

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

// ── BackendStatusBar 后端连接状态条（全局顶部提示）──
// 参考 VS Code 的 "Extension host terminated" 通知条
// 当后端断连时在页面顶部显示橙色提示条，恢复后自动消失

import { useEffect as useEffectState, useState as useStateState } from 'react'
import { getBackendState } from '../api/client'

export function BackendStatusBar() {
  const [state, setState] = useStateState(getBackendState())
  const [retryIn, setRetryIn] = useStateState(0)

  useEffectState(() => {
    const unsub = onBackendStateChange(setState)
    return unsub
  }, [])

  // 断线时显示倒计时（下次自动重连）
  useEffectState(() => {
    if (state !== 'disconnected') {
      setRetryIn(0)
      return
    }
    setRetryIn(5)
    const timer = setInterval(() => {
      setRetryIn(prev => prev > 0 ? prev - 1 : 5)
    }, 1000)
    return () => clearInterval(timer)
  }, [state])

  if (state === 'connected') return null
  if (state === 'connecting') return null  // 连接中不显示，避免闪烁

  return (
    <div className="fixed top-0 left-0 right-0 z-[9999] bg-cd-orange/90 text-white text-xs py-1.5 px-4 flex items-center justify-center gap-2 animate-fade-in">
      <AlertCircle size={14} className="shrink-0" />
      <span>后端服务断开，正在自动重连...{retryIn > 0 && `（${retryIn}s 后重试）`}</span>
    </div>
  )
}

// ── 追踪新增条目 ID（用于动态模糊动画）──

export function useNewIds<T>(items: T[], getId: (item: T) => string | number): Set<string | number> {
  const prevIdsRef = useRef<Set<string | number>>(new Set())
  const [newIds, setNewIds] = useState<Set<string | number>>(new Set())

  useEffect(() => {
    const currentIds = new Set(items.map(getId))
    const prevIds = prevIdsRef.current
    if (prevIds.size === 0) {
      // 首次加载，不标记任何为新增
      prevIdsRef.current = currentIds
      setNewIds(new Set())
      return
    }
    const added = new Set<string | number>()
    currentIds.forEach((id) => {
      if (!prevIds.has(id)) added.add(id)
    })
    prevIdsRef.current = currentIds
    setNewIds(added)
    // 动画结束后清空新增标记
    if (added.size > 0) {
      const timer = setTimeout(() => setNewIds(new Set()), 800)
      return () => clearTimeout(timer)
    }
  }, [items, getId])

  return newIds
}


// ── 刷新指示器（右上角小圆点）──

export function RefreshIndicator({ refreshing }: { refreshing: boolean }) {
  if (!refreshing) return null
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-cd-text-tertiary px-2 py-0.5 rounded-full bg-cd-bg-secondary border border-cd-border animate-fade-in">
      <Loader2 size={10} className="animate-spin-slow" />
      刷新中
    </span>
  )
}


// ── useAsyncData 异步数据加载 Hook（企业级稳定性增强版） ──
//
// 参考 VS Code / ActivityWatch / Grafana 的数据加载策略：
//   1. 首次加载显示 loading；有数据后的刷新走后台 silent refresh，不闪烁
//   2. 请求失败时保留上次数据（stale-while-error），仅显示顶部连接状态条
//   3. 断线后自动指数退避重试（1s → 2s → 5s → 10s），恢复后自动回到正常间隔
//   4. 组件卸载后不再 setState，避免内存泄漏
//

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  refreshing: boolean
}

export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  refreshInterval?: number,
): AsyncState<T> & { refresh: () => void } {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: true,
    error: null,
    refreshing: false,
  })
  const mountedRef = useRef(true)
  const hasDataRef = useRef(false)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async (isBackground = false) => {
    // 如果已经有数据，后台刷新不进入 loading 状态，避免页面闪烁
    setState(prev => ({
      ...prev,
      loading: isBackground && hasDataRef.current ? false : true,
      // 后台刷新出错时不清除已有错误信息，但也不覆盖已有数据
      error: isBackground && hasDataRef.current ? prev.error : null,
      refreshing: true,
    }))
    try {
      const data = await fetcher()
      if (mountedRef.current) {
        hasDataRef.current = true
        retryCountRef.current = 0  // 成功后重置重试计数
        setState({ data, loading: false, error: null, refreshing: false })
      }
    } catch (err: unknown) {
      if (mountedRef.current) {
        const message = err instanceof Error ? err.message : '加载失败'
        // 关键：有数据时保留旧数据（stale-while-error），只标记错误状态
        setState(prev => ({
          ...prev,
          loading: false,
          error: message,
          refreshing: false,
        }))
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    mountedRef.current = true
    hasDataRef.current = false
    retryCountRef.current = 0
    load(false)

    let intervalId: ReturnType<typeof setInterval> | undefined
    let cancelled = false

    if (refreshInterval) {
      // 正常定时刷新
      intervalId = setInterval(() => {
        if (cancelled) return
        load(true)
      }, refreshInterval)

      // 断线自动重连：指数退避（1s → 2s → 5s → 10s → 10s...）
      const scheduleRetry = () => {
        if (cancelled || !mountedRef.current) return
        const attempts = retryCountRef.current
        const delay = attempts === 0 ? 1000
          : attempts === 1 ? 2000
          : attempts === 2 ? 5000
          : 10000  // 封顶 10 秒
        retryTimerRef.current = setTimeout(() => {
          if (cancelled || !mountedRef.current) return
          retryCountRef.current++
          load(true).then(() => {
            // 成功后重置计数，恢复正常定时刷新
            retryCountRef.current = 0
          }).catch(() => {
            // 仍然失败，继续调度下一次重试
            scheduleRetry()
          })
        }, delay)
      }

      // 监听后端状态变化，断线时立即触发重连
      const unsubState = onBackendStateChange((s) => {
        if (s === 'disconnected' && mountedRef.current) {
          // 后端断线，1 秒后开始重试
          if (!retryTimerRef.current) {
            scheduleRetry()
          }
        }
      })
      return () => {
        cancelled = true
        mountedRef.current = false
        if (intervalId) clearInterval(intervalId)
        if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
        unsubState()
      }
    }

    return () => {
      mountedRef.current = false
      if (intervalId) clearInterval(intervalId)
    }
  }, [load, refreshInterval])

  return { ...state, refresh: () => load(false) }
}
