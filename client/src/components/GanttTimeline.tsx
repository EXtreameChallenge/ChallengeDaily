/**
 * GanttTimeline — Gantt 式时间线（参考 ActivityWatch）
 *
 * - 24 小时水平时间轴（0:00 - 24:00）
 * - 可缩放：默认显示全天，可放大到小时级别
 * - 时间块：水平彩色条，高度=分类行，颜色=分类色
 * - 悬停显示详情：应用名 + 标题 + 时长
 * - 空白时段：灰色斜纹背景
 * - 左侧分类图例（带总时长）
 * - 底部统计条：总活跃时长 + 各分类占比
 * - 支持点击块跳转到活动详情
 * - 使用 framer-motion 做缩放动画
 * - 响应式：小屏改为垂直布局
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { ZoomIn, ZoomOut, Clock, Layers } from 'lucide-react'
import {
  getGanttTimeline,
  type GanttBlock,
  type GanttTimelineData,
} from '../api/client'

const TOTAL_MINUTES = 24 * 60 // 1440

/** "HH:MM" → 当日累计分钟数 */
function hhmmToMin(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return (h || 0) * 60 + (m || 0)
}

/** 分钟数 → "Xh Ym" / "Ym" 友好显示 */
function formatDuration(min: number): string {
  if (min <= 0) return '0m'
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  if (h === 0) return `${m}m`
  if (m === 0) return `${h}h`
  return `${h}h ${m}m`
}

const ZOOM_LEVELS = [1, 2, 4, 6] as const // 1x = 全天，6x = 4 小时一屏

export interface GanttTimelineProps {
  /** 目标日期 YYYY-MM-DD，默认今天 */
  date?: string
  /** 点击块时的回调 */
  onBlockClick?: (block: GanttBlock) => void
  className?: string
}

