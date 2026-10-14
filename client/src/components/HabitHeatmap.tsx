/**
 * HabitHeatmap — 习惯独立热力图（参考 Loop Habit Tracker）
 *
 * - GitHub 风格方块矩阵：7 行（周一到周日）× N 列（天数）
 * - 5 级强度：0=灰色透明，1-4=紫橙渐变（#af52de → #ff9500）
 * - 鼠标悬停显示日期 + 完成次数 + 目标
 * - 底部统计：连续天数、完成率、强度等级（A-E 带颜色）
 * - 可切换天数：30/60/90/180/365
 * - 响应式：小屏可水平滚动
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Flame, TrendingUp, Award } from 'lucide-react'
import {
  getHabitHeatmap,
  type HabitHeatmapData,
  type HabitHeatmapDay,
  type HabitStrengthScore,
} from '../api/client'

// ── 紫橙渐变颜色（#af52de → #ff9500）──
// intensity 0: 灰色透明；1-4: 在紫→橙之间线性插值
const COLOR_LOW = '#af52de' // 紫
const COLOR_HIGH = '#ff9500' // 橙

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ]
}
function rgbToHex(r: number, g: number, b: number): string {
  const toHex = (n: number) => Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}
function lerpColor(a: string, b: string, t: number): string {
  const [r1, g1, b1] = hexToRgb(a)
  const [r2, g2, b2] = hexToRgb(b)
  return rgbToHex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)
}

/** 根据 intensity 返回填充色（0-4） */
function intensityColor(intensity: number): string {
  if (intensity <= 0) return 'var(--cd-border-light)'
  // 1 → 紫，2 → 紫偏中，3 → 中偏橙，4 → 橙
  const t = (intensity - 1) / 3 // 0, 0.33, 0.66, 1
  return lerpColor(COLOR_LOW, COLOR_HIGH, t)
}

/** 强度等级 → 徽章颜色 */
const SCORE_COLOR: Record<HabitStrengthScore, string> = {
  A: '#10b981', // 绿
  B: '#af52de', // 紫
  C: '#ff9500', // 橙
  D: '#f59e0b', // 琥珀
  E: '#6b7280', // 灰
}

const DAY_OPTIONS = [30, 60, 90, 180, 365] as const

// 周一 → 周日的中文标签
const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日']

export interface HabitHeatmapProps {
  /** 习惯 ID */
  habitId: number
  /** 默认展示天数 */
  defaultDays?: (typeof DAY_OPTIONS)[number]
  /** 初始折叠（点击展开） */
  defaultCollapsed?: boolean
  /** 自定义类名 */
  className?: string
}

