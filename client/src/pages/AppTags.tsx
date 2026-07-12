import { useEffect, useMemo, useState } from 'react'
import {
  getKnownApps,
  getAppIconUrl,
  CATEGORIES,
  CATEGORY_COLORS,
  type AppCategoryRule,
} from '../api/client'
import { useAsyncData, ApiErrorDisplay } from '../components/shared'
import { useToast } from '../components/Toast'
import AppTagEditModal from '../components/AppTagEditModal'
import { Tags, Search } from 'lucide-react'

interface KnownApp {
  app_name: string
  rule?: AppCategoryRule
}

export default function AppTags() {
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [editingApp, setEditingApp] = useState<KnownApp | null>(null)
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
      const results = await Promise.allSettled(
        apps.slice(0, 50).map(app => getAppIconUrl(app.app_name).then(url => ({ name: app.app_name, url })))
      )
      for (const r of results) {
        if (r.status === 'fulfilled') map[r.value.name] = r.value.url
      }
      if (!cancelled) setIconUrls(map)
    })()
    return () => {
      cancelled = true
    }
  }, [appsKey])

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

                {/* 操作按钮 */}
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    onClick={() => setEditingApp(app)}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
                  >
                    编辑标签
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <AppTagEditModal
        open={editingApp !== null}
        onClose={() => setEditingApp(null)}
        app={editingApp}
        onSaved={refresh}
      />
    </div>
  )
}
