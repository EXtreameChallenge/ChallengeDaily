/**
 * TimeAxis — 甘特图时间刻度尺组件（四视图复用）
 * 根据 mode 渲染不同粒度的刻度：hour(日) / day(周) / week(月) / month(年)
 */
import React from 'react'

export type TimeAxisMode = 'hour' | 'day' | 'week' | 'month'

export interface TimeAxisProps {
  mode: TimeAxisMode
  /** 起始值（hour: 起始小时如8; day: 0=周一; week: 第几周; month: 起始月1-12） */
  start?: number
  /** 结束值（hour: 结束小时如22; day: 7; week: 周数; month: 12） */
  end?: number
  /** 每格宽度（px） */
  cellWidth: number
  /** 标签偏移（左侧留白 px） */
  labelOffset?: number
  /** 自定义标签（覆盖默认） */
  labels?: string[]
  /** 高亮当前格索引（今日/当月） */
  highlightIndex?: number
  /** 高度 */
  height?: number
  style?: React.CSSProperties
}

const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

const TimeAxis: React.FC<TimeAxisProps> = ({
  mode,
  start,
  end,
  cellWidth,
  labelOffset = 0,
  labels,
  highlightIndex = -1,
  height = 28,
  style,
}) => {
  let items: string[] = []
  let count = 0

  switch (mode) {
    case 'hour': {
      const s = start ?? 8
      const e = end ?? 22
      count = e - s
      items = Array.from({ length: count }, (_, i) => `${s + i}:00`)
      break
    }
    case 'day': {
      count = end ?? 7
      items = labels || WEEKDAY_LABELS.slice(0, count)
      break
    }
    case 'week': {
      const s = start ?? 1
      count = (end ?? 5) - s + 1
      items = labels || Array.from({ length: count }, (_, i) => `W${s + i}`)
      break
    }
    case 'month': {
      const s = start ?? 1
      const e = end ?? 12
      count = e - s + 1
      items = labels || MONTH_LABELS.slice(s - 1, e)
      break
    }
  }

  return (
    <div
      style={{
        display: 'flex',
        height,
        marginLeft: labelOffset,
        borderBottom: '1px solid var(--cd-border, #333)',
        position: 'relative',
        ...style,
      }}
    >
      {items.map((label, i) => (
        <div
          key={i}
          style={{
            width: cellWidth,
            minWidth: cellWidth,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 10,
            fontWeight: i === highlightIndex ? 700 : 400,
            color: i === highlightIndex ? '#7B68EE' : 'var(--cd-text-secondary, #aaa)',
            borderLeft: i === 0 ? 'none' : '1px solid var(--cd-border, #33322)',
            background: i === highlightIndex ? '#7B68EE12' : 'transparent',
            userSelect: 'none',
          }}
        >
          {label}
        </div>
      ))}
    </div>
  )
}

export default TimeAxis