export default function GanttTimeline({
  date,
  onBlockClick,
  className = '',
}: GanttTimelineProps) {
  const [targetDate, setTargetDate] = useState(date || '')
  const [data, setData] = useState<GanttTimelineData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [zoom, setZoom] = useState<(typeof ZOOM_LEVELS)[number]>(1)
  const [hoveredBlock, setHoveredBlock] = useState<GanttBlock | null>(null)
  const [isNarrow, setIsNarrow] = useState(false)

  const containerRef = useRef<HTMLDivElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  // 监听容器宽度变化 → 小屏改垂直布局
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        setIsNarrow(entry.contentRect.width < 640)
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const d = targetDate || new Date().toISOString().slice(0, 10)
      const res = await getGanttTimeline(d)
      setData(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载时间线失败')
    } finally {
      setLoading(false)
    }
  }, [targetDate])

  useEffect(() => {
    load()
  }, [load])

  // 监听外部 date 变化
  useEffect(() => {
    if (date !== undefined) setTargetDate(date)
  }, [date])

  // 分类 → 行索引
  const categoryIndex = useMemo(() => {
    const map: Record<string, number> = {}
    ;(data?.categories || []).forEach((c, i) => {
      map[c.name] = i
    })
    return map
  }, [data])

  // 像素宽度：基础宽度 * zoom
  const baseWidth = 720
  const trackWidth = baseWidth * zoom
  const rowHeight = 32
  const headerHeight = 28
  const legendWidth = 140
  const totalRows = data?.categories.length || 0
  const trackHeight = totalRows * rowHeight

  // 时间标尺刻度：每 N 分钟一个
  const tickStep = zoom >= 4 ? 30 : zoom >= 2 ? 60 : 120 // 分钟
  const ticks = useMemo(() => {
    const arr: { min: number; label: string }[] = []
    for (let m = 0; m <= TOTAL_MINUTES; m += tickStep) {
      const h = Math.floor(m / 60)
      const mm = m % 60
      arr.push({ min: m, label: `${String(h).padStart(2, '0')}:${String(mm).padStart(2, '0')}` })
    }
    return arr
  }, [tickStep])

  // 缩放变化时重置 scroll
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = 0
    }
  }, [zoom])

  const minToX = (min: number) => (min / TOTAL_MINUTES) * trackWidth

  // 空白时段：把 gaps 也按像素定位
  const gapsAbs = useMemo(() => {
    if (!data?.gaps) return []
    const toX = (m: number) => (m / TOTAL_MINUTES) * trackWidth
    return data.gaps.map(g => ({
      ...g,
      x: toX(hhmmToMin(g.start)),
      w: toX(hhmmToMin(g.end)) - toX(hhmmToMin(g.start)),
    }))
  }, [data, trackWidth])

  return (
    <div
      ref={containerRef}
      className={`bg-cd-bg-card rounded-2xl border border-cd-border-light overflow-hidden ${className}`}
    >
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-cd-border-light flex-wrap gap-2">
        <div className="flex items-center gap-2 text-sm font-medium text-cd-text">
          <Layers size={14} className="text-cd-green" />
          甘特图时间线
          {!isNarrow && data && (
            <span className="text-[10px] text-cd-text-tertiary font-normal">
              · 总活跃 {formatDuration(data.total_active_min)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={targetDate}
            onChange={e => setTargetDate(e.target.value)}
            className="bg-cd-bg-input text-cd-text border border-cd-border rounded-lg px-2 py-1 text-xs focus:outline-none focus:border-cd-green"
          />
          <div className="flex items-center gap-0.5 bg-cd-bg-secondary rounded-lg border border-cd-border">
            <button
              onClick={() => {
                const idx = ZOOM_LEVELS.indexOf(zoom)
                if (idx > 0) setZoom(ZOOM_LEVELS[idx - 1])
              }}
              disabled={zoom === 1}
              className="p-1 text-cd-text-secondary hover:text-cd-text disabled:opacity-30"
              title="缩小"
            >
              <ZoomOut size={14} />
            </button>
            <span className="text-[10px] text-cd-text-tertiary px-1">{zoom}x</span>
            <button
              onClick={() => {
                const idx = ZOOM_LEVELS.indexOf(zoom)
                if (idx >= 0 && idx < ZOOM_LEVELS.length - 1) setZoom(ZOOM_LEVELS[idx + 1])
              }}
              disabled={zoom === 6}
              className="p-1 text-cd-text-secondary hover:text-cd-text disabled:opacity-30"
              title="放大"
            >
              <ZoomIn size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* 主体 */}
      <div className="p-3">
        {error ? (
          <div className="text-sm text-cd-red py-6 text-center">{error}</div>
        ) : loading && !data ? (
          <div className="text-sm text-cd-text-tertiary py-6 text-center animate-pulse">加载中...</div>
        ) : !data || data.blocks.length === 0 ? (
          <div className="text-sm text-cd-text-tertiary py-6 text-center">暂无活动记录</div>
        ) : isNarrow ? (
          <NarrowView data={data} onBlockClick={onBlockClick} />
        ) : (
          <div className="flex flex-col gap-2">
            {/* 主轨道：左侧图例 + 右侧时间轴 */}
            <div className="flex">
              {/* 左侧分类图例 */}
              <div
                className="shrink-0 border-r border-cd-border-light"
                style={{ width: legendWidth, paddingTop: headerHeight }}
              >
                {data.categories.map(cat => (
                  <div
                    key={cat.name}
                    className="flex items-center gap-1.5 px-2 text-xs text-cd-text"
                    style={{ height: rowHeight }}
                  >
                    <span
                      className="inline-block rounded-lg shrink-0"
                      style={{ width: 10, height: 10, background: cat.color }}
                    />
                    <span className="truncate flex-1">{cat.name}</span>
                    <span className="text-[10px] text-cd-text-tertiary">{formatDuration(cat.total_min)}</span>
                  </div>
                ))}
              </div>

              {/* 右侧时间轴（可水平滚动） */}
              <div
                ref={scrollRef}
                className="flex-1 overflow-x-auto"
                style={{ maxWidth: 'calc(100% - ' + legendWidth + 'px)' }}
              >
                <div style={{ width: trackWidth, position: 'relative' }}>
                  {/* 时间刻度头 */}
                  <div
                    className="relative border-b border-cd-border-light"
                    style={{ height: headerHeight }}
                  >
                    {ticks.map(t => (
                      <div
                        key={t.min}
                        className="absolute top-0 bottom-0 flex items-start justify-start"
                        style={{ left: minToX(t.min), transform: 'translateX(-50%)' }}
                      >
                        <div className="flex flex-col items-center">
                          <div className="w-px h-1.5 bg-cd-border" />
                          <span className="text-[9px] text-cd-text-tertiary mt-0.5 font-mono">
                            {t.label}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* 轨道区 */}
                  <div className="relative" style={{ height: trackHeight }}>
                    {/* 行底纹 + 空白斜纹背景（每行独立绘制） */}
                    {data.categories.map((cat, ri) => (
                      <div
                        key={cat.name}
                        className="absolute left-0 right-0"
                        style={{
                          top: ri * rowHeight,
                          height: rowHeight,
                          borderTop: ri > 0 ? '1px dashed var(--cd-border-light)' : 'none',
                        }}
                      >
                        {/* 整行底色：空白时段用斜纹 */}
                        {gapsAbs.map((g, gi) => (
                          <div
                            key={gi}
                            className="absolute top-0 bottom-0"
                            style={{
                              left: g.x,
                              width: g.w,
                              backgroundImage:
                                'repeating-linear-gradient(45deg, var(--cd-border-light) 0, var(--cd-border-light) 4px, transparent 4px, transparent 8px)',
                              opacity: 0.35,
                            }}
                            title={`空白 ${g.start} - ${g.end}（${formatDuration(g.duration_min)}）`}
                          />
                        ))}
                      </div>
                    ))}

                    {/* 时间块（动画） */}
                    {data.blocks.map((b, bi) => {
                      const ri = categoryIndex[b.category] ?? 0
                      const startX = minToX(b.start_min ?? hhmmToMin(b.start))
                      const endX = minToX(b.end_min ?? hhmmToMin(b.end))
                      const w = Math.max(2, endX - startX)
                      const isHovered = hoveredBlock === b
                      return (
                        <motion.div
                          key={`${bi}-${b.start}-${b.app_name}`}
                          initial={{ opacity: 0, scaleX: 0.6 }}
                          animate={{ opacity: 1, scaleX: 1 }}
                          transition={{ duration: 0.25, ease: 'easeOut' }}
                          onClick={() => onBlockClick?.(b)}
                          onMouseEnter={() => setHoveredBlock(b)}
                          onMouseLeave={() => setHoveredBlock(null)}
                          className="absolute rounded-lg cursor-pointer overflow-visible flex items-center px-1.5"
                          style={{
                            left: startX,
                            width: w,
                            top: ri * rowHeight + 4,
                            height: rowHeight - 8,
                            background: b.color,
                            boxShadow: isHovered
                              ? `0 0 0 2px var(--cd-text), 0 2px 6px ${b.color}66`
                              : `0 1px 2px ${b.color}55`,
                            zIndex: isHovered ? 20 : 10,
                          }}
                        >
                          {w > 60 && (
                            <span className="text-[10px] text-white truncate font-medium" style={{ textShadow: '0 1px 2px rgba(0,0,0,0.3)' }}>
                              {b.app_name}
                            </span>
                          )}
                          {/* 悬停 tooltip */}
                          {isHovered && (
                            <div
                              className="absolute z-30 bg-cd-bg-card border border-cd-border rounded-2xl shadow-xl p-2 text-xs"
                              style={{
                                top: '100%',
                                left: 0,
                                minWidth: 180,
                                marginTop: 4,
                              }}
                            >
                              <div className="flex items-center gap-1.5 mb-1">
                                <span
                                  className="inline-block rounded-lg"
                                  style={{ width: 8, height: 8, background: b.color }}
                                />
                                <span className="font-medium text-cd-text">{b.app_name}</span>
                                <span className="text-[10px] text-cd-text-tertiary">{b.category}</span>
                              </div>
                              <div className="text-cd-text-secondary break-words">
                                {b.title || '无标题'}
                              </div>
                              <div className="flex items-center gap-1 text-cd-text-tertiary mt-1">
                                <Clock size={10} />
                                {b.start} - {b.end}（{formatDuration(b.duration_min)}）
                              </div>
                            </div>
                          )}
                        </motion.div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* 底部统计条 */}
            <BottomStats data={data} />
          </div>
        )}
      </div>
    </div>
  )
}

/** 底部统计：总活跃时长 + 各分类占比条 */
function BottomStats({ data }: { data: GanttTimelineData }) {
  const total = data.total_active_min || 1
  return (
    <div className="bg-cd-bg-secondary rounded-2xl p-3 border border-cd-border-light">
      <div className="flex items-center justify-between text-xs mb-2">
        <span className="text-cd-text-tertiary flex items-center gap-1">
          <Clock size={11} /> 总活跃时长
        </span>
        <span className="text-cd-text font-semibold">{formatDuration(data.total_active_min)}</span>
      </div>
      {/* 分类占比堆叠条 */}
      <div className="flex h-2 rounded-full overflow-hidden bg-cd-bg-input">
        {data.categories.map(cat => (
          <div
            key={cat.name}
            style={{
              width: `${(cat.total_min / total) * 100}%`,
              background: cat.color,
            }}
            title={`${cat.name} ${formatDuration(cat.total_min)}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
        {data.categories.map(cat => (
          <span key={cat.name} className="text-[10px] text-cd-text-tertiary flex items-center gap-1">
            <span className="inline-block rounded-lg" style={{ width: 8, height: 8, background: cat.color }} />
            {cat.name} {((cat.total_min / total) * 100).toFixed(1)}%
          </span>
        ))}
      </div>
    </div>
  )
}

/** 小屏垂直布局：按时间顺序列出 block */
function NarrowView({
  data,
  onBlockClick,
}: {
  data: GanttTimelineData
  onBlockClick?: (block: GanttBlock) => void
}) {
  const sorted = [...data.blocks].sort((a, b) => (a.start_min ?? hhmmToMin(a.start)) - (b.start_min ?? hhmmToMin(b.start)))
  return (
    <div className="space-y-1.5">
      {sorted.map((b, i) => (
        <button
          key={`${i}-${b.start}-${b.app_name}`}
          onClick={() => onBlockClick?.(b)}
          className="w-full text-left bg-cd-bg-secondary rounded-2xl border border-cd-border-light overflow-hidden flex items-stretch"
        >
          <div className="shrink-0" style={{ width: 4, background: b.color }} />
          <div className="flex-1 min-w-0 p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-cd-text truncate">{b.app_name}</span>
              <span className="text-[10px] text-cd-text-tertiary font-mono shrink-0">
                {b.start} - {b.end}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span
                className="text-[10px] px-1 py-0.5 rounded-lg"
                style={{ background: b.color + '22', color: b.color }}
              >
                {b.category}
              </span>
              <span className="text-[10px] text-cd-text-tertiary">{formatDuration(b.duration_min)}</span>
            </div>
            {b.title && (
              <div className="text-[11px] text-cd-text-secondary mt-1 break-words truncate">{b.title}</div>
            )}
          </div>
        </button>
      ))}
      <BottomStats data={data} />
    </div>
  )
}

/** 占位导出（保留用于将来按分类筛选等扩展） */
export type { GanttBlock, GanttTimelineData }