export default function HabitHeatmap({
  habitId,
  defaultDays = 90,
  defaultCollapsed = false,
  className = '',
}: HabitHeatmapProps) {
  const [days, setDays] = useState<number>(defaultDays)
  const [collapsed, setCollapsed] = useState(defaultCollapsed)
  const [data, setData] = useState<HabitHeatmapData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hovered, setHovered] = useState<HabitHeatmapDay | null>(null)

  const load = useCallback(async () => {
    if (collapsed) return
    setLoading(true)
    setError(null)
    try {
      const res = await getHabitHeatmap(habitId, days)
      setData(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载热力图失败')
    } finally {
      setLoading(false)
    }
  }, [habitId, days, collapsed])

  useEffect(() => {
    load()
  }, [load])

  // 把 days 数组重排为 [col][weekday] 矩阵：
  // 列从左到右递增时间；每列 7 行（周一到周日）
  // 与 GitHub 热力图一致：第一列对齐到起始日的星期一
  const { grid, monthLabels } = useMemo(() => {
    if (!data || !data.days.length) return { grid: [] as HabitHeatmapDay[][], monthLabels: [] as { col: number; label: string }[] }
    // 按 ISO 周一=0, 周日=6
    const isoWeekday = (d: Date) => (d.getDay() + 6) % 7
    const first = new Date(data.days[0].date + 'T00:00:00')
    const leadOffset = isoWeekday(first) // 第一天前面要留几个空位
    const cells: (HabitHeatmapDay | null)[] = []
    for (let i = 0; i < leadOffset; i++) cells.push(null)
    cells.push(...data.days)
    // 补齐到 7 的倍数
    while (cells.length % 7 !== 0) cells.push(null)

    const cols: HabitHeatmapDay[][] = []
    for (let i = 0; i < cells.length; i += 7) {
      cols.push(cells.slice(i, i + 7) as HabitHeatmapDay[])
    }

    // 月份标签：每列若首日所在月份变化则标记
    const labels: { col: number; label: string }[] = []
    let lastMonth = ''
    cols.forEach((col, ci) => {
      const firstNonEmpty = col.find(Boolean)
      if (!firstNonEmpty) return
      const d = new Date(firstNonEmpty.date + 'T00:00:00')
      const m = `${d.getMonth() + 1}月`
      if (m !== lastMonth) {
        labels.push({ col: ci, label: m })
        lastMonth = m
      }
    })
    return { grid: cols, monthLabels: labels }
  }, [data])

  const cellSize = 13
  const cellGap = 3
  const weekdayLabelWidth = 22
  const monthLabelHeight = 16
  const gridWidth = grid.length * (cellSize + cellGap)
  const gridHeight = 7 * (cellSize + cellGap)

  return (
    <div
      className={`bg-cd-bg-card rounded-2xl border border-cd-border-light overflow-hidden ${className}`}
    >
      {/* 头部：标题 + 切换天数 + 折叠 */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-cd-border-light">
        <button
          onClick={() => setCollapsed(c => !c)}
          className="flex items-center gap-1.5 text-sm font-medium text-cd-text hover:text-cd-green transition-colors"
        >
          <span className="text-cd-text-tertiary">{collapsed ? '▶' : '▼'}</span>
          热力图
          {data && (
            <span className="text-[10px] text-cd-text-tertiary font-normal">
              · {data.habit_name}
            </span>
          )}
        </button>
        {!collapsed && (
          <div className="flex items-center gap-1">
            {DAY_OPTIONS.map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-2 py-0.5 text-[11px] rounded-lg transition-colors ${
                  days === d
                    ? 'bg-cd-green/20 text-cd-green'
                    : 'text-cd-text-tertiary hover:text-cd-text hover:bg-cd-hover'
                }`}
              >
                {d === 365 ? '1年' : `${d}天`}
              </button>
            ))}
          </div>
        )}
      </div>

      {collapsed ? null : (
        <div className="p-4">
          {error ? (
            <div className="text-sm text-cd-red py-6 text-center">{error}</div>
          ) : loading && !data ? (
            <div className="text-sm text-cd-text-tertiary py-6 text-center animate-pulse">加载中...</div>
          ) : !data || grid.length === 0 ? (
            <div className="text-sm text-cd-text-tertiary py-6 text-center">暂无打卡数据</div>
          ) : (
            <>
              {/* 热力图主体：水平可滚动 */}
              <div className="overflow-x-auto">
                <svg
                  width={weekdayLabelWidth + gridWidth}
                  height={monthLabelHeight + gridHeight}
                  style={{ minWidth: '100%' }}
                  role="img"
                  aria-label="习惯打卡热力图"
                >
                  {/* 月份标签 */}
                  {monthLabels.map(({ col, label }) => (
                    <text
                      key={`${col}-${label}`}
                      x={weekdayLabelWidth + col * (cellSize + cellGap)}
                      y={12}
                      fontSize={10}
                      fill="var(--cd-text-tertiary)"
                    >
                      {label}
                    </text>
                  ))}
                  {/* 周几标签 */}
                  {WEEKDAY_LABELS.map((lbl, idx) => {
                    // 仅在偶数行显示，避免拥挤
                    if (idx % 2 !== 0) return null
                    return (
                      <text
                        key={lbl}
                        x={0}
                        y={monthLabelHeight + idx * (cellSize + cellGap) + cellSize - 2}
                        fontSize={10}
                        fill="var(--cd-text-tertiary)"
                      >
                        {lbl}
                      </text>
                    )
                  })}
                  {/* 方块矩阵 */}
                  {grid.map((col, ci) =>
                    col.map((day, wi) => {
                      if (!day) return null
                      const x = weekdayLabelWidth + ci * (cellSize + cellGap)
                      const y = monthLabelHeight + wi * (cellSize + cellGap)
                      const fill = intensityColor(day.intensity)
                      const isHovered = hovered?.date === day.date
                      return (
                        <rect
                          key={`${ci}-${wi}`}
                          x={x}
                          y={y}
                          width={cellSize}
                          height={cellSize}
                          rx={2}
                          fill={fill}
                          stroke={isHovered ? 'var(--cd-text)' : 'transparent'}
                          strokeWidth={isHovered ? 1 : 0}
                          style={{ cursor: 'pointer', transition: 'fill 0.15s' }}
                          onMouseEnter={() => setHovered(day)}
                          onMouseLeave={() => setHovered(null)}
                        >
                          <title>
                            {day.date} | 完成 {day.count} / {data.target_count}（强度 {day.intensity}）
                          </title>
                        </rect>
                      )
                    }),
                  )}
                </svg>
              </div>

              {/* 悬停详情 */}
              {hovered && (
                <div className="mt-2 text-xs text-cd-text-secondary flex items-center gap-3">
                  <span className="font-mono">{hovered.date}</span>
                  <span>
                    完成 <span className="text-cd-text font-medium">{hovered.count}</span> / {data.target_count}
                  </span>
                  <span
                    className="px-1.5 py-0.5 rounded-lg"
                    style={{
                      background: intensityColor(hovered.intensity) + '22',
                      color: intensityColor(hovered.intensity),
                    }}
                  >
                    强度 {hovered.intensity}
                  </span>
                </div>
              )}

              {/* 图例 */}
              <div className="mt-3 flex items-center justify-between text-[11px] text-cd-text-tertiary">
                <span>较少</span>
                <div className="flex items-center gap-1">
                  {[0, 1, 2, 3, 4].map(i => (
                    <span
                      key={i}
                      style={{
                        width: 11,
                        height: 11,
                        borderRadius: 2,
                        display: 'inline-block',
                        background: intensityColor(i),
                      }}
                    />
                  ))}
                </div>
                <span>较多</span>
              </div>

              {/* 底部统计 */}
              <div className="mt-3 grid grid-cols-3 gap-3">
                <StatCard
                  icon={<Flame size={14} className="text-orange-400" />}
                  label="连续天数"
                  value={`${data.streak} 天`}
                />
                <StatCard
                  icon={<TrendingUp size={14} className="text-cd-green" />}
                  label="完成率"
                  value={`${data.completion_rate.toFixed(1)}%`}
                />
                <StatCard
                  icon={<Award size={14} style={{ color: SCORE_COLOR[data.strength_score] }} />}
                  label="强度等级"
                  value={
                    <span
                      className="px-2 py-0.5 rounded-lg text-xs font-bold"
                      style={{
                        background: SCORE_COLOR[data.strength_score] + '22',
                        color: SCORE_COLOR[data.strength_score],
                      }}
                    >
                      {data.strength_score}
                    </span>
                  }
                />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

/** 统计小卡片 */
function StatCard({
  icon,
  label,
  value,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
}) {
  return (
    <div className="bg-cd-bg-secondary rounded-2xl px-3 py-2 border border-cd-border-light">
      <div className="flex items-center gap-1.5 text-[10px] text-cd-text-tertiary mb-0.5">
        {icon}
        {label}
      </div>
      <div className="text-sm font-semibold text-cd-text">{value}</div>
    </div>
  )
}
