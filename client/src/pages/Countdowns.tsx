import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Calendar, Heart, Star } from 'lucide-react'
import { getCountdowns, createCountdown, deleteCountdown, type Countdown } from '../api/client'

const COLORS = ['#7B68EE', '#F0C040', '#22c55e', '#3b82f6', '#ec4899', '#f97316']

function daysUntil(targetDate: string): number {
  const target = new Date(targetDate)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  target.setHours(0, 0, 0, 0)
  return Math.ceil((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
}

export default function Countdowns() {
  const [countdowns, setCountdowns] = useState<Countdown[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ title: '', target_date: '', color: COLORS[0] })

  const load = useCallback(async () => {
    try {
      const { countdowns: data } = await getCountdowns()
      setCountdowns(data)
    } catch {}
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    if (!form.title.trim() || !form.target_date) return
    try {
      await createCountdown({ title: form.title, target_date: form.target_date, color: form.color })
      setForm({ title: '', target_date: '', color: COLORS[0] })
      setShowForm(false)
      load()
    } catch {}
  }

  const handleDelete = async (id: number) => {
    await deleteCountdown(id)
    load()
  }

  const sorted = [...countdowns].sort((a, b) => daysUntil(a.target_date) - daysUntil(b.target_date))

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <Calendar className="text-purple-400" /> 未来计划
        </h1>
        <button onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 bg-purple-500/20 text-purple-300 rounded-lg border border-purple-400/30 hover:bg-purple-500/30 transition">
          <Plus size={18} /> 新建倒数日
        </button>
      </div>

      {showForm && (
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4 space-y-3">
          <input type="text" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
            placeholder="事件标题..." autoFocus
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-4 py-2.5 text-cd-text focus:outline-none focus:border-purple-400/40" />
          <div className="flex gap-3 items-center">
            <input type="date" value={form.target_date} onChange={e => setForm({ ...form, target_date: e.target.value })}
              className="bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-cd-text" />
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
            创建
          </button>
        </div>
      )}

      {sorted.length === 0 ? (
        <div className="text-center py-12 text-cd-text-secondary">
          <Star size={48} className="mx-auto mb-3 opacity-30" />
          <p>暂无倒数日，点击右上角新建</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sorted.map(cd => {
            const days = daysUntil(cd.target_date)
            const isPast = days < 0
            const isToday = days === 0
            return (
              <div key={cd.id} className="bg-cd-bg-card rounded-xl p-4 border border-white/5 relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-1" style={{ backgroundColor: cd.color }} />
                <div className="flex items-center justify-between pl-3">
                  <div>
                    <div className="text-lg font-medium text-cd-text">{cd.title}</div>
                    <div className="text-sm text-cd-text-secondary">{cd.target_date}</div>
                  </div>
                  <div className="text-right">
                    <div className={`text-3xl font-bold ${isToday ? 'text-red-400' : isPast ? 'text-gray-500' : 'text-purple-400'}`}>
                      {isToday ? '今天' : isPast ? `已过${Math.abs(days)}天` : `${days}天`}
                    </div>
                    <button onClick={() => handleDelete(cd.id)} className="text-cd-text-secondary hover:text-red-400 transition mt-1">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
