/* P48+P50: 触摸手势 + 骨架屏组件
 * - useSwipe: 滑动手势检测
 * - Skeleton: 骨架屏占位组件
 * - SkeletonCard: 卡片骨架屏
 */
import { useRef, useCallback, type ReactNode } from 'react'

// ── P48: 滑动手势 hook ──
export function useSwipe(
  onSwipeLeft?: () => void,
  onSwipeRight?: () => void,
  onSwipeUp?: () => void,
  onSwipeDown?: () => void,
  threshold = 50
) {
  const startPos = useRef<{ x: number; y: number } | null>(null)

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    const touch = e.touches[0]
    startPos.current = { x: touch.clientX, y: touch.clientY }
  }, [])

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!startPos.current) return
      const touch = e.changedTouches[0]
      const dx = touch.clientX - startPos.current.x
      const dy = touch.clientY - startPos.current.y
      startPos.current = null

      const absDx = Math.abs(dx)
      const absDy = Math.abs(dy)

      if (absDx < threshold && absDy < threshold) return

      if (absDx > absDy) {
        // 水平滑动
        if (dx > 0 && onSwipeRight) onSwipeRight()
        else if (dx < 0 && onSwipeLeft) onSwipeLeft()
      } else {
        // 垂直滑动
        if (dy > 0 && onSwipeDown) onSwipeDown()
        else if (dy < 0 && onSwipeUp) onSwipeUp()
      }
    },
    [onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown, threshold]
  )

  return { onTouchStart, onTouchEnd }
}

// ── P50: 骨架屏组件 ──
export function Skeleton({ className = '', style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={`skeleton ${className}`} style={style} />
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="skeleton-text" />
      ))}
    </div>
  )
}

export function SkeletonCard() {
  return (
    <div className="p-4 rounded-lg border border-white/5">
      <div className="flex items-center gap-3 mb-3">
        <Skeleton className="skeleton-avatar" />
        <div className="flex-1">
          <Skeleton className="skeleton-text" />
          <Skeleton className="skeleton-text" style={{ width: '40%' }} />
        </div>
      </div>
      <SkeletonText lines={2} />
    </div>
  )
}

export function SkeletonList({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </>
  )
}

// ── P50: 带加载状态的容器 ──
export function AsyncContainer({
  loading,
  error,
  children,
  skeleton,
  errorFallback,
}: {
  loading: boolean
  error?: Error | null
  children: ReactNode
  skeleton?: ReactNode
  errorFallback?: (error: Error) => ReactNode
}) {
  if (loading) {
    return <>{skeleton ?? <SkeletonList />}</>
  }
  if (error) {
    return <>{errorFallback ? errorFallback(error) : <div className="text-red-400 p-4">加载失败: {error.message}</div>}</>
  }
  return <>{children}</>
}
