import { useState, useEffect, useRef } from 'react'
import Modal from './Modal'
import { useToast } from './Toast'
import { addWebhook } from '../api/client'

interface WebhookCreateModalProps {
  open: boolean
  onClose: () => void
  onCreated?: () => void
}

const WH_TYPE_INFO: Record<string, { label: string; color: string; desc: string }> = {
  feishu: { label: '飞书', color: '#3370FF', desc: '飞书群机器人 Webhook' },
  dingtalk: { label: '钉钉', color: '#0089FF', desc: '钉钉群自定义机器人' },
  wecom: { label: '企业微信', color: '#07C160', desc: '企业微信群机器人' },
  custom: { label: '自定义', color: 'var(--cd-text-tertiary)', desc: '自定义 HTTP Webhook' },
}

export default function WebhookCreateModal({ open, onClose, onCreated }: WebhookCreateModalProps) {
  const toast = useToast()
  const [type, setType] = useState<'feishu' | 'dingtalk' | 'wecom' | 'custom'>('feishu')
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [saving, setSaving] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setType('feishu')
      setName('')
      setUrl('')
      setSaving(false)
      setTimeout(() => nameRef.current?.focus(), 100)
    }
  }, [open])

  const handleCreate = async () => {
    if (!url.trim() || saving) return
    setSaving(true)
    try {
      await addWebhook({
        url: url.trim(),
        name: name.trim() || undefined,
        type,
        events: ['daily_report'],
      })
      toast.success('Webhook 已添加')
      onCreated?.()
      onClose()
    } catch (err) {
      console.error('添加 Webhook 失败:', err)
      toast.error('添加失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="添加 Webhook 推送"
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
            disabled={!url.trim() || saving}
            className="flex-1 py-2 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? '添加中...' : '添加推送'}
          </button>
        </div>
      }
    >
      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">推送类型</label>
        <div className="flex gap-2">
          {Object.entries(WH_TYPE_INFO).map(([key, info]) => (
            <button
              key={key}
              onClick={() => setType(key as any)}
              className={`flex-1 py-2 rounded-lg text-xs font-medium border transition ${
                type === key
                  ? 'bg-cd-accent/15 text-cd-accent border-cd-accent/30'
                  : 'bg-cd-bg-input text-cd-text border-cd-border hover:bg-cd-hover'
              }`}
            >
              {info.label}
            </button>
          ))}
        </div>
        <p className="mt-1.5 text-xs text-cd-text-tertiary">{WH_TYPE_INFO[type].desc}</p>
      </div>

      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">名称（可选）</label>
        <input
          ref={nameRef}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={`${WH_TYPE_INFO[type].label}群机器人`}
          className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">Webhook URL</label>
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
          className="w-full bg-cd-bg-input border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:border-cd-accent/50 font-mono"
        />
      </div>
    </Modal>
  )
}
