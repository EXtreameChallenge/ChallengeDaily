import { useNavigate } from 'react-router-dom'

export interface Insight {
  type: string
  text: string
  action_label?: string
  action_type?: string
}

interface Props {
  insights: Insight[]
  onIgnore?: (index: number) => void
}

const TYPE_ICONS: Record<string, string> = {
  positive: '✅',
  suggestion: '💡',
  warning: '⚠️',
  care: '💚',
  fun: '🎯',
  trend: '📈',
  rule: '📏',
  focus: '🍅',
}

export default function InsightCards({ insights, onIgnore }: Props) {
  const navigate = useNavigate()

  const handleAction = (actionType?: string) => {
    if (!actionType) return
    switch (actionType) {
      case 'create_rule':
        navigate('/rules-engine')
        break
      case 'start_pomodoro':
        navigate('/focus?autostart=1')
        break
      case 'view_trend':
        navigate('/heatmap')
        break
      default:
        break
    }
  }

  if (!insights.length) return null

  return (
    <div className="space-y-2">
      {insights.map((insight, idx) => (
        <div
          key={idx}
          className="flex items-start gap-3 bg-cd-bg-secondary rounded-lg px-3 py-2.5 border border-cd-border/50"
        >
          <span className="text-base mt-0.5 shrink-0">
            {TYPE_ICONS[insight.type] || '💡'}
          </span>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-cd-text leading-relaxed">{insight.text}</p>
            {insight.action_label && (
              <button
                onClick={() => handleAction(insight.action_type)}
                className="mt-1.5 text-[11px] text-cd-green hover:text-cd-green/80 font-medium transition-colors"
              >
                {insight.action_label} →
              </button>
            )}
          </div>
          {onIgnore && (
            <button
              onClick={() => onIgnore(idx)}
              className="text-cd-text-tertiary hover:text-cd-text text-xs shrink-0 transition-colors"
              title="忽略"
            >
              ✕
            </button>
          )}
        </div>
      ))}
    </div>
  )
}
