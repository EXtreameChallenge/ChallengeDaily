import { useEffect, useReducer, useRef, useMemo, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useEventStream } from '../hooks/useEventStream'
import { useGrowthStore } from '../stores/growthStore'

// ─── 配置 ──────────────────────────────────────
const FLOAT_DURATION_MS = 1400
const MAX_INDICATORS = 6
const LOW_HP_THRESHOLD = 0.3 // HP 低于 30% 触发警告

type IndicatorKind = 'hp' | 'mp'

interface Indicator {
  id: number
  kind: IndicatorKind
  delta: number
  reason?: string
}

type Action =
  | { type: 'add'; indicator: Indicator }
  | { type: 'remove'; id: number }

interface State {
  indicators: Indicator[]
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'add': {
      const next = [...state.indicators, action.indicator]
      // 限制最大同时显示数量
      while (next.length > MAX_INDICATORS) next.shift()
      return { indicators: next }
    }
    case 'remove':
      return { indicators: state.indicators.filter(i => i.id !== action.id) }
    default:
      return state
  }
}

export default function HpMpChangeIndicator() {
  const { event } = useEventStream()
  const hp = useGrowthStore(s => s.hp)
  const maxHp = useGrowthStore(s => s.maxHp)
  const applySseEvent = useGrowthStore(s => s.applySseEvent)
  const [state, dispatch] = useReducer(reducer, { indicators: [] })
  const idCounter = useRef(0)
  const timersRef = useRef(new Map<number, number>())
  // 记录上次的 hp，用于本地变化检测（兼容后端不发 hp_change 但 hp 字段变化的情况）
  const lastHpRef = useRef<number>(hp)

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

  const addIndicator = useCallback((kind: IndicatorKind, delta: number, reason?: string) => {
    if (delta === 0) return
    const id = ++idCounter.current
    dispatch({ type: 'add', indicator: { id, kind, delta, reason } })
    const t = window.setTimeout(() => dismiss(id), FLOAT_DURATION_MS)
    timersRef.current.set(id, t)
  }, [dismiss])

  // 保持 hp/maxHp ref 最新，供 SSE handler 读取但不触发 effect 重执行
  const hpRef = useRef(hp)
  const maxHpRef = useRef(maxHp)
  useEffect(() => { hpRef.current = hp; maxHpRef.current = maxHp }, [hp, maxHp])

  // 监听 SSE hp_change 事件（不依赖 hp/maxHp，防止 applySseEvent 触发循环）
  useEffect(() => {
    if (!event || event.type !== 'hp_change') return
    const data = event.data || {}
    const newHp = (data.hp as number) ?? hpRef.current
    const newMaxHp = (data.max_hp as number) ?? maxHpRef.current
    const delta = (data.delta as number) ?? (newHp - lastHpRef.current)
    const reason = (data.reason as string) || undefined
    // 同步 store
    applySseEvent('hp_change', data)
    if (delta !== 0) addIndicator('hp', delta, reason)
    lastHpRef.current = newHp
    void newMaxHp
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event, applySseEvent, addIndicator])

  // 监听 store 中 hp 的变化（兜底：后端只更新 store 不发 SSE 的情况）
  useEffect(() => {
    if (hp === lastHpRef.current) return
    const delta = hp - lastHpRef.current
    if (delta !== 0) addIndicator('hp', delta)
    lastHpRef.current = hp
  }, [hp, addIndicator])

  // 危险状态计算
  const hpRatio = maxHp > 0 ? hp / maxHp : 1
  const isLowHp = hpRatio > 0 && hpRatio < LOW_HP_THRESHOLD && hp > 0
  const isDead = hp <= 0 && maxHp > 0

  return (
    <>
      {/* 浮动数字指示器 */}
      <div
        className="fixed top-1/2 left-1/2 z-[150] pointer-events-none"
        style={{ transform: 'translate(-50%, -50%)' }}
        aria-live="polite"
        aria-atomic="true"
      >
        <AnimatePresence>
          {state.indicators.map(ind => (
            <FloatingNumber key={ind.id} indicator={ind} />
          ))}
        </AnimatePresence>
      </div>

      {/* HP 低警告：屏幕边缘红色脉冲 */}
      <AnimatePresence>
        {isLowHp && !isDead && (
          <motion.div
            className="fixed inset-0 z-[140] pointer-events-none"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0.3, 0.6, 0.3] }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
            style={{
              boxShadow: 'inset 0 0 120px rgba(239,68,68,0.6), inset 0 0 60px rgba(239,68,68,0.4)',
              border: '3px solid rgba(239,68,68,0.5)',
            }}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      {/* 虚弱状态：HP 归 0 时灰色滤镜 */}
      <AnimatePresence>
        {isDead && (
          <motion.div
            className="fixed inset-0 z-[145] pointer-events-none"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            style={{
              background: 'rgba(50, 50, 50, 0.35)',
              backdropFilter: 'grayscale(0.6) brightness(0.85)',
              WebkitBackdropFilter: 'grayscale(0.6) brightness(0.85)',
            }}
            aria-hidden="true"
          >
            <div className="absolute inset-0 flex items-center justify-center">
              <motion.div
                className="text-center"
                initial={{ scale: 0.5, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.4 }}
              >
                <div className="text-5xl mb-2 opacity-80">💀</div>
                <div className="text-lg font-bold text-red-300" style={{ textShadow: '0 2px 12px rgba(0,0,0,0.6)' }}>
                  虚弱状态
                </div>
                <div className="text-xs text-red-200/70 mt-1">HP 已耗尽，请休息恢复</div>
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

// ─── 浮动数字 ──────────────────────────────────────
interface FloatingNumberProps {
  indicator: Indicator
}

function FloatingNumber({ indicator }: FloatingNumberProps) {
  // 计算偏移：多条同时显示时错开位置
  const offsetX = useMemo(() => (Math.random() - 0.5) * 80, [])
  const offsetY = useMemo(() => (Math.random() - 0.5) * 40, [])

  const isPositive = indicator.delta > 0
  const color = indicator.kind === 'hp'
    ? (isPositive ? '#22C55E' : '#EF4444')
    : (isPositive ? '#3B82F6' : '#6366F1')

  return (
    <motion.div
      layout
      className="absolute font-black select-none"
      style={{
        color,
        textShadow: `0 0 12px ${color}99, 0 2px 4px rgba(0,0,0,0.5)`,
        fontSize: '28px',
        left: offsetX,
        top: offsetY,
        fontFamily: '"Anthropic Sans", system-ui, sans-serif',
      }}
      initial={{ opacity: 0, y: 20, scale: 0.5 }}
      animate={{ opacity: [0, 1, 1, 0], y: -80, scale: [0.5, 1.2, 1, 0.9] }}
      exit={{ opacity: 0 }}
      transition={{ duration: FLOAT_DURATION_MS / 1000, ease: 'easeOut', times: [0, 0.2, 0.7, 1] }}
    >
      {isPositive ? '+' : ''}{indicator.delta}
      {indicator.reason && (
        <span className="block text-[10px] font-medium opacity-80" style={{ color }}>
          {indicator.reason}
        </span>
      )}
    </motion.div>
  )
}
