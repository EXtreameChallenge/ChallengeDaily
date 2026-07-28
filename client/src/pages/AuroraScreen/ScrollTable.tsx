import { useRef, useEffect, useState } from 'react'

/**
 * 自动向上滚动的数据表格（大屏风格）
 * 数据超过可视高度时自动循环滚动
 */
export default function ScrollTable({
  rows,
  renderRow,
  rowHeight = 36,
  maxHeight = 260,
  scrollDuration = 20,
}: {
  rows: any[]
  renderRow: (row: any, index: number) => React.ReactNode
  rowHeight?: number
  maxHeight?: number
  scrollDuration?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [shouldScroll, setShouldScroll] = useState(false)

  useEffect(() => {
    if (containerRef.current) {
      const totalHeight = rows.length * rowHeight
      setShouldScroll(totalHeight > maxHeight)
    }
  }, [rows.length, rowHeight, maxHeight])

  // 复制一份内容实现无缝循环
  const displayRows = shouldScroll ? [...rows, ...rows] : rows

  return (
    <div
      ref={containerRef}
      className="aurora-scroll-table"
      style={{ maxHeight, overflow: 'hidden' }}
    >
      <div
        className={shouldScroll ? 'aurora-scroll-table-inner' : ''}
        style={shouldScroll ? { '--scroll-duration': `${scrollDuration}s` } as React.CSSProperties : {}}
      >
        {displayRows.map((row, i) => (
          <div key={i} style={{ height: rowHeight }}>
            {renderRow(row, i % rows.length)}
          </div>
        ))}
      </div>
    </div>
  )
}
