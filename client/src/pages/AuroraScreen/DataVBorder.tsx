/**
 * DataV 风格边框容器
 * 四角装饰 + 半透明暗色背景 + 扫描线效果
 */
export default function DataVBorder({
  children,
  className = '',
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={`dv-border-box ${className}`}>
      <div className="dv-border-inner" />
      <div className="dv-content">
        {children}
      </div>
    </div>
  )
}
