import { useState, useRef, useEffect } from 'react'
import { HelpCircle } from 'lucide-react'

/**
 * P11-1：教育 Tooltip 组件
 * 为专业指标提供简短解释，鼠标悬停/点击时显示。
 * 新手用户友好，帮助他们理解"注意力碎片化指数"等专业术语。
 */
interface EduTooltipProps {
  text: string
  size?: number
  className?: string
}

export function EduTooltip({ text, size = 12, className = '' }: EduTooltipProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  // 点击外部关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <span ref={ref} className={`relative inline-flex ${className}`}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="text-cd-text-tertiary hover:text-cd-green transition-colors"
        aria-label="查看解释"
      >
        <HelpCircle size={size} />
      </button>
      {open && (
        <span className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1.5 w-48 px-2.5 py-1.5 rounded-lg bg-cd-bg-card border border-cd-border shadow-lg text-[11px] text-cd-text leading-relaxed">
          {text}
          <span className="absolute top-full left-1/2 -translate-x-1/2 -mt-px border-4 border-transparent border-t-cd-border" />
        </span>
      )}
    </span>
  )
}

/**
 * 教育提示卡片：用于空状态引导新手用户
 * 根据用户使用天数显示不同的引导消息
 */
interface EmptyStateHintProps {
  dayCount: number  // 用户已使用天数
  feature: string   // 功能名称
  hint: string      // 引导提示
}

export function EmptyStateHint({ dayCount, feature, hint }: EmptyStateHintProps) {
  // 前 3 天显示新手鼓励
  if (dayCount <= 3) {
    return (
      <div className="rounded-xl p-4 bg-gradient-to-br from-cd-green/8 to-cd-accent/5 border border-cd-green/15">
        <div className="text-xs text-cd-green font-medium mb-1">新手引导</div>
        <div className="text-sm text-cd-text">{feature}</div>
        <div className="text-xs text-cd-text-secondary mt-1 leading-relaxed">{hint}</div>
      </div>
    )
  }
  // 进阶用户：简化提示
  return (
    <div className="text-center py-6 text-xs text-cd-text-tertiary">
      {hint}
    </div>
  )
}
