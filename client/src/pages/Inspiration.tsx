import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Lightbulb, CheckSquare, Flame, Target, Plus, Check, Loader2,
  Sunrise, BookOpen, Code, Dumbbell, Brain, Moon, Coffee, Droplet,
  PenLine, Music, Globe, Activity, Utensils, Eye,
} from 'lucide-react'
import { createTodo, createHabit, createGoal, getTodayStr, getWeekStart } from '../api/client'
import { useToast } from '../components/Toast'

// ─── 模板类型 ───
type TemplateType = 'todo' | 'habit' | 'goal'

interface TodoTemplate {
  type: 'todo'
  icon: typeof Sunrise
  title: string
  desc: string
  category: string
  target_min: number
  priority: number
  mode: string
}

interface HabitTemplate {
  type: 'habit'
  icon: typeof Sunrise
  title: string
  desc: string
  target_count: number
  period: string
  color: string
}

interface GoalTemplate {
  type: 'goal'
  icon: typeof Sunrise
  title: string
  desc: string
  category: 'personal' | 'work' | 'health' | 'learning' | 'finance'
  timeframe: 'yearly' | 'quarterly' | 'monthly'
}

type Template = TodoTemplate | HabitTemplate | GoalTemplate

// ─── 模板库 ───
const TEMPLATES: { group: string; items: Template[] }[] = [
  {
    group: '待办计划',
    items: [
      { type: 'todo', icon: Sunrise, title: '晨间例行', desc: '整理今日任务清单，规划一天节奏', category: '规划', target_min: 15, priority: 2, mode: 'timer' },
      { type: 'todo', icon: Coffee, title: '深度工作 90 分钟', desc: '不被打扰的专注工作时段', category: '开发', target_min: 90, priority: 1, mode: 'goal' },
      { type: 'todo', icon: BookOpen, title: '学习 1 小时', desc: '阅读技术文档或书籍', category: '学习', target_min: 60, priority: 2, mode: 'goal' },
      { type: 'todo', icon: Code, title: '代码 Review', desc: '审查 PR 或代码质量', category: '开发', target_min: 30, priority: 2, mode: 'timer' },
      { type: 'todo', icon: PenLine, title: '写日报/周报', desc: '总结工作成果与反思', category: '沟通', target_min: 20, priority: 3, mode: 'timer' },
      { type: 'todo', icon: Dumbbell, title: '运动 30 分钟', desc: '健身或户外活动', category: '休息', target_min: 30, priority: 3, mode: 'goal' },
    ],
  },
  {
    group: '习惯养成',
    items: [
      { type: 'habit', icon: Droplet, title: '每日喝水 8 杯', desc: '保持身体水分充足', target_count: 8, period: 'daily', color: '#3b82f6' },
      { type: 'habit', icon: BookOpen, title: '每日阅读 30 分钟', desc: '坚持阅读积累知识', target_count: 1, period: 'daily', color: '#10b981' },
      { type: 'habit', icon: Brain, title: '冥想 10 分钟', desc: '清空大脑，保持专注', target_count: 1, period: 'daily', color: '#8b5cf6' },
      { type: 'habit', icon: Moon, title: '23:00 前入睡', desc: '保证充足睡眠', target_count: 1, period: 'daily', color: '#6366f1' },
      { type: 'habit', icon: Sunrise, title: '早起 7:00', desc: '规律作息开启活力一天', target_count: 1, period: 'daily', color: '#f59e0b' },
      { type: 'habit', icon: Activity, title: '每日运动', desc: '跑步/健身/骑行', target_count: 1, period: 'daily', color: '#ef4444' },
      { type: 'habit', icon: Utensils, title: '健康饮食', desc: '少油少糖多吃蔬果', target_count: 3, period: 'daily', color: '#22c55e' },
      { type: 'habit', icon: Eye, title: '护眼休息', desc: '每 25 分钟远眺一次', target_count: 8, period: 'daily', color: '#06b6d4' },
    ],
  },
  {
    group: '长期目标',
    items: [
      { type: 'goal', icon: BookOpen, title: '年度阅读 24 本书', desc: '每月 2 本，拓宽视野', category: 'learning', timeframe: 'yearly' },
      { type: 'goal', icon: Globe, title: '掌握一门新语言', desc: '达到日常交流水平', category: 'learning', timeframe: 'yearly' },
      { type: 'goal', icon: Code, title: '完成开源项目', desc: '从 0 到 1 构建并发布', category: 'work', timeframe: 'quarterly' },
      { type: 'goal', icon: Dumbbell, title: '减脂 5kg', desc: '三个月内健康减脂', category: 'health', timeframe: 'quarterly' },
      { type: 'goal', icon: Music, title: '学会一种乐器', desc: '吉他/钢琴/尤克里里', category: 'personal', timeframe: 'yearly' },
      { type: 'goal', icon: PenLine, title: '坚持写日记 100 天', desc: '记录生活与反思', category: 'personal', timeframe: 'quarterly' },
    ],
  },
]

const TYPE_CONFIG: Record<TemplateType, { label: string; color: string; icon: typeof Plus; route: string }> = {
  todo: { label: '待办', color: 'text-cd-green', icon: CheckSquare, route: '/todos' },
  habit: { label: '习惯', color: 'text-orange-400', icon: Flame, route: '/habits' },
  goal: { label: '目标', color: 'text-cd-accent', icon: Target, route: '/goals' },
}

