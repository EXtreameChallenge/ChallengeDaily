/**
 * DataV V2 风格边框容器
 * 渐变发光边框 + 切角 clip-path + 四角发光点 + 扫描线
 */
export default function DataVBorder({
  children,
  className = '',
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={`dv-panel ${className}`}>
      <div className="dv-panel-inner">
        {children}
      </div>
      <div className="dv-panel-corners" />
    </div>
  )
}
