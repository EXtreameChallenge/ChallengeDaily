import { useState, useEffect } from 'react'

/**
 * 大屏顶部装饰标题栏
 * 包含标题、日期时间、装饰线
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
      {/* 两侧装饰线 */}
      <div className="flex items-center justify-center gap-6 mb-1">
        <div className="flex-1 h-px bg-gradient-to-r from-transparent via-[rgba(0,212,255,0.3)] to-[rgba(0,212,255,0.6)]" />
        <h1>极光数据大屏</h1>
        <div className="flex-1 h-px bg-gradient-to-l from-transparent via-[rgba(0,212,255,0.3)] to-[rgba(0,212,255,0.6)]" />
      </div>

      {/* 日期和时间 */}
      <div className="aurora-header-sub flex items-center justify-center gap-6">
        <span>{dateStr}</span>
        <span className="aurora-clock">
          {hours}:{minutes}:{seconds}
        </span>
      </div>

      {/* 底部装饰线 */}
      <div className="aurora-header-line" />
    </div>
  )
}
