import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Flame, Check } from 'lucide-react'
import { getHabits, createHabit, logHabit, deleteHabit, type Habit, type HabitLog } from '../api/client'

const COLORS = ['#7B68EE', '#F0C040', '#22c55e', '#3b82f6', '#ec4899', '#f97316']

export default function Habits() {
  const [habits, setHabits] = useState<Habit[]>([])
  const [logs, setLogs] = useState<HabitLog[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', target_count: 1, color: COLORS[0] })

  const load = useCallback(async () => {
    try {
      const { habits: h, logs: l } = await getHabits()
      setHabits(h)
      setLogs(l)
    } catch {}
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    if (!form.name.trim()) return
    await createHabit({ name: form.name, target_count: form.target_count, color: form.color })
    setForm({ name: '', target_count: 1, color: COLORS[0] })
    setShowForm(false)
    load()
  }

  const handleLog = async (habitId: number) => {
    await logHabit(habitId)
    load()
  }

  const handleDelete = async (id: number) => {
    await deleteHabit(id)
    load()
  }

  const today = new Date().toISOString().substring(0, 10)
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
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 bg-purple-500/20 text-purple-300 rounded-lg border border-purple-400/30 hover:bg-purple-500/30 transition">
          <Plus size={18} /> 新建习惯
        </button>
      </div>

      {showForm && (
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4 space-y-3">
          <input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
            placeholder="习惯名称..." autoFocus
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-4 py-2.5 text-cd-text focus:outline-none focus:border-purple-400/40" />
          <div className="flex gap-3 items-center">
            <div className="flex items-center gap-2">
              <span className="text-sm text-cd-text-secondary">每日目标</span>
              <input type="number" value={form.target_count} min="1" max="10"
                onChange={e => setForm({ ...form, target_count: parseInt(e.target.value) || 1 })}
                className="w-16 bg-cd-bg-input border border-white/5 rounded-lg px-2 py-2 text-cd-text text-center" />
            </div>
            <div className="flex gap-1">
              {COLORS.map(c => (
                <button key={c} onClick={() => setForm({ ...form, color: c })}
                  className={`w-6 h-6 rounded-full border-2 transition ${form.color === c ? 'scale-125 border-white' : 'border-transparent'}`}
                  style={{ backgroundColor: c }} />
              ))}
            </div>
          </div>
          <button onClick={handleCreate}
            className="w-full py-2.5 bg-purple-500/20 text-purple-300 rounded-lg border border-purple-400/30 hover:bg-purple-500/30 transition font-medium">
            创建习惯
          </button>
        </div>
      )}

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
                      completed ? 'bg-green-500/20 text-green-400' : 'bg-purple-500/20 text-purple-300 hover:bg-purple-500/30'
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
