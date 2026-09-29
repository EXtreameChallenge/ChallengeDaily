import { useState, useEffect } from 'react'
import { getFocusScore, type FocusScoreData } from '../api/client'
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown } from 'lucide-react'

const GRADE_COLORS: Record<string, string> = {
  S: 'text-emerald-500',
  A: 'text-green-500',
  B: 'text-blue-400',
  C: 'text-amber-400',
  D: 'text-red-400',
}

const GRADE_RING_COLORS: Record<string, string> = {
  S: '#10b981',
  A: '#22c55e',
  B: '#60a5fa',
  C: '#f59e0b',
  D: '#ef4444',
}

const BREAKDOWN_LABELS: Record<string, { label: string; icon: string }> = {
  productivity: { label: '生产力', icon: '⚡' },
  pomodoro_quality: { label: '番茄质量', icon: '🍅' },
  attention: { label: '注意力', icon: '🎯' },
  task_completion: { label: '任务完成', icon: '✅' },
  habit_completion: { label: '习惯打卡', icon: '📋' },
}

export default function FocusScoreRing() {
  const [data, setData] = useState<FocusScoreData | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let isFirst = true
    const fetchData = async () => {
      try {
        const result = await getFocusScore(undefined, 7)
        setData(result)
      } catch (err) {
        console.error('Failed to load focus score:', err)
      } finally {
        setLoading(false)
        isFirst = false
      }
    }
    fetchData()
    const interval = setInterval(() => {
      if (!document.hidden) fetchData()
    }, 120000) // 2 分钟刷新
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center gap-4 animate-pulse">
        <div className="w-24 h-24 rounded-full bg-cd-surface-elevated" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-cd-surface-elevated rounded-lg w-20" />
          <div className="h-3 bg-cd-surface-elevated rounded-lg w-32" />
        </div>
      </div>
    )
  }

  if (!data) return null

  const ringColor = GRADE_RING_COLORS[data.grade] || '#6b7280'
  const score = data.score
  const circumference = 2 * Math.PI * 42
  const dashOffset = circumference * (1 - score / 100)

  // 趋势数据
  const trend = data.trend || []
  const trendDelta = trend.length >= 2
    ? trend[trend.length - 1].score - trend[trend.length - 2].score
    : 0

  return (
    <div className="bg-cd-surface rounded-2xl p-5 border border-cd-border">
      <div className="flex items-center gap-5">
        {/* Score Ring */}
        <div className="relative w-28 h-28 shrink-0">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="42" fill="none" stroke="currentColor" strokeWidth="6"
              className="text-cd-surface-elevated" />
            <circle cx="50" cy="50" r="42" fill="none" stroke={ringColor} strokeWidth="6"
              strokeLinecap="round" strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              style={{ transition: 'stroke-dashoffset 1s ease-in-out' }} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-3xl font-bold ${GRADE_COLORS[data.grade] || 'text-cd-text'} font-brand`}>
              {data.grade}
            </span>
            <span className="text-xs text-cd-text-tertiary mt-0.5">{score.toFixed(0)}分</span>
          </div>
        </div>

        {/* Summary */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-cd-text">Focus Score</h3>
            {trendDelta !== 0 && (
              <span className={`flex items-center gap-0.5 text-xs ${trendDelta > 0 ? 'text-cd-green' : 'text-red-400'}`}>
                {trendDelta > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                {Math.abs(trendDelta).toFixed(1)}
              </span>
            )}
          </div>
          <p className="text-xs text-cd-text-tertiary mb-3">
            融合生产力、番茄质量、注意力、任务和习惯的综合效率评分
          </p>
          {/* Mini trend sparkline */}
          {trend.length > 1 && (
            <div className="flex items-end gap-1 h-8">
              {trend.map((t, i) => {
                const h = Math.max(4, (t.score / 100) * 32)
                const c = GRADE_RING_COLORS[t.grade] || '#6b7280'
                return (
                  <div key={i} className="flex-1 flex flex-col items-center justify-end" style={{ maxWidth: 12 }}>
                    <div style={{ height: h, backgroundColor: c, opacity: i === trend.length - 1 ? 1 : 0.4 }}
                      className="w-full rounded-lg" />
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Expand button */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="shrink-0 p-1.5 rounded-2xl hover:bg-cd-surface-elevated text-cd-text-tertiary transition"
        >
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {/* Breakdown details */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-cd-border space-y-2.5 animate-fade-in">
          {Object.entries(data.breakdown).map(([key, item]) => {
            const meta = BREAKDOWN_LABELS[key] || { label: key, icon: '📊' }
            return (
              <div key={key} className="flex items-center gap-3">
                <span className="text-base">{meta.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-xs text-cd-text-secondary">{meta.label}</span>
                    <span className="text-xs text-cd-text-tertiary">
                      {item.score.toFixed(0)} × {(item.weight * 100).toFixed(0)}% = {item.weighted.toFixed(1)}
                    </span>
                  </div>
                  <div className="h-1.5 bg-cd-surface-elevated rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-700"
                      style={{ width: `${item.score}%`, backgroundColor: GRADE_RING_COLORS[
                        item.score >= 90 ? 'S' : item.score >= 80 ? 'A' : item.score >= 70 ? 'B' : item.score >= 60 ? 'C' : 'D'
                      ] || '#6b7280' }} />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
