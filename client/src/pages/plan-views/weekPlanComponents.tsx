import { CATEGORY_COLORS } from '../../api/client'
import { MODE_LABELS, PRIORITY_COLORS } from './weekPlanUtils'
import type { TodoV2 } from '../../api/client'
import { GripVertical, ChevronDown, ChevronUp } from 'lucide-react'

// ── SVG 环形进度 ──
export function ProgressRing({ pct, size = 14, stroke = 2, color = '#10b981' }: { pct: number; size?: number; stroke?: number; color?: string }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const off = c - (Math.min(100, Math.max(0, pct)) / 100) * c
  return (
    <svg width={size} height={size} className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--cd-border)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  )
}

// ── 任务卡片（共享组件，含分类色条 + 进度环 + 可展开）──
interface CardProps {
  todo: TodoV2
  compact?: boolean
  onClick?: () => void
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: (e: React.DragEvent) => void
  expanded?: boolean
  onToggleExpand?: () => void
}

export function TaskCard({ todo, compact, onClick, onDragStart, onDragEnd, expanded, onToggleExpand }: CardProps) {
  const isDone = todo.status === 'completed'
  const pc = PRIORITY_COLORS[(todo.priority || 3) - 1]
  const catColor = CATEGORY_COLORS[todo.category] || '#9999B0'
  const pct = todo.target_min > 0 ? (todo.progress_min / todo.target_min) * 100 : 0
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      className="relative rounded-md cursor-grab active:cursor-grabbing transition hover:brightness-110 overflow-hidden"
      style={{
        background: compact ? 'var(--cd-bg-tertiary)' : 'var(--cd-bg-secondary)',
        borderLeft: `3px solid ${pc}`,
        padding: '6px 8px 6px 10px',
      }}
    >
      {/* 分类色条（顶部 2px） */}
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: catColor }} />
      <GripVertical size={8} className="absolute top-1 right-1 opacity-30" style={{ color: 'var(--cd-text-tertiary)' }} />
      {onToggleExpand && (
        <button
          onClick={(e) => { e.stopPropagation(); onToggleExpand() }}
          className="absolute top-1 right-3 opacity-50 hover:opacity-100"
          style={{ color: 'var(--cd-text-tertiary)' }}
          title={expanded ? '收起' : '展开'}
        >
          {expanded ? <ChevronUp size={9} /> : <ChevronDown size={9} />}
        </button>
      )}
      <div className="text-cd-text leading-tight pr-6" style={{ fontSize: 9, textDecoration: isDone ? 'line-through' : 'none', opacity: isDone ? 0.6 : 1 }}>
        {todo.title}
      </div>
      <div className="flex items-center justify-between mt-1" style={{ fontSize: 7, opacity: isDone ? 0.6 : 1 }}>
        <span className="text-cd-text-tertiary truncate max-w-[60%]">
          <span style={{ color: catColor }}>●</span> {todo.category} · {MODE_LABELS[todo.mode] || todo.mode}
        </span>
        <span className="text-cd-text-tertiary tabular-nums flex items-center gap-1">
          <ProgressRing pct={pct} size={10} stroke={1.5} color={isDone ? '#10b981' : catColor} />
          {todo.progress_min}/{todo.target_min}m
        </span>
      </div>
      {!todo.assigned_date && (
        <div style={{ fontSize: 9, color: '#F0C040' }} className="mt-0.5">⬚ 未安排</div>
      )}
      {/* 展开详情 */}
      {expanded && (
        <div className="mt-1.5 pt-1.5 border-t border-cd-border flex flex-col gap-0.5" style={{ fontSize: 8 }}>
          <div className="flex justify-between text-cd-text-tertiary">
            <span>预估番茄</span>
            <span className="tabular-nums">{todo.estimated_pomodoros || 0} 个（{todo.pomodoro_size === 'small' ? '小' : '大'}）</span>
          </div>
          <div className="flex justify-between text-cd-text-tertiary">
            <span>已完成</span>
            <span className="tabular-nums">{todo.progress_min}m / {todo.target_min}m</span>
          </div>
          {todo.due_date && (
            <div className="flex justify-between text-cd-text-tertiary">
              <span>截止</span><span className="tabular-nums">{todo.due_date}</span>
            </div>
          )}
          <div className="flex justify-between text-cd-text-tertiary">
            <span>优先级</span><span>P{todo.priority || 3}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 底部统计块 ──
export function StatBlock({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-xs font-semibold tabular-nums" style={{ color }}>{value}</span>
      <span className="text-[9px] text-cd-text-tertiary">{label}</span>
    </div>
  )
}

// ── 月度进度条（年视图用）──
export function MonthProgressBar({ month, rate, total, completed }: { month: string; rate: number; total: number; completed: number }) {
  const pct = Math.round(rate)
  return (
    <div className="flex items-center gap-2" style={{ fontSize: 11 }}>
      <span className="text-cd-text-tertiary w-10 shrink-0">{month}</span>
      <div className="flex-1 h-3 rounded-full overflow-hidden" style={{ background: 'var(--cd-bg-tertiary)' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: pct > 0 ? 'var(--cd-green)' : 'transparent', transition: 'width 0.5s' }} />
      </div>
      <span className="w-16 text-right tabular-nums text-cd-text-secondary">{completed}/{total}</span>
      <span className="w-10 text-right tabular-nums" style={{ color: pct >= 60 ? '#10b981' : pct >= 30 ? '#F0C040' : 'var(--cd-text-tertiary)' }}>{pct}%</span>
    </div>
  )
}
