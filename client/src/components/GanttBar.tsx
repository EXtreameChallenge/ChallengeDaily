/**
 * GanttBar — 甘特图横条组件（四视图复用）
 * 渲染一条带进度填充的圆角横条，支持点击、拖拽、紧凑模式
 */
import React from 'react'
import { CATEGORY_COLORS } from '../api/client'

export interface GanttBarProps {
  /** 条的左偏移（px 或 %） */
  left: number | string
  /** 条的宽度（px 或 %） */
  width: number | string
  /** 条的顶部偏移（px），用于纵向排列 */
  top?: number
  /** 条的高度（px），默认 28 */
  height?: number
  /** 进度比例 0-1 */
  progress?: number
  /** 类别（用于取颜色） */
  category?: string
  /** 自定义颜色（优先于 category） */
  color?: string
  /** 标签文字 */
  label?: string
  /** 副标签（时长等） */
  sublabel?: string
  /** 紧凑模式（月/年视图用，高度更小） */
  compact?: boolean
  /** 是否为习惯类任务（特殊样式） */
  isHabit?: boolean
  /** 是否已完成 */
  done?: boolean
  /** 优先级颜色边框 */
  priorityColor?: string
  onClick?: () => void
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: (e: React.DragEvent) => void
  draggable?: boolean
  style?: React.CSSProperties
}

const GanttBar: React.FC<GanttBarProps> = ({
  left,
  width,
  top = 0,
  height,
  progress = 0,
  category,
  color,
  label,
  sublabel,
  compact = false,
  isHabit = false,
  done = false,
  priorityColor,
  onClick,
  onDragStart,
  onDragEnd,
  draggable = false,
  style,
}) => {
  const barColor = color || (category ? CATEGORY_COLORS[category] : '#7B68EE') || '#7B68EE'
  const h = height ?? (compact ? 20 : 28)
  const clampedProgress = Math.min(1, Math.max(0, progress))

  return (
    <div
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      title={label ? `${label}${sublabel ? ` · ${sublabel}` : ''}` : undefined}
      style={{
        position: 'absolute',
        left: typeof left === 'number' ? `${left}px` : left,
        width: typeof width === 'number' ? `${width}px` : width,
        top: `${top}px`,
        height: `${h}px`,
        borderRadius: compact ? 3 : 5,
        overflow: 'hidden',
        cursor: onClick ? 'pointer' : draggable ? 'grab' : 'default',
        border: `1px solid ${done ? 'var(--cd-green, #10b981)' : barColor}44`,
        borderLeft: priorityColor ? `3px solid ${priorityColor}` : `1px solid ${barColor}66`,
        background: isHabit
          ? `repeating-linear-gradient(90deg, ${barColor}18, ${barColor}18 4px, transparent 4px, transparent 8px)`
          : `${barColor}22`,
        transition: 'box-shadow 0.15s, transform 0.1s',
        userSelect: 'none',
        ...style,
      }}
      className="gantt-bar group"
    >
      {/* 进度填充层 */}
      {clampedProgress > 0 && (
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: `${clampedProgress * 100}%`,
            background: done ? 'var(--cd-green, #10b981)' : barColor,
            opacity: done ? 0.5 : 0.35,
            borderRadius: 'inherit',
          }}
        />
      )}
      {/* 文字层 */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          height: '100%',
          padding: `0 ${compact ? 4 : 8}px`,
          overflow: 'hidden',
        }}
      >
        {label && (
          <span
            style={{
              fontSize: compact ? 9 : 11,
              fontWeight: 500,
              color: done ? 'var(--cd-text-tertiary, #888)' : 'var(--cd-text, #e0e0e0)',
              textDecoration: done ? 'line-through' : 'none',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              flex: 1,
              minWidth: 0,
            }}
          >
            {label}
          </span>
        )}
        {sublabel && !compact && (
          <span
            style={{
              fontSize: 9,
              color: 'var(--cd-text-tertiary, #888)',
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            {sublabel}
          </span>
        )}
      </div>
    </div>
  )
}

export default GanttBar
