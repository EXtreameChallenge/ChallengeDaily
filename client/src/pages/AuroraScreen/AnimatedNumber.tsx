import { useState, useEffect, useRef } from 'react'

/**
 * 动画数字：从 0 滚动到目标值，带发光效果
 */
export default function AnimatedNumber({
  value,
  duration = 1500,
  className = '',
  prefix = '',
  suffix = '',
  decimals = 0,
}: {
  value: number
  duration?: number
  className?: string
  prefix?: string
  suffix?: string
  decimals?: number
}) {
  const [current, setCurrent] = useState(0)
  const ref = useRef(value)
  const frameRef = useRef<number>(0)

  useEffect(() => {
    const start = ref.current
    const end = value
    ref.current = end

    if (start === end) return

    const startTime = performance.now()
    const animate = (now: number) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      // easeOutExpo
      const ease = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress)
      setCurrent(start + (end - start) * ease)
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate)
      }
    }
    frameRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frameRef.current)
  }, [value, duration])

  return (
    <span className={`aurora-number ${className}`}>
      {prefix}{decimals > 0 ? current.toFixed(decimals) : Math.round(current)}{suffix}
    </span>
  )
}
