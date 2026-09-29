import { useState, useEffect } from 'react'
import { getAnomalies, type AnomalyItem } from '../api/client'
import { AlertTriangle, AlertCircle, Info, X } from 'lucide-react'
import { safeText } from '../utils/helpers'

const SEVERITY_CONFIG = {
  high: {
    icon: AlertCircle,
    color: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/20',
    label: '严重',
  },
  medium: {
    icon: AlertTriangle,
    color: 'text-amber-400',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/20',
    label: '警告',
  },
  low: {
    icon: Info,
    color: 'text-blue-400',
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/20',
    label: '提示',
  },
}

export default function AnomalyAlert() {
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([])
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const result = await getAnomalies(7)
        setAnomalies(result.anomalies)
      } catch (err) {
        console.error('Failed to load anomalies:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
    const interval = setInterval(() => {
      if (!document.hidden) fetchData()
    }, 180000) // 3 分钟刷新
    return () => clearInterval(interval)
  }, [])

  if (loading || anomalies.length === 0) return null

  const visibleAnomalies = anomalies.filter(a => !dismissed.has(a.type))
  if (visibleAnomalies.length === 0) return null

  const dismiss = (type: string) => {
    setDismissed(prev => new Set([...prev, type]))
  }

  return (
    <div className="space-y-2">
      {visibleAnomalies.map((anomaly, i) => {
        const config = SEVERITY_CONFIG[anomaly.severity] || SEVERITY_CONFIG.low
        const Icon = config.icon
        return (
          <div key={`${anomaly.type}-${i}`}
            className={`flex items-start gap-3 p-3 rounded-xl border ${config.bg} ${config.border}`}>
            <Icon size={18} className={`shrink-0 mt-0.5 ${config.color}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-sm font-medium text-cd-text">{anomaly.title}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-lg ${config.bg} ${config.color} font-medium`}>
                  {config.label}
                </span>
              </div>
              <p className="text-xs text-cd-text-secondary mb-1">{safeText(anomaly.detail)}</p>
              <p className="text-xs text-cd-text-tertiary">
                <span className="text-cd-green">建议</span> · {anomaly.suggestion}
              </p>
            </div>
            <button
              onClick={() => dismiss(anomaly.type)}
              className="shrink-0 p-1 rounded-lg hover:bg-cd-surface-elevated text-cd-text-tertiary transition"
            >
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}
