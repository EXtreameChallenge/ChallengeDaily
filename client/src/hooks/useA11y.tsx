/* P41-P44: 可访问性工具集
 * - useFocusTrap: 模态框焦点陷阱
 * - useKeyboardNav: 键盘导航
 * - useAnnouncement: 屏幕阅读器公告
 * - ariaHelpers: ARIA 属性辅助
 * - usePrefersReducedMotion: 减弱动画偏好检测
 * - usePrefersHighContrast: 高对比度模式检测
 */
import { useEffect, useRef, useCallback, useState, type ReactNode } from 'react'

// ── P43: 焦点陷阱 — 模态框内焦点循环 ──
export function useFocusTrap<T extends HTMLElement = HTMLDivElement>(active: boolean) {
  const ref = useRef<T>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!active || !ref.current) return
    previouslyFocused.current = document.activeElement as HTMLElement

    const container = ref.current
    const focusable = container.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    if (focusable.length > 0) {
      focusable[0].focus()
    } else {
      container.tabIndex = -1
      container.focus()
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      if (focusable.length === 0) {
        e.preventDefault()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    container.addEventListener('keydown', handleKeyDown)
    return () => {
      container.removeEventListener('keydown', handleKeyDown)
      previouslyFocused.current?.focus()
    }
  }, [active])

  return ref
}

// ── P41: 键盘导航 hook ──
export function useKeyboardNav(
  handlers: Record<string, (e: KeyboardEvent) => void>,
  deps: unknown[] = []
) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const key = e.key
      const combo = [
        e.ctrlKey ? 'Ctrl' : '',
        e.shiftKey ? 'Shift' : '',
        e.altKey ? 'Alt' : '',
        key,
      ].filter(Boolean).join('+')

      if (handlers[combo]) {
        handlers[combo](e)
      } else if (handlers[key]) {
        handlers[key](e)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}

// ── P44: 屏幕阅读器公告 ──
export function useAnnouncement() {
  const [announcement, setAnnouncement] = useState('')

  const announce = useCallback((message: string) => {
    setAnnouncement('')
    setTimeout(() => setAnnouncement(message), 50)
  }, [])

  const liveRegion: ReactNode = (
    <div
      aria-live="polite"
      aria-atomic="true"
      style={{
        position: 'absolute',
        width: '1px',
        height: '1px',
        padding: 0,
        margin: '-1px',
        overflow: 'hidden',
        clip: 'rect(0,0,0,0)',
        whiteSpace: 'nowrap',
        border: 0,
      }}
    >
      {announcement}
    </div>
  )

  return { announce, liveRegion }
}

// ── P42: ARIA 属性辅助 ──
export const aria = {
  label: (text: string) => ({ 'aria-label': text }),
  describedBy: (id: string) => ({ 'aria-describedby': id }),
  expanded: (isExpanded: boolean) => ({
    'aria-expanded': isExpanded,
    'aria-controls': isExpanded ? 'panel' : undefined,
  }),
  busy: (isLoading: boolean) => ({ 'aria-busy': isLoading }),
  required: () => ({ 'aria-required': true }),
  invalid: (isInvalid: boolean) => ({ 'aria-invalid': isInvalid }),
}

// ── P47: prefers-reduced-motion 检测 ──
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return reduced
}

// ── P45: 高对比度模式检测 ──
export function usePrefersHighContrast(): boolean {
  const [highContrast, setHighContrast] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-contrast: more)')
    setHighContrast(mq.matches)
    const handler = (e: MediaQueryListEvent) => setHighContrast(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return highContrast
}
