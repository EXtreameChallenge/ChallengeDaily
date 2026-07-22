import { useState, useEffect, useCallback } from 'react'
import { request } from '../api/client'
import { Sunrise, ChevronDown, ChevronUp, Check, X } from 'lucide-react'
import SchedulePanel from './SchedulePanel'

interface PendingTask {
  id: number
  title: string
}

interface YesterdayReview {
  focus_minutes: number
  tasks_completed: number
  distraction_count: number
}

interface MorningData {
  planned: boolean
  yesterday: YesterdayReview | null
  pending_tasks: PendingTask[]
  schedule?: Array<{ time_start: string; time_end: string; task: string; type: string }>
}

export default function MorningRitual() {
  const [data, setData] = useState<MorningData | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [intention, setIntention] = useState('')
  const [focusGoal, setFocusGoal] = useState(4)
  const [taskActions, setTaskActions] = useState<Record<number, 'carry' | 'drop'>>({})
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  const hour = new Date().getHours()
  const inWindow = hour >= 6 && hour < 12

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await request('/api/ritual/morning') as MorningData
      setData(res)
      if (res.planned) setDone(true)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (inWindow) load()
  }, [inWindow, load])

  if (!inWindow) return null
  if (loading) {
    return (
      <div className="bg-cd-bg-card border border-cd-border rounded-xl p-4 text-xs text-cd-text-tertiary">
        加载晨间规划...
      </div>
    )
  }
  if (!data || done) return null

  const setTaskAction = (id: number, action: 'carry' | 'drop') => {
    setTaskActions((prev) => ({ ...prev, [id]: action }))
  }

  const handleSubmit = async (adopt: boolean) => {
    setSubmitting(true)
    try {
      await request('/api/ritual/morning/plan', {
        method: 'POST',
        body: JSON.stringify({
          intention,
          focus_goal: focusGoal,
          task_actions: taskActions,
          adopt_schedule: adopt,
        }),
      })
      setDone(true)
    } catch {
      // silent
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="bg-cd-bg-card border border-cd-border rounded-xl overflow-hidden">
      <button
        onClick={() => setCollapsed((c) => !c)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-cd-hover transition-colors"
      >
        <div className="flex items-center gap-2">
          <Sunrise size={16} className="text-cd-green" />
          <span className="text-sm font-medium text-cd-text">晨间规划</span>
        </div>
        {collapsed ? (
          <ChevronDown size={16} className="text-cd-text-tertiary" />
        ) : (
          <ChevronUp size={16} className="text-cd-text-tertiary" />
        )}
      </button>

      {!collapsed && (
        <div className="px-4 pb-4 space-y-4">
          {data.yesterday && (
            <div>
              <div className="text-xs text-cd-text-secondary mb-2">昨日回顾</div>
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-cd-bg-secondary rounded-lg px-3 py-2 text-center">
                  <div className="text-base font-semibold text-cd-text">
                    {data.yesterday.focus_minutes}
                  </div>
                  <div className="text-[10px] text-cd-text-tertiary">专注分钟</div>
                </div>
                <div className="bg-cd-bg-secondary rounded-lg px-3 py-2 text-center">
                  <div className="text-base font-semibold text-cd-text">
                    {data.yesterday.tasks_completed}
                  </div>
                  <div className="text-[10px] text-cd-text-tertiary">完成任务</div>
                </div>
                <div className="bg-cd-bg-secondary rounded-lg px-3 py-2 text-center">
                  <div className="text-base font-semibold text-cd-text">
                    {data.yesterday.distraction_count}
                  </div>
                  <div className="text-[10px] text-cd-text-tertiary">分心次数</div>
                </div>
              </div>
            </div>
          )}

          {data.pending_tasks.length > 0 && (
            <div>
              <div className="text-xs text-cd-text-secondary mb-2">未完成任务</div>
              <div className="space-y-1.5">
                {data.pending_tasks.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between bg-cd-bg-secondary rounded-lg px-3 py-2"
                  >
                    <span className="text-xs text-cd-text flex-1 min-w-0 truncate">
                      {task.title}
                    </span>
                    <div className="flex gap-1 shrink-0 ml-2">
                      <button
                        onClick={() => setTaskAction(task.id, 'carry')}
                        className={
                          'px-2 py-0.5 text-[10px] rounded border transition-colors ' +
                          (taskActions[task.id] === 'carry'
                            ? 'bg-cd-green/20 text-cd-green border-cd-green/40'
                            : 'text-cd-text-secondary border-cd-border hover:text-cd-text')
                        }
                      >
                        顺延
                      </button>
                      <button
                        onClick={() => setTaskAction(task.id, 'drop')}
                        className={
                          'px-2 py-0.5 text-[10px] rounded border transition-colors ' +
                          (taskActions[task.id] === 'drop'
                            ? 'bg-red-500/20 text-red-400 border-red-500/40'
                            : 'text-cd-text-secondary border-cd-border hover:text-cd-text')
                        }
                      >
                        放弃
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="text-xs text-cd-text-secondary mb-2">AI 排程建议</div>
            <SchedulePanel initialSchedule={data.schedule} />
          </div>

          <div>
            <div className="text-xs text-cd-text-secondary mb-2">今日意图</div>
            <input
              type="text"
              value={intention}
              onChange={(e) => setIntention(e.target.value)}
              placeholder="今天最重要的一件事..."
              className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-xs text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-green/50"
            />
          </div>

          <div>
            <div className="text-xs text-cd-text-secondary mb-2">
              专注目标：{focusGoal} 个番茄
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setFocusGoal((g) => Math.max(1, g - 1))}
                className="w-7 h-7 flex items-center justify-center rounded-lg bg-cd-bg-secondary border border-cd-border text-cd-text-secondary hover:text-cd-text transition-colors"
              >
                -
              </button>
              <div className="flex-1 flex gap-1">
                {Array.from({ length: Math.min(focusGoal, 12) }).map((_, i) => (
                  <div key={i} className="flex-1 h-2 rounded-full bg-cd-green/40" />
                ))}
              </div>
              <button
                onClick={() => setFocusGoal((g) => Math.min(12, g + 1))}
                className="w-7 h-7 flex items-center justify-center rounded-lg bg-cd-bg-secondary border border-cd-border text-cd-text-secondary hover:text-cd-text transition-colors"
              >
                +
              </button>
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={() => handleSubmit(true)}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium bg-cd-green/15 text-cd-green rounded-lg border border-cd-green/25 hover:bg-cd-green/25 transition-colors disabled:opacity-50"
            >
              <Check size={14} /> 采纳安排
            </button>
            <button
              onClick={() => handleSubmit(false)}
              disabled={submitting}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs text-cd-text-secondary bg-cd-bg-secondary rounded-lg border border-cd-border hover:text-cd-text transition-colors disabled:opacity-50"
            >
              <X size={14} /> 跳过规划
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
