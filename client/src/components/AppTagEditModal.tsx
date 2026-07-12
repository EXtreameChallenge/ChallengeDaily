import { useState, useEffect } from 'react'
import { Plus, X, Trash2, Save } from 'lucide-react'
import Modal from './Modal'
import { useToast } from './Toast'
import { updateAppRule, deleteAppRule, CATEGORIES, CATEGORY_COLORS, type AppCategoryRule } from '../api/client'

interface AppInfo {
  app_name: string
  rule?: AppCategoryRule
}

interface AppTagEditModalProps {
  open: boolean
  onClose: () => void
  app: AppInfo | null
  onSaved?: () => void
}

export default function AppTagEditModal({ open, onClose, app, onSaved }: AppTagEditModalProps) {
  const toast = useToast()
  const [draft, setDraft] = useState<Partial<AppCategoryRule>>({
    display_name: '',
    primary_category: '',
    tags: [],
    window_rules: {},
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open && app) {
      setDraft({
        display_name: app.rule?.display_name || app.app_name.replace(/\.exe$/i, ''),
        primary_category: app.rule?.primary_category || '',
        tags: app.rule?.tags ? [...app.rule.tags] : [],
        window_rules: app.rule?.window_rules ? { ...app.rule.window_rules } : {},
      })
      setSaving(false)
    }
  }, [open, app])

  const toggleTag = (cat: string) => {
    setDraft((prev) => {
      const current = prev.tags || []
      const exists = current.includes(cat)
      const tags = exists ? current.filter((t) => t !== cat) : [...current, cat]
      return { ...prev, tags }
    })
  }

  const setPrimary = (cat: string) => {
    setDraft((prev) => ({
      ...prev,
      primary_category: cat,
      tags: prev.tags?.includes(cat) ? prev.tags : [cat, ...(prev.tags || [])],
    }))
  }

  const addWindowRule = () => {
    setDraft((prev) => ({
      ...prev,
      window_rules: { ...(prev.window_rules || {}), '': '' },
    }))
  }

  const updateWindowRule = (oldKw: string, newKw: string, cat: string) => {
    setDraft((prev) => {
      const rules = { ...(prev.window_rules || {}) }
      if (oldKw !== newKw) delete rules[oldKw]
      if (newKw.trim()) rules[newKw.trim()] = cat
      return { ...prev, window_rules: rules }
    })
  }

  const removeWindowRule = (kw: string) => {
    setDraft((prev) => {
      const rules = { ...(prev.window_rules || {}) }
      delete rules[kw]
      return { ...prev, window_rules: rules }
    })
  }

  const handleSave = async () => {
    if (!app) return
    setSaving(true)
    try {
      await updateAppRule({
        app_name: app.app_name,
        display_name: draft.display_name,
        primary_category: draft.primary_category,
        tags: draft.tags,
        window_rules: draft.window_rules,
      })
      toast.success('规则已保存')
      onSaved?.()
      onClose()
    } catch (err: any) {
      toast.error(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!app?.rule) return
    if (!window.confirm('确定删除该应用规则？')) return
    setSaving(true)
    try {
      await deleteAppRule(app.app_name)
      toast.success('规则已删除')
      onSaved?.()
      onClose()
    } catch (err: any) {
      toast.error(err.message || '删除失败')
    } finally {
      setSaving(false)
    }
  }

  const title = app ? `编辑标签：${app.app_name.replace(/\.exe$/i, '')}` : '编辑标签'

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      maxWidth="max-w-2xl"
      footer={
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm text-cd-text-secondary border border-cd-border hover:bg-cd-hover transition"
          >
            取消
          </button>
          {app?.rule && (
            <button
              onClick={handleDelete}
              disabled={saving}
              className="flex items-center gap-1 px-4 py-2 rounded-xl text-sm font-medium text-cd-red hover:bg-cd-red/10 transition disabled:opacity-40"
            >
              <Trash2 size={14} /> 删除
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-1 px-4 py-2 rounded-xl text-sm font-medium bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40"
          >
            <Save size={14} /> {saving ? '保存中...' : '保存'}
          </button>
        </div>
      }
    >
      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">候选标签（多选）</label>
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => {
            const checked = draft.tags?.includes(cat)
            const color = CATEGORY_COLORS[cat]
            return (
              <button
                key={cat}
                onClick={() => toggleTag(cat)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors ${
                  checked
                    ? 'border-transparent text-white'
                    : 'border-cd-border text-cd-text-secondary hover:bg-cd-hover'
                }`}
                style={checked ? { background: color } : undefined}
              >
                {cat}
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-cd-text-secondary mb-1.5">主分类（兜底）</label>
        <select
          value={draft.primary_category || ''}
          onChange={(e) => setPrimary(e.target.value)}
          className="w-full bg-cd-bg-input text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-accent/50"
        >
          <option value="">自动推断</option>
          {CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-medium text-cd-text-secondary">窗口标题关键词规则</label>
          <button
            onClick={addWindowRule}
            className="flex items-center gap-1 text-xs text-cd-green hover:opacity-80"
          >
            <Plus size={10} /> 添加
          </button>
        </div>
        <div className="space-y-2">
          {Object.entries(draft.window_rules || {}).map(([kw, cat], idx) => (
            <div key={`${kw}-${idx}`} className="flex items-center gap-2">
              <input
                type="text"
                value={kw}
                onChange={(e) => updateWindowRule(kw, e.target.value, cat)}
                placeholder="关键词"
                className="flex-1 bg-cd-bg-input text-cd-text border border-cd-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-cd-accent/50"
              />
              <select
                value={cat}
                onChange={(e) => updateWindowRule(kw, kw, e.target.value)}
                className="bg-cd-bg-input text-cd-text border border-cd-border rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-cd-accent/50"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button
                onClick={() => removeWindowRule(kw)}
                className="text-cd-text-tertiary hover:text-cd-red transition"
              >
                <X size={14} />
              </button>
            </div>
          ))}
          {Object.keys(draft.window_rules || {}).length === 0 && (
            <div className="text-xs text-cd-text-tertiary">未设置标题关键词规则</div>
          )}
        </div>
      </div>
    </Modal>
  )
}
