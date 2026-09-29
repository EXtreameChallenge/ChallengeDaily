import { useState, useCallback, useEffect } from 'react'
import { Zap, Plus, Trash2, Play, Bell, Brain, FileText, Clock, Activity, AlertTriangle } from 'lucide-react'
import { getRules, createRule, deleteRule, toggleRule, evaluateRules, type Rule, type RuleEvalResult } from '../api/client'
import { RULE_TEMPLATES, type RuleTemplate } from '../data/ruleTemplates'
import { useToast } from '../components/Toast'

const ACTION_ICONS: Record<string, typeof Bell> = {
  notify: Bell,
  ai_advice: Brain,
  auto_report_draft: FileText,
  webhook: Zap,
  start_pomodoro: Play,
}

const TRIGGER_ICONS: Record<string, typeof Clock> = {
  time: Clock,
  pomodoro_complete: Play,
  deep_work: Brain,
  streak_break: AlertTriangle,
  no_diary: FileText,
  week_plan_behind: AlertTriangle,
  meeting_heavy: Activity,
  idle_too_long: Clock,
}

// 模板 trigger_type → 后端 trigger_type 映射
const TRIGGER_TYPE_MAP: Record<string, string> = {
  condition: 'idle_too_long',
  schedule: 'time',
  activity: 'deep_work',
  event: 'pomodoro_complete',
}

// 模板 action_type → 后端 action_type 映射
const ACTION_TYPE_MAP: Record<string, string> = {
  notification: 'notify',
  generate_report: 'auto_report_draft',
}

