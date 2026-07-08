import { useEffect, useMemo, useState } from 'react'
import {
  getKnownApps,
  updateAppRule,
  deleteAppRule,
  getAppIconUrl,
  CATEGORIES,
  CATEGORY_COLORS,
  type AppCategoryRule,
} from '../api/client'
import { useAsyncData, ApiErrorDisplay } from '../components/shared'
import { useToast } from '../components/Toast'
import { Tags, Plus, X, Save, Trash2, Search, ImageOff } from 'lucide-react'

interface KnownApp {
  app_name: string
  rule?: AppCategoryRule
}

const EMPTY_RULE: Partial<AppCategoryRule> = {
  primary_category: '',
  tags: [],
  window_rules: {},
}

export default function AppTags() {
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState<Partial<AppCategoryRule>>(EMPTY_RULE)
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})

  const { data, loading, error, refresh } = useAsyncData<{ apps: KnownApp[] }>(
    async () => getKnownApps(),
    [],
  )

  const apps = data?.apps || []

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return apps
    return apps.filter(
      (a) =>
        a.app_name.toLowerCase().includes(q) ||
        a.rule?.display_name?.toLowerCase().includes(q),
    )
  }, [apps, search])

  const appsKey = useMemo(() => apps.map((a) => a.app_name).join('|'), [apps])

  // 加载图标 URL
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      for (const app of apps.slice(0, 50)) {
        try {
          map[app.app_name] = await getAppIconUrl(app.app_name)
        } catch {
          map[app.app_name] = ''
        }
      }
      if (!cancelled) setIconUrls(map)
    })()
    return () => {
      cancelled = true
    }
  }, [appsKey])

  const startEdit = (app: KnownApp) => {
    setEditing(app.app_name)
    setDraft({
      app_name: app.app_name,
      display_name: app.rule?.display_name || app.app_name.replace(/\.exe$/i, ''),
      primary_category: app.rule?.primary_category || '',
      tags: app.rule?.tags ? [...app.rule.tags] : [],
      window_rules: app.rule?.window_rules ? { ...app.rule.window_rules } : {},
    })
  }

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
    if (!editing) return
    try {
      await updateAppRule({
        app_name: editing,
        display_name: draft.display_name,
        primary_category: draft.primary_category,
        tags: draft.tags,
        window_rules: draft.window_rules,
      })
      toast.success('规则已保存')
      setEditing(null)
      setDraft(EMPTY_RULE)
      refresh()
    } catch (err: any) {
      toast.error(err.message || '保存失败')
    }
  }

  const handleDelete = async (appName: string) => {
    try {
      await deleteAppRule(appName)
      toast.success('规则已删除')
      if (editing === appName) {
        setEditing(null)
        setDraft(EMPTY_RULE)
      }
      refresh()
    } catch (err: any) {
      toast.error(err.message || '删除失败')
    }
  }

  const displayName = (app: KnownApp) =>
    app.rule?.display_name || app.app_name.replace(/\.exe$/i, '')

  if (error) return <ApiErrorDisplay error={error} onRetry={refresh} />

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-cd-text flex items-center gap-2">
            <Tags size={18} className="text-cd-green" />
            应用标签
          </h1>
          <p className="text-xs text-cd-text-tertiary mt-1">
            为每个应用预设候选标签，AI 会自动匹配最合适的分类
          </p>
        </div>
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-cd-text-tertiary" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索应用..."
            className="bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors w-48"
          />
        </div>
      </div>

      {loading ? (
        <div className="text-cd-text-tertiary animate-pulse">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="text-cd-text-tertiary text-center py-16">
          {search ? '未找到匹配应用' : '暂无应用记录，使用一段时间后自动出现'}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filtered.map((app) => {
            const isEditing = editing === app.app_name
            const rule = app.rule
            const tags = rule?.tags || []
            const iconUrl = iconUrls[app.app_name]
            return (
              <div key={app.app_name} className="card p-4 space-y-3">
                {/* 头部 */}
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center shrink-0 overflow-hidden">
                    {(() => {
                      const defaultIcon = import.meta.env.DEV ? '/icon.png' : './icon.png'
                      return (
                        <img
                          src={iconUrl || defaultIcon}
                          alt=""
                          className="w-7 h-7 object-contain"
                          onError={(e) => { e.currentTarget.src = defaultIcon }}
                        />
                      )
                    })()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-cd-text truncate">
                      {displayName(app)}
                    </div>
                    <div className="text-[10px] text-cd-text-tertiary font-mono truncate">
                      {app.app_name}
                    </div>
                  </div>
                  {rule ? (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-cd-green-light text-cd-green">
                      已配置
                    </span>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-cd-bg-secondary text-cd-text-tertiary">
                      默认
                    </span>
                  )}
                </div>

                {/* 标签预览 */}
                {!isEditing && (
                  <div className="flex flex-wrap gap-1.5">
                    {tags.length > 0 ? (
                      tags.map((tag) => {
                        const color = CATEGORY_COLORS[tag] || 'var(--cd-text-tertiary)'
                        return (
                          <span
                            key={tag}
                            className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                            style={{ background: color + '18', color }}
                          >
                            {tag}
                            {tag === rule?.primary_category && ' · 主'}
                          </span>
                        )
                      })
                    ) : (
                      <span className="text-[10px] text-cd-text-tertiary">未设置标签，使用默认规则</span>
                    )}
                  </div>
                )}

                {/* 编辑区 */}
                {isEditing && (
                  <div className="space-y-3 pt-2 border-t border-cd-border-light">
                    <div>
                      <label className="text-[10px] text-cd-text-secondary block mb-1.5">候选标签（多选）</label>
                      <div className="flex flex-wrap gap-2">
                        {CATEGORIES.map((cat) => {
                          const checked = draft.tags?.includes(cat)
                          const color = CATEGORY_COLORS[cat]
                          return (
                            <button
                              key={cat}
                              onClick={() => toggleTag(cat)}
                              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium border transition-colors ${
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
                      <label className="text-[10px] text-cd-text-secondary block mb-1.5">主分类（兜底）</label>
                      <select
                        value={draft.primary_category || ''}
                        onChange={(e) => setPrimary(e.target.value)}
                        className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
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
                        <label className="text-[10px] text-cd-text-secondary">窗口标题关键词规则</label>
                        <button
                          onClick={addWindowRule}
                          className="flex items-center gap-1 text-[10px] text-cd-green hover:opacity-80"
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
                              className="flex-1 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-cd-green"
                            />
                            <select
                              value={cat}
                              onChange={(e) => updateWindowRule(kw, kw, e.target.value)}
                              className="bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-cd-green"
                            >
                              {CATEGORIES.map((c) => (
                                <option key={c} value={c}>
                                  {c}
                                </option>
                              ))}
                            </select>
                            <button
                              onClick={() => removeWindowRule(kw)}
                              className="text-cd-text-tertiary hover:text-cd-red"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        ))}
                        {Object.keys(draft.window_rules || {}).length === 0 && (
                          <div className="text-[10px] text-cd-text-tertiary">未设置标题关键词规则</div>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* 操作按钮 */}
                <div className="flex items-center justify-end gap-2 pt-1">
                  {isEditing ? (
                    <>
                      <button
                        onClick={() => {
                          setEditing(null)
                          setDraft(EMPTY_RULE)
                        }}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium text-cd-text-secondary hover:bg-cd-hover transition-colors"
                      >
                        取消
                      </button>
                      {rule && (
                        <button
                          onClick={() => handleDelete(app.app_name)}
                          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-cd-red hover:bg-cd-red/10 transition-colors"
                        >
                          <Trash2 size={12} /> 删除
                        </button>
                      )}
                      <button
                        onClick={handleSave}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:opacity-90 transition-opacity"
                      >
                        <Save size={12} /> 保存
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => startEdit(app)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
                    >
                      编辑标签
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
