import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { getAppUsage, getTodayStats, getAppIconUrl, CATEGORY_COLORS, type AppUsage, type TodayStats } from '../api/client'
import { CategoryFilter, formatDuration, useAsyncData, ApiErrorDisplay } from '../components/shared'
import dayjs from 'dayjs'

export default function AppRecords() {
  const [selectedDate, setSelectedDate] = useState(dayjs().format('YYYY-MM-DD'))
  const [filterCategory, setFilterCategory] = useState<string>('全部')
  const [iconUrls, setIconUrls] = useState<Record<string, string>>({})
  // 展开的内容维度 app_name_raw
  const [expandedApp, setExpandedApp] = useState<string | null>(null)

  const { data, loading, error, refresh } = useAsyncData<{ apps: AppUsage[]; stats: TodayStats | null }>(
    async () => {
      const [appData, s] = await Promise.all([getAppUsage(selectedDate), getTodayStats()])
      return { apps: appData, stats: s }
    },
    [selectedDate],
  )

  const apps = data?.apps || []
  const stats = data?.stats || null

  const appsKey = useMemo(() => apps.map((a) => a.app_name_raw).join('|'), [apps])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const map: Record<string, string> = {}
      for (const app of apps) {
        try {
          map[app.app_name_raw] = await getAppIconUrl(app.app_name_raw)
        } catch {
          map[app.app_name_raw] = ''
        }
      }
      if (!cancelled) setIconUrls(map)
    })()
    return () => { cancelled = true }
  }, [appsKey])

  // 切换日期时折叠所有展开项
  useEffect(() => { setExpandedApp(null) }, [selectedDate])

  const filtered = filterCategory === '全部'
    ? apps
    : apps.filter((a) => a.category === filterCategory)

  // 提取实际出现的分类（用于筛选栏）
  const activeCategories = [...new Set(apps.map((a) => a.category))]
  const totalMin = stats?.total_duration_min || 1

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-cd-text">应用记录</h1>
        <input
          type="date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
        />
      </div>

      {/* ─── 分类筛选 ──────────────────────── */}
      <CategoryFilter selected={filterCategory} onChange={setFilterCategory} categories={activeCategories} />

      {/* ─── 错误提示 ──────────────────────── */}
      {error && <ApiErrorDisplay error={error} onRetry={refresh} />}

      {/* ─── 提示：点击展开内容 ──────────────── */}
      {filtered.length > 0 && (
        <div className="text-[11px] text-cd-text-tertiary">
          提示：点击应用可展开查看同应用下不同窗口标题的时长分布（多窗口分摊 + 内容维度）。
        </div>
      )}

      {/* ─── 应用列表 ──────────────────────── */}
      {loading ? (
        <div className="text-cd-text-tertiary animate-pulse">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="text-cd-text-tertiary text-center py-16">
          暂无应用使用记录
        </div>
      ) : (
        <div className="card">
          <div className="space-y-2">
            {filtered.map((app, idx) => {
              const catColor = CATEGORY_COLORS[app.category] || 'var(--cd-text-tertiary)'
              const pct = app.percentage || (totalMin > 0 ? (app.duration_min / totalMin) * 100 : 0)
              const iconUrl = iconUrls[app.app_name_raw]
              const isExpanded = expandedApp === app.app_name_raw
              const hasContents = (app.contents?.length || 0) > 0
              const defaultIcon = import.meta.env.DEV ? '/icon.png' : './icon.png'
              return (
                <div key={app.app_name} className="rounded-lg transition-colors">
                  <div
                    className={`flex items-center gap-4 group px-2 py-2 rounded-lg cursor-pointer ${isExpanded ? 'bg-cd-bg-secondary' : 'hover:bg-cd-bg-secondary/50'}`}
                    onClick={() => hasContents && setExpandedApp(isExpanded ? null : app.app_name_raw)}
                  >
                    {/* 排名 */}
                    <div className="w-6 text-center text-xs text-cd-text-tertiary font-mono shrink-0">
                      {idx + 1}
                    </div>

                    {/* 应用图标 */}
                    <div className="w-10 h-10 rounded-xl bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center text-sm font-medium text-cd-text-secondary shrink-0 overflow-hidden">
                      <img
                        src={iconUrl || defaultIcon}
                        alt=""
                        className="w-7 h-7 object-contain"
                        onError={(e) => { e.currentTarget.src = defaultIcon }}
                      />
                    </div>

                    {/* 内容 */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-cd-text truncate">{app.app_name}</span>
                        <span
                          className="px-2 py-0.5 rounded-full text-[10px] font-medium shrink-0"
                          style={{
                            background: catColor + '18',
                            color: catColor,
                          }}
                        >
                          {app.category}
                        </span>
                        {hasContents && (
                          <span
                            className="text-[10px] text-cd-text-tertiary flex items-center gap-0.5 shrink-0"
                            title={`${app.window_count} 个不同窗口/标题`}
                          >
                            <span className={`inline-block transition-transform ${isExpanded ? 'rotate-90' : ''}`}>▸</span>
                            {app.window_count} 个内容
                          </span>
                        )}
                        <Link
                          to="/app-tags"
                          onClick={(e) => e.stopPropagation()}
                          className="opacity-0 group-hover:opacity-100 text-[10px] text-cd-green hover:underline transition-opacity"
                        >
                          编辑标签
                        </Link>
                      </div>
                      <div className="progress-bar">
                        <div
                          className="progress-bar-fill"
                          style={{
                            width: `${Math.max(pct, 2)}%`,
                            background: catColor,
                          }}
                        />
                      </div>
                    </div>

                    {/* 时长 */}
                    <div className="text-right shrink-0">
                      <div className="text-sm font-medium text-cd-text">
                        {formatDuration(app.duration_min)}
                      </div>
                      <div className="text-[10px] text-cd-text-tertiary">
                        {pct.toFixed(1)}%
                      </div>
                    </div>
                  </div>

                  {/* ─── 内容维度展开区 ─── */}
                  {isExpanded && hasContents && (
                    <div className="ml-16 mr-2 mb-2 mt-1 border-l-2 border-cd-border-light pl-4 space-y-2 animate-fade-in">
                      <div className="text-[10px] text-cd-text-tertiary uppercase tracking-wide">
                        内容维度 · 同应用不同窗口标题时长
                      </div>
                      {app.contents!.map((c, cIdx) => {
                        const cPct = c.percentage
                        return (
                          <div key={cIdx} className="flex items-center gap-3 py-1">
                            <div className="flex-1 min-w-0">
                              <div className="text-xs text-cd-text truncate" title={c.title || '(无标题)'}>
                                {c.title || '(无标题)'}
                              </div>
                              <div className="progress-bar mt-1" style={{ height: '4px' }}>
                                <div
                                  className="progress-bar-fill"
                                  style={{
                                    width: `${Math.max(cPct, 2)}%`,
                                    background: catColor,
                                    opacity: 0.7,
                                  }}
                                />
                              </div>
                            </div>
                            <div className="text-right shrink-0 w-20">
                              <div className="text-[11px] text-cd-text-secondary">
                                {formatDuration(c.duration_min)}
                              </div>
                              <div className="text-[10px] text-cd-text-tertiary">
                                {cPct.toFixed(1)}%
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ─── 分类汇总 ──────────────────────── */}
      {stats?.categories && Object.keys(stats.categories).length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-cd-text mb-3">分类汇总</h2>
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(stats.categories)
              .sort(([, a], [, b]) => b - a)
              .map(([cat, dur]) => {
                const catColor = CATEGORY_COLORS[cat] || 'var(--cd-text-tertiary)'
                const pct = totalMin > 0 ? (dur / totalMin) * 100 : 0
                return (
                  <div
                    key={cat}
                    className="flex items-center gap-3 bg-cd-bg-secondary rounded-xl p-3"
                  >
                    <span
                      className="w-3 h-3 rounded-full shrink-0"
                      style={{ background: catColor }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-cd-text">{cat}</div>
                      <div className="text-[10px] text-cd-text-tertiary">
                        {Math.round(dur)} 分钟
                      </div>
                    </div>
                    <span className="text-xs font-mono text-cd-text-tertiary">
                      {pct.toFixed(0)}%
                    </span>
                  </div>
                )
              })}
          </div>
        </div>
      )}
    </div>
  )
}
