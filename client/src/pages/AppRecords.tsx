import { useState } from 'react'
import { getAppUsage, getTodayStats, CATEGORY_COLORS, type AppUsage, type TodayStats } from '../api/client'
import { CategoryFilter, formatDuration, useAsyncData, ApiErrorDisplay } from '../components/shared'
import dayjs from 'dayjs'

export default function AppRecords() {
  const [selectedDate, setSelectedDate] = useState(dayjs().format('YYYY-MM-DD'))
  const [filterCategory, setFilterCategory] = useState<string>('全部')

  const { data, loading, error, refresh } = useAsyncData<{ apps: AppUsage[]; stats: TodayStats | null }>(
    async () => {
      const [appData, s] = await Promise.all([getAppUsage(selectedDate), getTodayStats()])
      return { apps: appData, stats: s }
    },
    [selectedDate],
  )

  const apps = data?.apps || []
  const stats = data?.stats || null

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

      {/* ─── 应用列表 ──────────────────────── */}
      {loading ? (
        <div className="text-cd-text-tertiary animate-pulse">加载中...</div>
      ) : filtered.length === 0 ? (
        <div className="text-cd-text-tertiary text-center py-16">
          暂无应用使用记录
        </div>
      ) : (
        <div className="card">
          <div className="space-y-4">
            {filtered.map((app, idx) => {
              const catColor = CATEGORY_COLORS[app.category] || 'var(--cd-text-tertiary)'
              const pct = app.percentage || (totalMin > 0 ? (app.duration_min / totalMin) * 100 : 0)
              return (
                <div key={app.app_name} className="flex items-center gap-4">
                  {/* 排名 */}
                  <div className="w-6 text-center text-xs text-cd-text-tertiary font-mono shrink-0">
                    {idx + 1}
                  </div>

                  {/* 应用图标 */}
                  <div className="w-10 h-10 rounded-xl bg-cd-bg-secondary border border-cd-border-light flex items-center justify-center text-sm font-medium text-cd-text-secondary shrink-0">
                    {app.app_name.slice(0, 2)}
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
