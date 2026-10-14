import { useEffect, useReducer, useCallback, useRef, type CSSProperties } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useEventStream } from '../hooks/useEventStream'
import { useGrowthStore, type ItemRarity, type PetStage } from '../stores/growthStore'

// ─── 稀有度视觉配置 ──────────────────────────────
const RARITY_STYLE: Record<ItemRarity, { color: string; border: string; glow: string; label: string; pulse?: boolean }> = {
  common: { color: '#9CA3AF', border: 'rgba(156,163,175,0.5)', glow: '0 0 0 rgba(156,163,175,0)', label: '普通' },
  rare: { color: '#60A5FA', border: 'rgba(96,165,250,0.6)', glow: '0 0 12px rgba(96,165,250,0.4)', label: '稀有' },
  epic: { color: '#C084FC', border: 'rgba(192,132,252,0.7)', glow: '0 0 16px rgba(192,132,252,0.5)', label: '史诗' },
  legendary: { color: '#FBBF24', border: 'rgba(251,191,36,0.8)', glow: '0 0 24px rgba(251,191,36,0.6)', label: '传说', pulse: true },
}

type NotificationKind = 'item_drop' | 'level_up' | 'pet_evolution'

interface NotificationItem {
  id: number
  kind: NotificationKind
  // item_drop
  itemKey?: string
  itemName?: string
  rarity?: ItemRarity
  icon?: string
  source?: string
  // level_up
  newLevel?: number
  expAwarded?: number
  // pet_evolution
  oldStage?: PetStage
  newStage?: PetStage
  message?: string
}

type ReducerAction =
  | { type: 'add'; item: NotificationItem }
  | { type: 'remove'; id: number }
  | { type: 'clear' }

interface NotificationState {
  items: NotificationItem[]
}

function notificationReducer(state: NotificationState, action: ReducerAction): NotificationState {
  switch (action.type) {
    case 'add': {
      // 最多同时显示 3 条，超过则移除最早的
      const next = [...state.items, action.item]
      if (next.length > 3) next.shift()
      return { items: next }
    }
    case 'remove':
      return { items: state.items.filter(i => i.id !== action.id) }
    case 'clear':
      return { items: [] }
    default:
      return state
  }
}

const AUTO_DISMISS_MS = 3000

export default function DropNotification() {
  const { event } = useEventStream()
  const applySseEvent = useGrowthStore(s => s.applySseEvent)
  const [state, dispatch] = useReducer(notificationReducer, { items: [] })
  const idCounter = useRef(0)
  const timersRef = useRef(new Map<number, number>())

  // 清理所有定时器
  useEffect(() => {
    const timers = timersRef.current
    return () => {
      timers.forEach(t => window.clearTimeout(t))
      timers.clear()
    }
  }, [])

  const dismiss = useCallback((id: number) => {
    dispatch({ type: 'remove', id })
    const t = timersRef.current.get(id)
    if (t) {
      window.clearTimeout(t)
      timersRef.current.delete(id)
    }
  }, [])

  const enqueue = useCallback((item: Omit<NotificationItem, 'id'>) => {
    const id = ++idCounter.current
    dispatch({ type: 'add', item: { ...item, id } })
    const timer = window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
    timersRef.current.set(id, timer)
  }, [dismiss])

  // 监听 SSE 事件
  useEffect(() => {
    if (!event || !event.type) return
    const data = event.data || {}
    switch (event.type) {
      case 'item_drop':
        // 同步更新 store（背包）
        applySseEvent('item_drop', data)
        enqueue({
          kind: 'item_drop',
          itemKey: (data.item_key as string) || '',
          itemName: (data.item_name as string) || '未知道具',
          rarity: (data.rarity as ItemRarity) || 'common',
          icon: (data.icon as string) || '📦',
          source: (data.source as string) || '',
        })
        break
      case 'level_up':
        applySseEvent('level_up', data)
        enqueue({
          kind: 'level_up',
          newLevel: (data.new_level as number) || 0,
          expAwarded: (data.exp_awarded as number) || 0,
        })
        break
      case 'pet_evolution':
        applySseEvent('pet_evolution', data)
        enqueue({
          kind: 'pet_evolution',
          oldStage: (data.old_stage as PetStage) || 'egg',
          newStage: (data.new_stage as PetStage) || 'egg',
          message: (data.message as string) || '宠物进化了！',
        })
        break
      default:
        break
    }
  }, [event, applySseEvent, enqueue])

  return (
    <div
      className="fixed top-16 right-4 z-[100] flex flex-col gap-2 pointer-events-none"
      style={{ maxWidth: '320px' }}
      aria-live="polite"
      aria-atomic="false"
    >
      <AnimatePresence>
        {state.items.map(item => (
          <NotificationCard key={item.id} item={item} onDismiss={() => dismiss(item.id)} />
        ))}
      </AnimatePresence>
    </div>
  )
}

