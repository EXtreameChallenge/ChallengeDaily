import { useState, useRef, useEffect } from 'react'
import { HelpCircle } from 'lucide-react'

/**
 * P15-4：教育性 tooltip 组件
 * 在指标旁显示问号图标，hover/click 展开解释
 *
 * 用法：<InfoTooltip text="这是该指标的解释" />
 * 或富文本：<InfoTooltip content={<div>...</div>} />
 */
interface InfoTooltipProps {
  /** 简单文本解释 */
  text?: string
  /** 富文本内容（与 text 二选一） */
  content?: React.ReactNode
  /** 图标大小，默认 12 */
  size?: number
  /** 标题（可选，显示在内容上方） */
  title?: string
}

export default function InfoTooltip({ text, content, size = 12, title }: InfoTooltipProps) {
  const [show, setShow] = useState(false)
  const [position, setPosition] = useState<{ top: number; left: number; arrowBelow: boolean }>({ top: 0, left: 0, arrowBelow: false })
  const iconRef = useRef<HTMLSpanElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  const computePosition = () => {
    if (!iconRef.current) return
    const rect = iconRef.current.getBoundingClientRect()
    const tooltipWidth = 280
    const tooltipHeight = 160
    const viewportWidth = window.innerWidth
    const viewportHeight = window.innerHeight
    // 水平：尽量居中于图标，避免超出视口
    let left = rect.left + rect.width / 2 - tooltipWidth / 2
    left = Math.max(8, Math.min(left, viewportWidth - tooltipWidth - 8))
    // 垂直：默认在图标上方，空间不足则放下方
    const spaceAbove = rect.top
    const spaceBelow = viewportHeight - rect.bottom
    let top: number
    let arrowBelow: boolean
    if (spaceAbove >= tooltipHeight + 12 || spaceAbove >= spaceBelow) {
      top = rect.top - tooltipHeight - 8
      arrowBelow = true
    } else {
      top = rect.bottom + 8
      arrowBelow = false
    }
    // 防止 top 为负
    top = Math.max(8, top)
    setPosition({ top, left, arrowBelow })
  }

  useEffect(() => {
    if (!show) return
    computePosition()
    const handleClickOutside = (e: MouseEvent) => {
      if (
        iconRef.current && !iconRef.current.contains(e.target as Node) &&
        tooltipRef.current && !tooltipRef.current.contains(e.target as Node)
      ) {
        setShow(false)
      }
    }
    const handleScroll = () => setShow(false)
    document.addEventListener('mousedown', handleClickOutside)
    window.addEventListener('scroll', handleScroll, true)
    window.addEventListener('resize', computePosition)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      window.removeEventListener('scroll', handleScroll, true)
      window.removeEventListener('resize', computePosition)
    }
  }, [show])

  return (
    <>
      <span
        ref={iconRef}
        className="inline-flex items-center cursor-help text-cd-text-tertiary hover:text-cd-text-secondary transition"
        onMouseEnter={() => { setShow(true); }}
        onMouseLeave={() => setShow(false)}
        onClick={(e) => { e.stopPropagation(); setShow(s => !s) }}
      >
        <HelpCircle size={size} />
      </span>
      {show && (
        <div
          ref={tooltipRef}
          className="fixed z-50 w-[280px] max-h-[200px] overflow-y-auto bg-cd-bg-card border border-cd-border rounded-lg shadow-xl p-3 text-xs text-cd-text leading-relaxed animate-[fadeIn_0.15s_ease]"
          style={{ top: position.top, left: position.left }}
          onMouseEnter={() => setShow(true)}
          onMouseLeave={() => setShow(false)}
        >
          {title && (
            <div className="font-semibold text-cd-text mb-1.5 pb-1.5 border-b border-cd-border">{title}</div>
          )}
          {content || <span>{text}</span>}
        </div>
      )}
      <style>{`@keyframes fadeIn { from { opacity: 0; transform: translateY(-2px) } to { opacity: 1; transform: translateY(0) } }`}</style>
    </>
  )
}

/**
 * P15-4：指标释义字典
 * 集中管理常用指标的解释文本，方便复用
 */
export const METRIC_EXPLANATIONS: Record<string, { title: string; text: string }> = {
  focus_min: {
    title: '专注时长',
    text: '当日所有非"生活"分类的活动时长之和，单位为分钟。截图采样间隔 × 活动条数累计得出。',
  },
  deep_work_hours: {
    title: '深度工作时长',
    text: '单次连续 ≥25 分钟、期间不切换分类的专注时段。基于《深度工作》一书的定义，是衡量高产出的核心指标。',
  },
  streak_days: {
    title: '连续天数',
    text: '从今天往前数，每日都有专注活动（>0 分钟）的连续天数。中间断一天即归零。',
  },
  completion_rate: {
    title: '完成率',
    text: '近 N 天中有打卡记录的天数占比。如 30 天中打卡 20 天，完成率为 66.7%。',
  },
  distraction_index: {
    title: '分心指数',
    text: '一天内分类切换频率的指标。切换越频繁，指数越高，代表注意力越碎片化。建议保持在 30% 以下。',
  },
  efficiency: {
    title: '专注效率',
    text: '深度工作时长 / 总专注时长 × 100%。高于 60% 为优秀，低于 30% 建议审视工作节奏。',
  },
  cross_domain_index: {
    title: '跨域指数',
    text: '一天内涉及的不同大类数量（如开发+学习+沟通=3）。适度跨域利于创意，过高则易分散。',
  },
  habit_consistency: {
    title: '习惯一致性',
    text: '近 7 天习惯打卡的稳定性，0-100%。100% 表示每日都按目标完成，波动越小数值越高。',
  },
  category_count: {
    title: '分类数',
    text: '当日活动涉及的不同分类数（如开发、学习、沟通等）。反映工作多样性。',
  },
  pomodoro_count: {
    title: '番茄数',
    text: '当日完成的番茄钟会话数。一个标准番茄钟为 25 分钟专注 + 5 分钟休息。',
  },
  flow_state: {
    title: '心流状态',
    text: '当连续专注 ≥90 分钟且分心切换 ≤2 次时进入心流。心流时段产出最高，建议保护不被打断。',
  },
}
