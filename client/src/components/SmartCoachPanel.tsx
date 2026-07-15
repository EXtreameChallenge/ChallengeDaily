import { useState, useEffect, useCallback } from 'react'
import { Sparkles, RefreshCw, Loader2, TrendingUp, Clock, X } from 'lucide-react'
import { getChronotype, getSmartSuggestions, type Chronotype, type SmartSuggestion } from '../api/client'

/**
 * P16: 智能教练面板 — 生物钟检测 + 主动智能建议
 * 显示用户的生物钟类型、个性化问候，以及基于行为模式的可执行建议。
 */
export default function SmartCoachPanel() {
  const [chrono, setChrono] = useState<Chronotype | null>(null)
  const [suggestions, setSuggestions] = useState<SmartSuggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    else setRefreshing(true)
    try {
      const [c, s] = await Promise.all([
        getChronotype(),
        getSmartSuggestions(),
      ])
      setChrono(c)
      setSuggestions(s.suggestions || [])
    } catch (err) {
      console.error('[SmartCoachPanel] 加载失败:', err)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    loadData()
    const timer = setInterval(() => loadData(true), 600000) // 10 分钟刷新
    return () => clearInterval(timer)
  }, [loadData])

  const handleDismiss = (type: string) => {
    setDismissed(prev => new Set(prev).add(type))
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-cd-text-tertiary py-3">
        <Loader2 size={14} className="animate-spin" />
        正在分析你的行为模式...
      </div>
    )
  }

  const visibleSuggestions = suggestions.filter(s => !dismissed.has(s.type))

  return (
    <div className="space-y-3">
      {/* 生物钟卡片 */}
      {chrono && (
        <div className="rounded-xl bg-gradient-to-br from-indigo-500/8 via-purple-500/8 to-blue-500/8 dark:from-indigo-500/10 dark:via-purple-500/10 dark:to-blue-500/10 border border-indigo-200/30 dark:border-indigo-500/15 p-4">
          <div className="flex items-start gap-3">
            <span className="text-2xl shrink-0 leading-none mt-0.5">{chrono.icon}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm font-semibold text-cd-text">{chrono.label}体质</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-500/15 text-indigo-500 dark:text-indigo-300 font-medium">
                  黄金时段 {chrono.peak_period_short}
                </span>
                {chrono.valid_days > 0 && (
                  <span className="text-[10px] text-cd-text-tertiary">
                    基于 {chrono.valid_days} 天数据
                  </span>
                )}
              </div>
              <p className="text-sm text-cd-text-secondary leading-relaxed">{chrono.greeting}</p>
              <div className="flex items-center gap-3 mt-2 text-[11px] text-cd-text-tertiary">
                <span className="flex items-center gap-1">
                  <Clock size={11} />
                  活跃 {chrono.first_active_hour}h - {chrono.last_active_hour}h
                </span>
              </div>
            </div>
            <button
              onClick={() => loadData(true)}
              className="text-cd-text-tertiary hover:text-cd-text transition shrink-0"
              title="刷新"
            >
              <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>
      )}

      {/* 智能建议列表 */}
      {visibleSuggestions.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 px-1">
            <TrendingUp size={13} className="text-cd-green" />
            <span className="text-xs font-medium text-cd-green uppercase tracking-wider">智能建议</span>
            <span className="text-[10px] text-cd-text-tertiary">基于近期行为模式</span>
          </div>
          {visibleSuggestions.map((s, idx) => {
            const priorityColor =
              s.priority === 'high'
                ? 'border-red-200/40 dark:border-red-500/20 bg-red-50/50 dark:bg-red-500/5'
                : s.priority === 'medium'
                  ? 'border-amber-200/40 dark:border-amber-500/20 bg-amber-50/50 dark:bg-amber-500/5'
                  : 'border-cd-border bg-cd-card/50'
            return (
              <div
                key={idx}
                className={`relative rounded-lg border ${priorityColor} p-3 pl-9 transition-all hover:shadow-sm`}
              >
                <span className="absolute left-3 top-3 text-base">{s.icon}</span>
                <button
                  onClick={() => handleDismiss(s.type)}
                  className="absolute top-2 right-2 text-cd-text-tertiary hover:text-cd-text opacity-0 hover:opacity-100 transition"
                  title="忽略"
                >
                  <X size={12} />
                </button>
                <div className="pr-5">
                  <p className="text-sm font-medium text-cd-text mb-0.5">{s.title}</p>
                  <p className="text-xs text-cd-text-secondary leading-relaxed">{s.detail}</p>
                  {s.action && (
                    <p className="text-[11px] text-cd-green mt-1.5 flex items-center gap-0.5">
                      <Sparkles size={10} />
                      {s.action}
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