// ─── 单条通知卡片 ──────────────────────────────────
interface CardProps {
  item: NotificationItem
  onDismiss: () => void
}

function NotificationCard({ item, onDismiss }: CardProps) {
  // 关闭按钮可点击
  const isLegendary = item.kind === 'item_drop' && item.rarity === 'legendary'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 360, scale: 0.85 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 360, scale: 0.85 }}
      transition={{ type: 'spring', stiffness: 320, damping: 28 }}
      onClick={onDismiss}
      className="pointer-events-auto cursor-pointer rounded-2xl overflow-hidden relative"
      style={getCardStyle(item)}
      role="status"
    >
      {/* 传说级脉冲光效 */}
      {isLegendary && (
        <motion.span
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'radial-gradient(circle at 50% 50%, rgba(251,191,36,0.3) 0%, transparent 70%)',
          }}
          animate={{ opacity: [0.4, 0.9, 0.4], scale: [0.95, 1.05, 0.95] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
        />
      )}

      <div className="relative flex items-center gap-2.5 p-3">
        {item.kind === 'item_drop' && (
          <>
            <motion.span
              className="text-2xl shrink-0"
              animate={isLegendary ? { scale: [1, 1.15, 1], rotate: [0, 5, -5, 0] } : {}}
              transition={{ duration: 1.2, repeat: Infinity }}
            >
              {item.icon || '📦'}
            </motion.span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] text-cd-text-tertiary">获得道具</span>
                {item.source && (
                  <span className="text-[9px] text-cd-text-tertiary opacity-70">来自 {item.source}</span>
                )}
              </div>
              <div className="text-sm font-semibold truncate" style={{ color: getAccentColor(item) }}>
                {item.itemName}
              </div>
              {item.rarity && (
                <span className="text-[9px] px-1 rounded-lg" style={{
                  background: RARITY_STYLE[item.rarity].color + '22',
                  color: RARITY_STYLE[item.rarity].color,
                }}>
                  {RARITY_STYLE[item.rarity].label}
                </span>
              )}
            </div>
          </>
        )}

        {item.kind === 'level_up' && (
          <>
            <motion.span
              className="text-2xl shrink-0"
              animate={{ scale: [1, 1.2, 1], rotate: [0, 10, -10, 0] }}
              transition={{ duration: 1, repeat: Infinity }}
            >
              🎉
            </motion.span>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] text-cd-text-tertiary">升级了！</div>
              <div className="text-sm font-bold text-amber-400">
                Lv.{item.newLevel}
              </div>
              {item.expAwarded ? (
                <div className="text-[10px] text-cd-text-secondary">+{item.expAwarded} EXP</div>
              ) : null}
            </div>
          </>
        )}

        {item.kind === 'pet_evolution' && (
          <>
            <motion.span
              className="text-2xl shrink-0"
              animate={{ scale: [1, 1.25, 1] }}
              transition={{ duration: 1, repeat: Infinity }}
            >
              ✨
            </motion.span>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] text-cd-text-tertiary">宠物进化</div>
              <div className="text-sm font-bold text-cd-purple truncate">
                {item.message}
              </div>
            </div>
          </>
        )}

        {/* 关闭按钮 */}
        <button
          onClick={(e) => { e.stopPropagation(); onDismiss() }}
          className="shrink-0 text-cd-text-tertiary hover:text-cd-text p-0.5 rounded-lg"
          aria-label="关闭通知"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
    </motion.div>
  )
}

function getAccentColor(item: NotificationItem): string {
  if (item.kind === 'item_drop' && item.rarity) return RARITY_STYLE[item.rarity].color
  if (item.kind === 'level_up') return '#FBBF24'
  if (item.kind === 'pet_evolution') return '#af52de'
  return '#9CA3AF'
}

function getCardStyle(item: NotificationItem): CSSProperties {
  const base: CSSProperties = {
    background: 'var(--cd-card)',
    border: '1px solid var(--cd-border)',
    boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
    backdropFilter: 'blur(12px)',
  }
  if (item.kind === 'item_drop' && item.rarity) {
    const r = RARITY_STYLE[item.rarity]
    base.border = `1.5px solid ${r.border}`
    base.boxShadow = `${r.glow}, 0 8px 32px rgba(0,0,0,0.18)`
  } else if (item.kind === 'level_up') {
    base.border = '1.5px solid rgba(251,191,36,0.7)'
    base.boxShadow = '0 0 24px rgba(251,191,36,0.4), 0 8px 32px rgba(0,0,0,0.18)'
  } else if (item.kind === 'pet_evolution') {
    base.border = '1.5px solid rgba(175,82,222,0.7)'
    base.boxShadow = '0 0 24px rgba(175,82,222,0.4), 0 8px 32px rgba(0,0,0,0.18)'
  }
  return base
}
