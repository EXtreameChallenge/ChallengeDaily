import { useState, useCallback } from 'react'
import { request } from '../api/client'
import { RefreshCw, Check } from 'lucide-react'

interface ScheduleBlock {
  time_start: string
  time_end: string
  task: string
  type: string
}

interface Props {
  initialSchedule?: ScheduleBlock[]
}

const TYPE_ICONS: Record<string, string> = {
  focus: '🍅',
  meeting: '📅',
  break: '☕',
  learning: '📚',
  admin: '📋',
  default: '📌',
}

export default function SchedulePanel({ initialSchedule }: Props) {
  const [schedule, setSchedule] = useState<ScheduleBlock[]>(initialSchedule || [])
  const [loading, setLoading] = useState(false)
  const [adopted, setAdopted] = useState(false)
  const [error, setError] = useState('')

  const fetchSchedule = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await request('/api/scheduler/suggest') as { schedule?: ScheduleBlock[] }
      setSchedule(data.schedule || [])
    } catch {
      setError('获取排程建议失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleAdopt = async () => {
    setLoading(true)
    setError('')
    try {
      await request('/api/scheduler/adopt', {
        method: 'POST',
        body: JSON.stringify({ schedule }),
      })
      setAdopted(true)
    } catch {
      setError('采纳排程失败')
    } finally {
      setLoading(false)
    }
  }

  if (!schedule.length && !loading) {
    return (
      <div className="text-center py-4">
        <button
          onClick={fetchSchedule}
          className="text-xs text-cd-green hover:text-cd-green/80 font-medium transition-colors"
        >
          获取 AI 排程建议
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {loading && (
        <div className="flex items-center justify-center py-4 text-xs text-cd-text-tertiary">
          <RefreshCw size={14} className="animate-spin mr-2" />
          加载中...
        </div>
      )}

      {!loading && schedule.map((block, idx) => (
        <div
          key={idx}
          className="flex items-center gap-3 bg-cd-bg-secondary rounded-lg px-3 py-2 border border-cd-border/50"
        >
          <span className="text-sm shrink-0">
            {TYPE_ICONS[block.type] || TYPE_ICONS.default}
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium text-cd-text truncate">{block.task}</div>
            <div className="text-[10px] text-cd-text-tertiary">
              {block.time_start} - {block.time_end}
            </div>
          </div>
        </div>
      ))}

      {error && (
        <div className="text-xs text-red-400 py-1">{error}</div>
      )}

      {adopted ? (
        <div className="flex items-center gap-2 text-xs text-cd-green py-2 justify-center">
          <Check size={14} /> 已采纳排程
        </div>
      ) : (
        !loading && schedule.length > 0 && (
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleAdopt}
              disabled={loading}
              className="flex-1 px-3 py-2 text-xs font-medium bg-cd-green/15 text-cd-green rounded-lg border border-cd-green/25 hover:bg-cd-green/25 transition-colors disabled:opacity-50"
            >
              采纳全部
            </button>
            <button
              onClick={fetchSchedule}
              disabled={loading}
              className="px-3 py-2 text-xs text-cd-text-secondary bg-cd-bg-secondary rounded-lg border border-cd-border hover:text-cd-text transition-colors disabled:opacity-50"
            >
              重新生成
            </button>
          </div>
        )
      )}
    </div>
  )
}
