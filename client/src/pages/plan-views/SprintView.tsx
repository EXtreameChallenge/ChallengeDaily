import { useState, useEffect } from 'react'
import { Flame, TrendingDown, CheckCircle, Clock, AlertCircle, Target, Edit3, Check, X } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, BarChart, Bar, Cell } from 'recharts'
import { request } from '../../api/client'
import { WEEKDAY_LABELS, fmtDate } from './weekPlanUtils'

interface SprintData {
  week_start: string
  total_tasks: number
  completed_tasks: number
  remaining_tasks: number
  completion_rate: number
  burndown: { date: string; ideal: number; actual: number | null }[]
  daily_completion: { date: string; total: number; completed: number }[]
}

interface SprintViewProps {
  weekStart: string
}

export default function SprintView({ weekStart }: SprintViewProps) {
  const [data, setData] = useState<SprintData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // R2-3: Sprint 目标设定
  const [goalText, setGoalText] = useState('')
  const [goalEditing, setGoalEditing] = useState(false)
  const [goalSaving, setGoalSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(null)
    request(`/api/week-plan/sprint/${weekStart}`)
      .then((d: unknown) => setData(d as SprintData))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
    // R2-3: 加载 Sprint 目标
    request(`/api/week-plan/sprint-goal/${weekStart}`)
      .then((d: unknown) => { const r = d as { goal_text: string }; setGoalText(r.goal_text || '') })
      .catch(() => { setGoalText('') })
  }, [weekStart])

  const handleSaveGoal = async () => {
    if (!goalText.trim()) return
    setGoalSaving(true)
    try {
      await request(`/api/week-plan/sprint-goal/${weekStart}`, { method: 'POST', body: JSON.stringify({ goal_text: goalText }) })
      setGoalEditing(false)
    } catch {
      // silent
    }
    setGoalSaving(false)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-cd-text-tertiary text-sm">加载 Sprint 数据...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-red-400 text-sm flex items-center gap-2">
          <AlertCircle size={16} /> {error}
        </div>
      </div>
    )
  }

  if (!data) return null

  // R2-3: Sprint 目标卡片
  const renderSprintGoal = () => {
    if (goalEditing) {
      return (
        <div className="bg-cd-bg-card rounded-xl p-4 border border-cd-accent/20 mb-4">
          <div className="flex items-center gap-2 mb-2">
            <Target size={14} className="text-cd-accent" />
            <span className="text-sm font-semibold text-cd-text">Sprint 目标</span>
          </div>
          <textarea
            value={goalText}
            onChange={(e) => setGoalText(e.target.value)}
            placeholder="本周 Sprint 要达成的目标..."
            className="w-full bg-cd-bg-input text-cd-text text-sm rounded-2xl p-2.5 border border-cd-border focus:border-cd-accent/30 outline-none resize-none"
            rows={2}
            autoFocus
          />
          <div className="flex items-center gap-2 mt-2">
            <button onClick={handleSaveGoal} disabled={goalSaving || !goalText.trim()}
              className="flex items-center gap-1 px-2.5 py-1 rounded-2xl text-xs bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 disabled:opacity-30 transition">
              <Check size={12} /> {goalSaving ? '保存中...' : '保存'}
            </button>
            <button onClick={() => { setGoalEditing(false); }} 
              className="flex items-center gap-1 px-2.5 py-1 rounded-2xl text-xs text-cd-text-tertiary hover:text-cd-text transition">
              <X size={12} /> 取消
            </button>
          </div>
        </div>
      )
    }
    return (
      <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4 group">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2 flex-1 min-w-0">
            <Target size={14} className="text-cd-accent mt-0.5 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs text-cd-text-tertiary mb-0.5">Sprint 目标</div>
              {goalText ? (
                <div className="text-sm text-cd-text whitespace-pre-wrap">{goalText}</div>
              ) : (
                <div className="text-sm text-cd-text-tertiary italic">点击设置本周 Sprint 目标</div>
              )}
            </div>
          </div>
          <button onClick={() => setGoalEditing(true)}
            className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-cd-text-tertiary hover:text-cd-accent transition shrink-0">
            <Edit3 size={12} />
          </button>
        </div>
      </div>
    )
  }

  const rate = data.completion_rate
  const rateColor = rate >= 80 ? 'text-green-400' : rate >= 50 ? 'text-yellow-400' : 'text-red-400'
  const rateBg = rate >= 80 ? 'bg-green-500/10 border-green-500/20' : rate >= 50 ? 'bg-yellow-500/10 border-yellow-500/20' : 'bg-red-500/10 border-red-500/20'

  // 准备燃尽图数据
  const burndownData = data.burndown.map((b, i) => ({
    day: WEEKDAY_LABELS[i] || b.date,
    ideal: b.ideal,
    actual: b.actual,
  }))

  // 准备每日完成数据
  const dailyData = data.daily_completion.map((d, i) => ({
    day: WEEKDAY_LABELS[i] || d.date,
    completed: d.completed,
    remaining: d.total - d.completed,
  }))

  return (
    <div className="space-y-4">
      {/* R2-3: Sprint 目标 */}
      {renderSprintGoal()}

      {/* Sprint 概要卡片 */}
      <div className="grid grid-cols-4 gap-3">
        <div className={`rounded-xl p-4 border ${rateBg}`}>
          <div className="flex items-center gap-2 mb-1">
            <Flame size={14} className="text-cd-accent" />
            <span className="text-xs text-cd-text-tertiary">完成率</span>
          </div>
          <div className={`text-2xl font-bold ${rateColor}`}>{rate.toFixed(1)}%</div>
        </div>
        <div className="rounded-xl p-4 border border-white/5 bg-cd-bg-card">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle size={14} className="text-green-400" />
            <span className="text-xs text-cd-text-tertiary">已完成</span>
          </div>
          <div className="text-2xl font-bold text-cd-text">{data.completed_tasks}</div>
        </div>
        <div className="rounded-xl p-4 border border-white/5 bg-cd-bg-card">
          <div className="flex items-center gap-2 mb-1">
            <Clock size={14} className="text-yellow-400" />
            <span className="text-xs text-cd-text-tertiary">剩余</span>
          </div>
          <div className="text-2xl font-bold text-cd-text">{data.remaining_tasks}</div>
        </div>
        <div className="rounded-xl p-4 border border-white/5 bg-cd-bg-card">
          <div className="flex items-center gap-2 mb-1">
            <TrendingDown size={14} className="text-blue-400" />
            <span className="text-xs text-cd-text-tertiary">总任务</span>
          </div>
          <div className="text-2xl font-bold text-cd-text">{data.total_tasks}</div>
        </div>
      </div>

      {/* 燃尽图 */}
      <div className="bg-cd-bg-card rounded-xl p-5 border border-white/5">
        <h3 className="text-sm font-semibold text-cd-text mb-4">燃尽图 (Burndown Chart)</h3>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={burndownData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="day" tick={{ fontSize: 11, fill: 'var(--cd-text-tertiary)' }} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--cd-text-tertiary)' }} allowDecimals={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--cd-bg-card)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                fontSize: '12px',
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="ideal" stroke="#6b7280" strokeDasharray="5 5" name="理想线" dot={false} />
            <Line type="monotone" dataKey="actual" stroke="#10b981" strokeWidth={2} name="实际剩余" dot={{ r: 4 }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* 每日完成分布 */}
      <div className="bg-cd-bg-card rounded-xl p-5 border border-white/5">
        <h3 className="text-sm font-semibold text-cd-text mb-4">每日任务完成分布</h3>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={dailyData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="day" tick={{ fontSize: 11, fill: 'var(--cd-text-tertiary)' }} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--cd-text-tertiary)' }} allowDecimals={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--cd-bg-card)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                fontSize: '12px',
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="completed" stackId="a" fill="#10b981" name="已完成" radius={[0, 0, 0, 0]} />
            <Bar dataKey="remaining" stackId="a" fill="#3b82f6" name="未完成" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 进度条 */}
      <div className="bg-cd-bg-card rounded-xl p-5 border border-white/5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-cd-text-secondary">Sprint 进度</span>
          <span className="text-sm font-semibold text-cd-text">{data.completed_tasks}/{data.total_tasks}</span>
        </div>
        <div className="h-3 bg-cd-bg-secondary rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              rate >= 80 ? 'bg-green-500' : rate >= 50 ? 'bg-yellow-500' : 'bg-red-500'
            }`}
            style={{ width: `${rate}%` }}
          />
        </div>
        <div className="text-xs text-cd-text-tertiary mt-2 text-center">
          {data.remaining_tasks > 0
            ? `还有 ${data.remaining_tasks} 个任务待完成`
            : '🎉 所有任务已完成！'}
        </div>
      </div>
    </div>
  )
}
