import { useState, useEffect, useRef } from 'react'
import Modal from './Modal'
import { useToast } from './Toast'
import { createCountdown } from '../api/client'

const COLORS = ['#7B68EE', '#F0C040', '#22c55e', '#3b82f6', '#ec4899', '#f97316']

interface CountdownCreateModalProps {
  open: boolean
  onClose: () => void
  onCreated?: () => void
}

export default function CountdownCreateModal({ open, onClose, onCreated }: CountdownCreateModalProps) {
  const toast = useToast()
  const [title, setTitle] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [color, setColor] = useState(COLORS[0])
  const [saving, setSaving] = useState(false)
  const titleRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setTitle('')
      setTargetDate('')
      setColor(COLORS[0])
      setSaving(false)
      setTimeout(() => titleRef.current?.focus(), 100)
    }
  }, [open])

  const handleCreate = async () => {
    if (!title.trim() || !targetDate || saving) return
    setSaving(true)
    try {
      await createCountdown({ title: title.trim(), target_date: targetDate, color })
      toast.success('倒数日已创建')
      onCreated?.()
      onClose()
    } catch (err) {
      console.error('创建倒数日失败:', err)
      toast.error('操作失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="新建倒数日"
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
            disabled={!title.trim() || !targetDate || saving}
            className="flex-1 py-2 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? '创建中...' : '创建倒数日'}
          </button>
        </div>
      }
    >
      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">事件标题</label>
        <input
          ref={titleRef}
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          placeholder="例如：项目上线"
          className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50"
        />
      </div>

      <div className="flex gap-4">
        <div className="flex-1">
          <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">目标日期</label>
          <input
            type="date"
            value={targetDate}
            onChange={(e) => setTargetDate(e.target.value)}
            className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-accent/50"
          />
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
      </div>
    </Modal>
  )
}