export default function WorkflowEditor() {
  const [rules, setRules] = useState<Rule[]>([])
  const [triggered, setTriggered] = useState<RuleEvalResult[]>([])
  const [loading, setLoading] = useState(false)
  const [evaluating, setEvaluating] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState<RuleTemplate | null>(null)
  const { toast } = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getRules()
      setRules(data.rules)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreateFromTemplate = async (tpl: RuleTemplate) => {
    try {
      const triggerType = TRIGGER_TYPE_MAP[tpl.trigger_type] || tpl.trigger_type
      const actionType = ACTION_TYPE_MAP[tpl.action_type] || tpl.action_type
      await createRule({
        name: tpl.name,
        description: tpl.description,
        trigger_type: triggerType,
        trigger_params: tpl.trigger_condition,
        action_type: actionType,
        action_params: tpl.action_config,
      })
      toast('success', `已从模板创建规则: ${tpl.name}`)
      setShowTemplates(false)
      load()
    } catch {
      toast('error', '创建规则失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteRule(id)
      setRules(rules.filter(r => r.id !== id))
      toast('success', '规则已删除')
    } catch {
      toast('error', '删除失败')
    }
  }

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
    <div className="max-w-5xl mx-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-cd-text flex items-center gap-2">
            <Zap size={20} className="text-cd-accent" /> 工作流编辑器
          </h1>
          <p className="text-sm text-cd-text-secondary mt-1">
            可视化 IF-THEN 规则编排 · 从模板快速创建 · 拖拽式管理
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowTemplates(!showTemplates)}
            className="flex items-center gap-1 px-3 py-1.5 rounded-2xl text-xs bg-cd-accent/10 text-cd-accent border border-cd-accent/20 hover:bg-cd-accent/20 transition">
            <Plus size={12} /> 从模板创建
          </button>
          <button onClick={handleEvaluate} disabled={evaluating}
            className="flex items-center gap-1 px-3 py-1.5 rounded-2xl text-xs bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition">
            <Play size={12} className={evaluating ? 'animate-spin' : ''} /> 立即评估
          </button>
        </div>
      </div>

      {/* Template Panel */}
      {showTemplates && (
        <div className="bg-cd-bg-card rounded-xl p-5 border border-cd-accent/20 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-cd-text">规则模板库</h2>
            <button onClick={() => setShowTemplates(false)}
              className="text-xs text-cd-text-tertiary hover:text-cd-text">收起</button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {RULE_TEMPLATES.map(tpl => (
              <button key={tpl.id} onClick={() => handleCreateFromTemplate(tpl)}
                className="text-left p-3 rounded-2xl bg-cd-bg-input border border-white/5 hover:border-cd-accent/30 hover:bg-cd-accent/5 transition group">
                <div className="flex items-start gap-2 mb-2">
                  <span className="text-lg">{tpl.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-cd-text group-hover:text-cd-accent transition">{tpl.name}</div>
                    <div className="text-xs text-cd-text-tertiary mt-0.5 line-clamp-2">{tpl.description}</div>
                  </div>
                  <Plus size={14} className="text-cd-text-tertiary group-hover:text-cd-accent flex-shrink-0 mt-0.5" />
                </div>
                {/* R2-4: IF-THEN 可视化预览 */}
                <div className="flex items-center gap-1.5 text-[10px] mt-1.5">
                  <span className="px-1.5 py-0.5 rounded-lg bg-blue-500/10 text-blue-400 font-medium">
                    IF {tpl.trigger_type}
                  </span>
                  <span className="text-cd-text-tertiary">→</span>
                  <span className="px-1.5 py-0.5 rounded-lg bg-cd-accent/10 text-cd-accent font-medium">
                    THEN {tpl.action_type}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Triggered Rules */}
      {triggered.length > 0 && (
        <div className="bg-orange-500/10 border border-orange-400/20 rounded-xl p-4 mb-6">
          <h2 className="text-sm font-semibold text-orange-400 mb-2 flex items-center gap-2">
            <Bell size={14} /> 刚刚触发的规则
          </h2>
          <div className="space-y-2">
            {triggered.map((t, i) => {
              const Icon = ACTION_ICONS[t.action] || Bell
              return (
                <div key={i} className="flex items-start gap-2 bg-orange-500/5 rounded-2xl p-2">
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

      {/* Rules Canvas */}
      <div className="bg-cd-bg-card rounded-xl p-5 border border-white/5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-cd-text">规则画布</h2>
          <span className="text-xs text-cd-text-tertiary">{rules.length} 条规则</span>
        </div>

        {rules.length === 0 ? (
          <div className="text-center py-12">
            <div className="w-16 h-16 rounded-2xl bg-cd-accent/10 flex items-center justify-center mx-auto mb-4">
              <Zap size={28} className="text-cd-accent" />
            </div>
            <h3 className="text-base font-semibold text-cd-text mb-1">创建你的第一条规则</h3>
            <p className="text-sm text-cd-text-tertiary mb-6">自动化你的工作流，从模板开始只需 3 步</p>
            {/* R2-6: 3 步引导 */}
            <div className="flex items-center justify-center gap-4 mb-6 max-w-md mx-auto">
              {[
                { step: 1, label: '选择模板', icon: Plus },
                { step: 2, label: '一键创建', icon: Zap },
                { step: 3, label: '自动运行', icon: Play },
              ].map((s, i) => (
                <div key={s.step} className="flex items-center gap-2">
                  <div className="flex flex-col items-center gap-1.5">
                    <div className="w-10 h-10 rounded-full bg-cd-accent/10 flex items-center justify-center text-cd-accent">
                      <s.icon size={16} />
                    </div>
                    <span className="text-[10px] text-cd-text-tertiary">{s.label}</span>
                  </div>
                  {i < 2 && <div className="text-cd-text-tertiary text-xs">→</div>}
                </div>
              ))}
            </div>
            <button onClick={() => setShowTemplates(true)}
              className="flex items-center gap-1 px-4 py-2 rounded-2xl text-xs bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition mx-auto">
              <Plus size={14} /> 浏览规则模板库
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {rules.map(rule => {
              const ActionIcon = ACTION_ICONS[rule.action_type] || Bell
              const TriggerIcon = TRIGGER_ICONS[rule.trigger_type] || Clock
              return (
                <div key={rule.id}
                  className={`group relative rounded-2xl border p-4 transition ${
                    rule.enabled
                      ? 'bg-cd-bg-input border-white/5 hover:border-cd-accent/20'
                      : 'bg-cd-bg-input/50 border-white/5 opacity-60'
                  }`}>
                  {/* IF-THEN Visual */}
                  <div className="flex items-center gap-3">
                    {/* IF block */}
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                      <div className={`w-8 h-8 rounded-2xl flex items-center justify-center flex-shrink-0 ${
                        rule.enabled ? 'bg-blue-500/10 text-blue-400' : 'bg-white/5 text-cd-text-tertiary'
                      }`}>
                        <TriggerIcon size={14} />
                      </div>
                      <div className="min-w-0">
                        <div className="text-[10px] text-cd-text-tertiary uppercase tracking-wider">IF</div>
                        <div className="text-sm text-cd-text font-medium truncate">{rule.name}</div>
                        <div className="text-xs text-cd-text-tertiary truncate">{rule.description}</div>
                      </div>
                    </div>

                    {/* Arrow */}
                    <div className="text-cd-text-tertiary text-lg flex-shrink-0">→</div>

                    {/* THEN block */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <div className={`w-8 h-8 rounded-2xl flex items-center justify-center ${
                        rule.enabled ? 'bg-cd-accent/10 text-cd-accent' : 'bg-white/5 text-cd-text-tertiary'
                      }`}>
                        <ActionIcon size={14} />
                      </div>
                      <div className="text-xs text-cd-text-secondary">{rule.action_type}</div>
                    </div>

                    {/* Controls */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <label className="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" checked={rule.enabled === 1}
                          onChange={() => handleToggle(rule)} className="sr-only peer" />
                        <div className="w-9 h-5 bg-cd-bg-secondary rounded-full peer peer-checked:bg-cd-accent transition-all relative">
                          <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-all ${
                            rule.enabled ? 'translate-x-4' : ''
                          }`} />
                        </div>
                      </label>
                      <button onClick={() => handleDelete(rule.id)}
                        className="opacity-0 group-hover:opacity-100 text-cd-text-tertiary hover:text-red-400 transition">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {/* Last fired */}
                  {rule.last_fired_at && (
                    <div className="text-[10px] text-cd-text-tertiary mt-2 ml-10">
                      上次触发: {rule.last_fired_at}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="text-xs text-cd-text-tertiary text-center mt-4">
        规则引擎会在后台定期评估 · 触发后执行对应动作（通知/AI建议/自动日报草稿/Webhook推送）
      </div>
    </div>
  )
}
