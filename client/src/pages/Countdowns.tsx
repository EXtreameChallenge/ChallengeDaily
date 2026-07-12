import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Calendar, Star } from 'lucide-react'
import { getCountdowns, deleteCountdown, type Countdown } from '../api/client'
import { useToast } from '../components/Toast'
import CountdownCreateModal from '../components/CountdownCreateModal'

function daysUntil(targetDate: string): number {
  const target = new Date(targetDate)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  target.setHours(0, 0, 0, 0)
  return Math.ceil((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
}

export default function Countdowns() {
  const [countdowns, setCountdowns] = useState<Countdown[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const toast = useToast()

  const load = useCallback(async () => {
    try {
      const { countdowns: data } = await getCountdowns()
      setCountdowns(data)
    } catch (e) {
      toast.error('加载失败，请重试')
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定删除该倒计时？')) return
    try {
      await deleteCountdown(id)
      load()
    } catch (e) {
      toast.error('删除失败，请重试')
    }
  }

  const sorted = [...countdowns].sort((a, b) => daysUntil(a.target_date) - daysUntil(b.target_date))

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <Calendar className="text-cd-accent" /> 未来计划
        </h1>
        <button onClick={() => setModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 transition">
          <Plus size={18} /> 新建倒数日
        </button>
      </div>

      <CountdownCreateModal open={modalOpen} onClose={() => setModalOpen(false)} onCreated={load} />

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
                    <div className={`text-3xl font-bold ${isToday ? 'text-red-400' : isPast ? 'text-gray-500' : 'text-cd-accent'}`}>
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
