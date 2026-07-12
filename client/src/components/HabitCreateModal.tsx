import { useState, useEffect, useRef } from 'react'
import Modal from './Modal'
import { useToast } from './Toast'
import { createHabit } from '../api/client'

const COLORS = ['#7B68EE', '#F0C040', '#22c55e', '#3b82f6', '#ec4899', '#f97316']

interface HabitCreateModalProps {
  open: boolean
  onClose: () => void
  onCreated?: () => void
}

export default function HabitCreateModal({ open, onClose, onCreated }: HabitCreateModalProps) {
  const toast = useToast()
  const [name, setName] = useState('')
  const [targetCount, setTargetCount] = useState(1)
  const [color, setColor] = useState(COLORS[0])
  const [saving, setSaving] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setName('')
      setTargetCount(1)
      setColor(COLORS[0])
      setSaving(false)
      setTimeout(() => nameRef.current?.focus(), 100)
    }
  }, [open])

  const handleCreate = async () => {
    if (!name.trim() || saving) return
    setSaving(true)
    try {
      await createHabit({ name: name.trim(), target_count: targetCount, color })
      toast.success('习惯已创建')
      onCreated?.()
      onClose()
    } catch (err) {
      console.error('创建习惯失败:', err)
      toast.error('创建失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新建习惯"
      footer={
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-xl text-sm text-cd-text-secondary border border-cd-border hover:bg-cd-hover transition"
          >
            取消
          </button>
          <button
            onClick={handleCreate}
            disabled={!name.trim() || saving}
            className="flex-1 py-2 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? '创建中...' : '创建习惯'}
          </button>
        </div>
      }
    >
      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">习惯名称</label>
        <input
          ref={nameRef}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          placeholder="例如：每天喝水 8 杯"
          className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">每日目标次数</label>
        <div className="flex items-center gap-1 bg-cd-bg-input border border-cd-border rounded-lg px-2 py-1.5 w-32">
          <button
            onClick={() => setTargetCount(Math.max(1, targetCount - 1))}
            className="w-6 h-6 flex items-center justify-center rounded bg-cd-hover text-cd-text hover:bg-cd-accent/20 transition text-sm font-bold"
          >
            −
          </button>
          <span className="flex-1 text-center text-lg font-bold text-cd-text tabular-nums">{targetCount}</span>
          <button
            onClick={() => setTargetCount(Math.min(10, targetCount + 1))}
            className="w-6 h-6 flex items-center justify-center rounded bg-cd-hover text-cd-text hover:bg-cd-accent/20 transition text-sm font-bold"
          >
            +
          </button>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">标记颜色</label>
        <div className="flex gap-2">
          {COLORS.map((c) => (
            <button
              key={c}
              onClick={() => setColor(c)}
              className={`w-7 h-7 rounded-full border-2 transition ${color === c ? 'scale-110 border-white' : 'border-transparent'}`}
              style={{ backgroundColor: c }}
            />
          ))}
        </div>
      </div>
    </Modal>
  )
}
