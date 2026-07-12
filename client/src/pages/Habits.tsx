import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Flame, Check } from 'lucide-react'
import { getHabits, logHabit, deleteHabit, getTodayStr, type Habit, type HabitLog } from '../api/client'
import { useToast } from '../components/Toast'
import HabitCreateModal from '../components/HabitCreateModal'

export default function Habits() {
  const [habits, setHabits] = useState<Habit[]>([])
  const [logs, setLogs] = useState<HabitLog[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const toast = useToast()

  const load = useCallback(async () => {
    try {
      const { habits: h, logs: l } = await getHabits()
      setHabits(h)
      setLogs(l)
    } catch {
      toast.error('加载习惯数据失败')
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleLog = async (habitId: number) => {
    try {
      await logHabit(habitId)
      load()
    } catch {
      toast.error('打卡失败')
    }
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定删除该习惯？相关打卡记录不会删除。')) return
    try {
      await deleteHabit(id)
      toast.success('习惯已删除')
      load()
    } catch {
      toast.error('删除失败，请重试')
    }
  }

  const today = getTodayStr()
  const todayLogs = logs.filter(l => l.log_date === today)
  const todayLogMap = new Map(todayLogs.map(l => [l.habit_id, l.count]))

  // 计算连续天数
  const getStreak = (habitId: number) => {
    const habitLogs = logs.filter(l => l.habit_id === habitId).sort((a, b) => b.log_date.localeCompare(a.log_date))
    let streak = 0
    let checkDate = new Date()
    for (const log of habitLogs) {
      const logDate = new Date(log.log_date)
      const diffDays = Math.floor((checkDate.getTime() - logDate.getTime()) / (1000 * 60 * 60 * 24))
      if (diffDays <= 1) {
        streak++
        checkDate = logDate
      } else break
    }
    return streak
  }

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <Flame className="text-orange-400" /> 习惯追踪
        </h1>
        <button onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 transition">
          <Plus size={18} /> 新建习惯
        </button>
      </div>

      <HabitCreateModal open={modalOpen} onClose={() => setModalOpen(false)} onCreated={load} />

      {habits.length === 0 ? (
        <div className="text-center py-12 text-cd-text-secondary">
          <Flame size={48} className="mx-auto mb-3 opacity-30" />
          <p>暂无习惯，点击右上角新建</p>
        </div>
      ) : (
        <div className="space-y-3">
          {habits.map(habit => {
            const todayCount = todayLogMap.get(habit.id) || 0
            const streak = getStreak(habit.id)
            const completed = todayCount >= habit.target_count
            return (
              <div key={habit.id} className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: habit.color }} />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-cd-text font-medium">{habit.name}</span>
                      {streak > 0 && <span className="text-xs text-orange-400 flex items-center gap-1"><Flame size={12} />{streak}天</span>}
                    </div>
                    <div className="text-xs text-cd-text-secondary mt-0.5">每日目标 {habit.target_count} 次 · 今日 {todayCount}/{habit.target_count}</div>
                  </div>
                  <button onClick={() => handleLog(habit.id)} disabled={completed}
                    className={`w-10 h-10 rounded-full flex items-center justify-center transition ${
                      completed ? 'bg-green-500/20 text-green-400' : 'bg-cd-accent/20 text-cd-accent hover:bg-cd-accent/30'
                    } disabled:opacity-60`}>
                    <Check size={20} />
                  </button>
                  <button onClick={() => handleDelete(habit.id)} className="text-cd-text-secondary hover:text-red-400 transition">
                    <Trash2 size={16} />
                  </button>
                </div>
                {habit.target_count > 1 && (
                  <div className="mt-2 flex gap-1">
                    {Array.from({ length: habit.target_count }).map((_, i) => (
                      <div key={i} className={`flex-1 h-1.5 rounded-full ${i < todayCount ? '' : 'bg-cd-bg-input'}`}
                        style={{ backgroundColor: i < todayCount ? habit.color : undefined }} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
