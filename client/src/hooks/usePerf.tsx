/* P26-P28: 前端性能工具 hooks
 * - useDebounce: 防抖搜索输入
 * - useVirtualScroll: 大列表虚拟滚动
 * - useLazyImage: 图片懒加载（IntersectionObserver）
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'

// ── P27: 防抖 hook ──
export function useDebounce<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(id)
  }, [value, delayMs])
  return debounced
}

// ── P27: 节流 hook ──
export function useThrottle<T extends (...args: never[]) => void>(fn: T, delayMs = 200): T {
  const lastRun = useRef(0)
  return useCallback(
    (...args: Parameters<T>) => {
      const now = Date.now()
      if (now - lastRun.current >= delayMs) {
        lastRun.current = now
        fn(...args)
      }
    },
    [fn, delayMs]
  ) as T
}

// ── P26: 虚拟滚动 hook ──
// 适用于大列表（>100 项），只渲染可视区域内的项
export function useVirtualScroll<T>(
  items: T[],
  itemHeight: number,
  containerHeight: number,
  overscan = 5
) {
  const [scrollTop, setScrollTop] = useState(0)
  const onScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop)
  }, [])

  const totalHeight = items.length * itemHeight
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan)
  const visibleCount = Math.ceil(containerHeight / itemHeight) + overscan * 2
  const endIndex = Math.min(items.length, startIndex + visibleCount)

  const visibleItems = useMemo(
    () =>
      items.slice(startIndex, endIndex).map((item, i) => ({
        item,
        index: startIndex + i,
        offsetY: (startIndex + i) * itemHeight,
      })),
    [items, startIndex, endIndex]
  )

  return { visibleItems, totalHeight, onScroll, startIndex, endIndex }
}

// ── P28: 图片懒加载 hook ──
// 使用 IntersectionObserver，当图片进入视口时才加载
export function useLazyImage(src: string | undefined) {
  const [loaded, setLoaded] = useState(false)
  const ref = useRef<HTMLImageElement>(null)

  useEffect(() => {
    setLoaded(false)
    if (!src || !ref.current) return
    const img = ref.current
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setLoaded(true)
            observer.disconnect()
          }
        })
      },
      { rootMargin: '50px' }
    )
    observer.observe(img)
    return () => observer.disconnect()
  }, [src])

  return { ref, loaded, src: loaded ? src : undefined }
}

// ── P28: 通用懒加载图片组件 ──
export function LazyImage({
  src,
  alt,
  className,
  placeholder,
}: {
  src: string
  alt?: string
  className?: string
  placeholder?: string
}) {
  const { ref, loaded, src: lazySrc } = useLazyImage(src)
  return (
    <img
      ref={ref}
      src={lazySrc ?? placeholder}
      alt={alt}
      className={className}
      loading="lazy"
      decoding="async"
    />
  )
}
