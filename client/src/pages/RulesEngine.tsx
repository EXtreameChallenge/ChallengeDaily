import { useState, useEffect, useCallback } from 'react'
import { Zap, RefreshCw, Bell, Brain, FileText, Play } from 'lucide-react'
import { getRules, toggleRule, evaluateRules, type Rule, type RuleEvalResult } from '../api/client'
import { useToast } from '../components/Toast'

const ACTION_ICONS: Record<string, typeof Bell> = {
  notify: Bell,
  ai_advice: Brain,
  auto_report_draft: FileText,
  webhook: Zap,
  start_pomodoro: Play,
}

export default function RulesEngine() {
  const [rules, setRules] = useState<Rule[]>([])
  const [triggered, setTriggered] = useState<RuleEvalResult[]>([])
  const [loading, setLoading] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const { toast } = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getRules()
      setRules(data.rules)
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleToggle = async (rule: Rule) => {
    try {
      await toggleRule(rule.id, rule.enabled === 0)
      setRules(rules.map(r => r.id === rule.id ? { ...r, enabled: rule.enabled === 0 ? 1 : 0 } : r))
    } catch { toast('error', '更新失败') }
  }

  const handleEvaluate = async () => {
    setEvaluating(true)
    try {
      const result = await evaluateRules()
      setTriggered(result.triggered)
      if (result.count > 0) {
        toast('success', `触发了 ${result.count} 条规则`)
      } else {
        toast('info', '当前无规则触发')
      }
    } catch { toast('error', '评估失败') }
    setEvaluating(false)
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-cd-text flex items-center gap-2">
            <Zap size={20} className="text-cd-accent" /> 工作流规则引擎
          </h1>
          <p className="text-sm text-cd-text-secondary mt-1">IF-THEN 场景触发 · 从自动日报到主动教练</p>
        </div>
        <button onClick={handleEvaluate} disabled={evaluating}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition">
          <RefreshCw size={12} className={evaluating ? 'animate-spin' : ''} /> 立即评估
        </button>
      </div>

      {/* 触发的规则 */}
      {triggered.length > 0 && (
        <div className="bg-orange-500/10 border border-orange-400/20 rounded-xl p-4 mb-6">
          <h2 className="text-sm font-semibold text-orange-400 mb-2 flex items-center gap-2">
            <Bell size={14} /> 刚刚触发的规则
          </h2>
          <div className="space-y-2">
            {triggered.map((t, i) => {
              const Icon = ACTION_ICONS[t.action] || Bell
              return (
                <div key={i} className="flex items-start gap-2 bg-orange-500/5 rounded-lg p-2">
                  <Icon size={14} className="text-orange-400 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <div className="text-sm text-cd-text">{t.message}</div>
                    <div className="text-[10px] text-cd-text-tertiary mt-0.5">
                      {t.rule_name} · 动作: {t.action}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 规则列表 */}
      <div className="bg-cd-bg-card rounded-xl p-5 border border-white/5">
        <h2 className="text-sm font-semibold text-cd-text mb-4">已配置规则</h2>
        {rules.length === 0 ? (
          <div className="text-center py-8 text-cd-text-tertiary text-sm">
            {loading ? '加载中...' : '暂无规则'}
          </div>
        ) : (
          <div className="space-y-2">
            {rules.map(rule => {
              const Icon = ACTION_ICONS[rule.action_type] || Bell
              return (
                <div key={rule.id} className={`flex items-center gap-3 p-3 rounded-lg ${
                  rule.enabled ? 'bg-cd-bg-input' : 'bg-cd-bg-input opacity-50'
                }`}>
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                    rule.enabled ? 'bg-cd-accent/10 text-cd-accent' : 'bg-white/5 text-cd-text-tertiary'
                  }`}>
                    <Icon size={16} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-cd-text font-medium">{rule.name}</div>
                    <div className="text-xs text-cd-text-tertiary">{rule.description}</div>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" checked={rule.enabled === 1}
                      onChange={() => handleToggle(rule)} className="sr-only peer" />
                    <div className="w-9 h-5 bg-cd-bg-secondary rounded-full peer peer-checked:bg-cd-accent transition-all relative">
                      <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-all ${
                        rule.enabled ? 'translate-x-4' : ''
                      }`} />
                    </div>
                  </label>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="text-xs text-cd-text-tertiary text-center mt-4">
        规则引擎会在后台定期评估，触发后执行对应动作（通知/AI建议/自动生成日报草稿）
      </div>
    </div>
  )
}