export default function Inspiration() {
  const navigate = useNavigate()
  const toast = useToast()
  const [appliedIds, setAppliedIds] = useState<Set<string>>(new Set())
  const [applying, setApplying] = useState<string | null>(null)

  const handleApply = async (tpl: Template, idx: number) => {
    const key = `${tpl.type}-${idx}`
    setApplying(key)
    try {
      if (tpl.type === 'todo') {
        const today = getTodayStr()
        const ws = getWeekStart()
        await createTodo({
          title: tpl.title,
          category: tpl.category,
          mode: tpl.mode,
          target_min: tpl.target_min,
          priority: tpl.priority,
          assigned_date: today,
          week_start: ws,
        })
      } else if (tpl.type === 'habit') {
        await createHabit({
          name: tpl.title,
          target_count: tpl.target_count,
          period: tpl.period,
          color: tpl.color,
        })
      } else {
        const today = getTodayStr()
        const target = new Date()
        if (tpl.timeframe === 'yearly') target.setFullYear(target.getFullYear() + 1)
        else if (tpl.timeframe === 'quarterly') target.setMonth(target.getMonth() + 3)
        else target.setMonth(target.getMonth() + 1)
        await createGoal({
          title: tpl.title,
          description: tpl.desc,
          category: tpl.category,
          timeframe: tpl.timeframe,
          start_date: today,
          target_date: target.toISOString().slice(0, 10),
          status: 'active',
        } as any)
      }
      setAppliedIds(prev => new Set(prev).add(key))
      toast.success(`已添加到${TYPE_CONFIG[tpl.type].label}`)
    } catch {
      toast.error('添加失败，请重试')
    } finally {
      setApplying(null)
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* 顶部 */}
      <div className="flex items-center gap-2 mb-1">
        <div className="w-9 h-9 rounded-xl bg-cd-accent/20 flex items-center justify-center">
          <Lightbulb size={20} className="text-cd-accent" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-cd-text font-display">灵感中心</h1>
          <p className="text-xs text-cd-text-tertiary">精选计划、习惯、目标模板，一键添加到你的计划</p>
        </div>
      </div>

      {/* 模板组 */}
      <div className="mt-6 space-y-8">
        {TEMPLATES.map(group => (
          <div key={group.group}>
            <div className="text-sm font-semibold text-cd-text-secondary mb-3 flex items-center gap-2">
              {group.group}
              <span className="text-xs text-cd-text-tertiary font-normal">({group.items.length})</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {group.items.map((tpl, idx) => {
                const key = `${tpl.type}-${idx}`
                const applied = appliedIds.has(key)
                const isApplying = applying === key
                const TypeIcon = TYPE_CONFIG[tpl.type].icon

                return (
                  <div
                    key={key}
                    className="bg-cd-bg-card rounded-xl p-4 border border-white/5 hover:border-cd-accent/30 transition group"
                  >
                    <div className="flex items-start gap-3">
                      {/* 模板图标 */}
                      <div className="w-10 h-10 rounded-lg bg-cd-bg-input flex items-center justify-center shrink-0">
                        <tpl.icon size={18} className="text-cd-accent" />
                      </div>

                      {/* 内容 */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-sm font-semibold text-cd-text">{tpl.title}</span>
                          <span className={`flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] ${TYPE_CONFIG[tpl.type].color} bg-cd-bg-input`}>
                            <TypeIcon size={9} /> {TYPE_CONFIG[tpl.type].label}
                          </span>
                        </div>
                        <p className="text-xs text-cd-text-tertiary mb-2">{tpl.desc}</p>

                        {/* 属性标签 */}
                        <div className="flex gap-1.5 flex-wrap">
                          {tpl.type === 'todo' && (
                            <>
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-cd-bg-input text-cd-text-secondary">{tpl.category}</span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-cd-bg-input text-cd-text-secondary">{tpl.target_min}min</span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-cd-bg-input text-cd-text-secondary">P{tpl.priority}</span>
                            </>
                          )}
                          {tpl.type === 'habit' && (
                            <>
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-cd-bg-input text-cd-text-secondary">每日 {tpl.target_count} 次</span>
                              <span className="w-2 h-2 rounded-full" style={{ background: tpl.color }} />
                            </>
                          )}
                          {tpl.type === 'goal' && (
                            <>
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-cd-bg-input text-cd-text-secondary">{tpl.category}</span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] bg-cd-bg-input text-cd-text-secondary">
                                {tpl.timeframe === 'yearly' ? '年度' : tpl.timeframe === 'quarterly' ? '季度' : '月度'}
                              </span>
                            </>
                          )}
                        </div>
                      </div>

                      {/* 应用按钮 */}
                      <button
                        onClick={() => handleApply(tpl, idx)}
                        disabled={applied || isApplying}
                        className={`shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition ${
                          applied
                            ? 'bg-cd-green/20 text-cd-green cursor-default'
                            : isApplying
                              ? 'bg-cd-bg-input text-cd-text-tertiary cursor-wait'
                              : 'bg-cd-accent/20 text-cd-accent hover:bg-cd-accent/30 border border-cd-accent/30'
                        }`}
                      >
                        {applied ? (
                          <><Check size={12} /> 已添加</>
                        ) : isApplying ? (
                          <><Loader2 size={12} className="animate-spin" /> 添加中</>
                        ) : (
                          <><Plus size={12} /> 添加</>
                        )}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* 底部提示 */}
      <div className="mt-8 text-center text-xs text-cd-text-tertiary">
        添加后可前往对应页面查看和调整 ·
        <button onClick={() => navigate('/todos')} className="text-cd-green hover:underline ml-1">待办</button> ·
        <button onClick={() => navigate('/habits')} className="text-orange-400 hover:underline ml-1">习惯</button> ·
        <button onClick={() => navigate('/goals')} className="text-cd-accent hover:underline ml-1">目标</button>
      </div>
    </div>
  )
}
