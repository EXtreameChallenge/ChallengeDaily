import { useState, useEffect } from 'react'
import Modal from './Modal'
import { useToast } from './Toast'
import { updateActivity, CATEGORIES, type Activity } from '../api/client'

interface ActivityEditModalProps {
  open: boolean
  onClose: () => void
  activity: Activity | null
  onSaved?: () => void
}

export default function ActivityEditModal({ open, onClose, activity, onSaved }: ActivityEditModalProps) {
  const toast = useToast()
  const [category, setCategory] = useState('')
  const [summary, setSummary] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open && activity) {
      setCategory(activity.category)
      setSummary(activity.ai_summary || '')
      setSaving(false)
    }
  }, [open, activity])

  const handleSave = async () => {
    if (!activity || saving) return
    setSaving(true)
    try {
      await updateActivity(activity.id, { category, summary })
      toast.success('分类和摘要已更新')
      onSaved?.()
      onClose()
    } catch (err) {
      console.error('保存失败:', err)
      toast.error('保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  const title = activity ? `编辑记录 · ${activity.app_name.replace(/\.exe$/i, '')}` : '编辑记录'

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded-xl text-sm text-cd-text-secondary border border-cd-border hover:bg-cd-hover transition"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex-1 py-2 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      }
    >
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
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">摘要</label>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={4}
          className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50 resize-none"
          placeholder="输入工作摘要..."
        />
      </div>
    </Modal>
  )
}
