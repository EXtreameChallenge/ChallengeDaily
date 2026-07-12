import { useState, useEffect, useRef } from 'react'
import Modal from './Modal'
import { useToast } from './Toast'
import { createActivity, CATEGORIES } from '../api/client'
import dayjs from 'dayjs'

interface ActivityCreateModalProps {
  open: boolean
  onClose: () => void
  onCreated?: () => void
}

export default function ActivityCreateModal({ open, onClose, onCreated }: ActivityCreateModalProps) {
  const toast = useToast()
  const [time, setTime] = useState(dayjs().format('YYYY-MM-DDTHH:mm'))
  const [category, setCategory] = useState('开发')
  const [appName, setAppName] = useState('')
  const [summary, setSummary] = useState('')
  const [duration, setDuration] = useState(30)
  const [saving, setSaving] = useState(false)
  const timeRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setTime(dayjs().format('YYYY-MM-DDTHH:mm'))
      setCategory('开发')
      setAppName('')
      setSummary('')
      setDuration(30)
      setSaving(false)
      setTimeout(() => timeRef.current?.focus(), 100)
    }
  }, [open])

  const handleCreate = async () => {
    if (!category || !time || saving) return
    setSaving(true)
    try {
      const timestamp = dayjs(time).format('YYYY-MM-DD HH:mm:ss')
      await createActivity({
        timestamp,
        category,
        summary: summary || undefined,
        app_name: appName || undefined,
        duration_min: duration,
      })
      toast.success('时间条目已补录')
      onCreated?.()
      onClose()
    } catch (err) {
      console.error('补录失败:', err)
      toast.error('补录失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="手动补录时间条目"
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
            disabled={!category || !time || saving}
            className="flex-1 py-2 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? '保存中...' : '保存补录'}
          </button>
        </div>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">时间</label>
          <input
            ref={timeRef}
            type="datetime-local"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-accent/50"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">时长（分钟）</label>
          <input
            type="number"
            value={duration}
            onChange={(e) => setDuration(Math.max(5, parseInt(e.target.value) || 30))}
            min={5}
            max={480}
            className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-accent/50"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">分类</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-accent/50"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">应用名称（可选）</label>
          <input
            type="text"
            value={appName}
            onChange={(e) => setAppName(e.target.value)}
            placeholder="如：微信、邮件..."
            className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">工作摘要</label>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={3}
          className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50 resize-none"
          placeholder="描述你在这段时间做了什么..."
        />
      </div>
    </Modal>
  )
}
