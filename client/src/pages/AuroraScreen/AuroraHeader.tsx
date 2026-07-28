import { useState, useEffect } from 'react'

/**
 * 大屏顶部飞翼标题栏
 * 包含：两侧飞翼装饰线 + 菱形 + 箭头 + 居中标题 + 日期时间 + 中心菱形分隔符
 */
export default function AuroraHeader() {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const hours = String(time.getHours()).padStart(2, '0')
  const minutes = String(time.getMinutes()).padStart(2, '0')
  const seconds = String(time.getSeconds()).padStart(2, '0')
  const dateStr = time.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'long',
  })

  return (
    <div className="aurora-header">
      {/* 左飞翼 */}
      <div className="aurora-header-wing left">
        <div className="aurora-header-line-top" />
        <div className="aurora-header-line-main" />
        <div className="aurora-header-diamond" />
        <div className="aurora-header-arrow" />
      </div>

      {/* 中心标题 */}
      <div className="aurora-header-title">极光数据大屏</div>

      {/* 右飞翼 */}
      <div className="aurora-header-wing right">
        <div className="aurora-header-line-top" />
        <div className="aurora-header-line-main" />
        <div className="aurora-header-diamond" />
        <div className="aurora-header-arrow" />
      </div>

      {/* 中心菱形分隔装饰 */}
      <div className="aurora-header-center-deco">
        <div className="aurora-header-center-diamond" />
      </div>

      {/* 日期时间行 */}
      <div className="aurora-header-datetime">
        <span>{dateStr}</span>
        <span className="aurora-clock">{hours}:{minutes}:{seconds}</span>
      </div>
    </div>
  )
}
