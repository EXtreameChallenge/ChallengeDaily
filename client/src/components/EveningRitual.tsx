import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { request } from '../api/client'
import { Moon, ChevronDown, ChevronUp, FileText } from 'lucide-react'
import InsightCards, { Insight } from './InsightCards'

interface EveningData {
  has_activity: boolean
  productivity_score: number
  focus_minutes: number
  tasks_completed: number
  insights: Insight[]
}

const REFLECTIONS = [
  { key: 'great', label: '很棒', emoji: '😄' },
  { key: 'good', label: '不错', emoji: '🙂' },
  { key: 'okay', label: '一般', emoji: '😐' },
  { key: 'tough', label: '艰难', emoji: '😮‍💨' },
]

export default function EveningRitual() {
  const navigate = useNavigate()
  const [data, setData] = useState<EveningData | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [insights, setInsights] = useState<Insight[]>([])
  const [reflection, setReflection] = useState('')
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  const hour = new Date().getHours()
  const inWindow = hour >= 21

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await request('/api/ritual/evening') as EveningData
      setData(res)
      setInsights(res.insights || [])
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (inWindow) load()
  }, [inWindow, load])

  if (!inWindow || dismissed) return null
  if (loading) {
    return (
      <div className="bg-cd-bg-card border border-cd-border rounded-xl p-4 text-xs text-cd-text-tertiary">
        加载晚间回顾...
      </div>
    )
  }
  if (!data || !data.has_activity) return null

  const handleIgnore = (index: number) => {
    setInsights((prev) => prev.filter((_, i) => i !== index))
  }

  const handleGenerateReport = async () => {
    setSubmitting(true)
    try {
      await request('/api/ritual/evening/reflect', {
        method: 'POST',
        body: JSON.stringify({ reflection, note }),
      })
    } catch {
      // silent
    } finally {
      setSubmitting(false)
    }
    navigate('/report')
  }

  const scoreColor =
    data.productivity_score >= 80
      ? 'text-cd-green'
      : data.productivity_score >= 50
        ? 'text-cd-text'
        : 'text-red-400'

  return (
    <div className="bg-cd-bg-card border border-cd-border rounded-xl overflow-hidden">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-cd-hover transition-colors"
      >
        <div className="flex items-center gap-2">
          <Moon size={16} className="text-cd-accent" />
          <span className="text-sm font-medium text-cd-text">晚间回顾</span>
        </div>
        {collapsed ? (
          <ChevronDown size={16} className="text-cd-text-tertiary" />
        ) : (
          <ChevronUp size={16} className="text-cd-text-tertiary" />
        )}
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 space-y-4">
          <div className="flex items-center gap-4 bg-cd-bg-secondary rounded-lg px-4 py-3">
            <div className="text-center shrink-0">
              <div className={'text-2xl font-bold ' + scoreColor}>
                {data.productivity_score}
              </div>
              <div className="text-[10px] text-cd-text-tertiary">效率分</div>
            </div>
            <div className="flex-1 grid grid-cols-2 gap-2">
              <div>
                <div className="text-sm font-semibold text-cd-text">
                  {data.focus_minutes}
                </div>
                <div className="text-[10px] text-cd-text-tertiary">专注分钟</div>
              </div>
              <div>
                <div className="text-sm font-semibold text-cd-text">
                  {data.tasks_completed}
                </div>
                <div className="text-[10px] text-cd-text-tertiary">完成任务</div>
              </div>
            </div>
          </div>

          {insights.length > 0 && (
            <div>
              <div className="text-xs text-cd-text-secondary mb-2">今日洞察</div>
              <InsightCards insights={insights} onIgnore={handleIgnore} />
            </div>
          )}

          <div>
            <div className="text-xs text-cd-text-secondary mb-2">快速回顾</div>
            <div className="flex gap-2">
              {REFLECTIONS.map((r) => (
                <button
                  key={r.key}
                  onClick={() => setReflection(r.key)}
                  className={
                    'flex-1 flex flex-col items-center gap-1 py-2 rounded-lg border transition-colors ' +
                    (reflection === r.key
                      ? 'bg-cd-accent/15 border-cd-accent/40'
                      : 'bg-cd-bg-secondary border-cd-border hover:border-cd-text-tertiary')
                  }
                >
                  <span className="text-base">{r.emoji}</span>
                  <span className="text-[10px] text-cd-text-secondary">{r.label}</span>
                </button>
              ))}
            </div>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="今天有什么想记录的..."
              rows={2}
              className="mt-2 w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-xs text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50 resize-none"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={handleGenerateReport}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium bg-cd-accent/15 text-cd-accent rounded-lg border border-cd-accent/25 hover:bg-cd-accent/25 transition-colors disabled:opacity-50"
            >
              <FileText size={14} /> 生成今日日报
            </button>
            <button
              onClick={() => setDismissed(true)}
              disabled={submitting}
              className="flex-1 px-3 py-2 text-xs text-cd-text-secondary bg-cd-bg-secondary rounded-lg border border-cd-border hover:text-cd-text transition-colors disabled:opacity-50"
            >
              明天再说
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
