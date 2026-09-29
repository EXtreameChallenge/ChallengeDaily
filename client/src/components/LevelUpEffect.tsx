import { useEffect, useReducer, useRef, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useEventStream } from '../hooks/useEventStream'
import { useGrowthStore } from '../stores/growthStore'

// ─── 升级特效配置 ──────────────────────────────────
const PARTICLE_COUNT = 18
const DURATION_MS = 2500

interface LevelUpInstance {
  id: number
  newLevel: number
  expAwarded: number
}

type Action =
  | { type: 'show'; instance: LevelUpInstance }
  | { type: 'hide'; id: number }

interface State {
  current: LevelUpInstance | null
  queue: LevelUpInstance[]
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'show': {
      // 如果当前已有特效在播放，加入队列
      if (state.current) {
        return { current: state.current, queue: [...state.queue, action.instance] }
      }
      return { current: action.instance, queue: state.queue }
    }
    case 'hide': {
      // 隐藏当前，从队列取下一个
      const [next, ...rest] = state.queue
      return { current: next ?? null, queue: rest }
    }
    default:
      return state
  }
}

export default function LevelUpEffect() {
  const { event } = useEventStream()
  const applySseEvent = useGrowthStore(s => s.applySseEvent)
  const [state, dispatch] = useReducer(reducer, { current: null, queue: [] })
  const idCounter = useRef(0)
  const hideTimer = useRef<number | null>(null)

  // 清理定时器
  useEffect(() => {
    return () => {
      if (hideTimer.current) window.clearTimeout(hideTimer.current)
    }
  }, [])

  // 当 current 变化时启动/重置定时器
  useEffect(() => {
    if (state.current) {
      if (hideTimer.current) window.clearTimeout(hideTimer.current)
      hideTimer.current = window.setTimeout(() => {
        dispatch({ type: 'hide', id: state.current!.id })
      }, DURATION_MS)
    } else {
      if (hideTimer.current) window.clearTimeout(hideTimer.current)
    }
  }, [state.current])

  // 监听 SSE level_up 事件
  useEffect(() => {
    if (!event || event.type !== 'level_up') return
    const data = event.data || {}
    const newLevel = (data.new_level as number) || 0
    const expAwarded = (data.exp_awarded as number) || 0
    if (!newLevel) return
    // 同步更新 store
    applySseEvent('level_up', data)
    dispatch({
      type: 'show',
      instance: { id: ++idCounter.current, newLevel, expAwarded },
    })
  }, [event, applySseEvent])

  return (
    <AnimatePresence>
      {state.current && (
        <LevelUpOverlay
          key={state.current.id}
          instance={state.current}
        />
      )}
    </AnimatePresence>
  )
}

// ─── 全屏升级特效层 ─────────────────────────────────
interface OverlayProps {
  instance: LevelUpInstance
}

function LevelUpOverlay({ instance }: OverlayProps) {
  // 预生成粒子角度（避免每次渲染随机）
  const particles = useMemo(() => {
    return Array.from({ length: PARTICLE_COUNT }).map((_, i) => {
      const angle = (i / PARTICLE_COUNT) * Math.PI * 2 + (Math.random() - 0.5) * 0.3
      const distance = 180 + Math.random() * 120
      return {
        id: i,
        x: Math.cos(angle) * distance,
        y: Math.sin(angle) * distance,
        size: 4 + Math.random() * 6,
        delay: Math.random() * 0.2,
        rotate: Math.random() * 720 - 360,
      }
    })
  }, [])

  return (
    <motion.div
      className="fixed inset-0 z-[200] flex items-center justify-center pointer-events-none"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      aria-hidden="true"
    >
      {/* 全屏金色光芒爆发 */}
      <motion.div
        className="absolute inset-0"
        initial={{ opacity: 0 }}
        animate={{ opacity: [0, 0.6, 0.3, 0] }}
        transition={{ duration: DURATION_MS / 1000, times: [0, 0.15, 0.6, 1] }}
        style={{
          background: 'radial-gradient(circle at 50% 50%, rgba(251,191,36,0.55) 0%, rgba(255,149,0,0.3) 25%, transparent 60%)',
        }}
      />

      {/* 金色光环扩散 */}
      <motion.div
        className="absolute rounded-full"
        style={{
          width: 100,
          height: 100,
          border: '3px solid rgba(251,191,36,0.8)',
          boxShadow: '0 0 40px rgba(251,191,36,0.6)',
        }}
        initial={{ scale: 0, opacity: 1 }}
        animate={{ scale: [0, 8, 12], opacity: [1, 0.4, 0] }}
        transition={{ duration: 1.4, ease: 'easeOut' }}
      />

      {/* 第二层光环 */}
      <motion.div
        className="absolute rounded-full"
        style={{
          width: 60,
          height: 60,
          border: '2px solid rgba(255,149,0,0.7)',
        }}
        initial={{ scale: 0, opacity: 1 }}
        animate={{ scale: [0, 10, 14], opacity: [1, 0.3, 0] }}
        transition={{ duration: 1.6, ease: 'easeOut', delay: 0.15 }}
      />

      {/* 粒子飞散 */}
      {particles.map(p => (
        <motion.div
          key={p.id}
          className="absolute rounded-full"
          style={{
            width: p.size,
            height: p.size,
            background: p.id % 3 === 0 ? '#FBBF24' : p.id % 3 === 1 ? '#FF9500' : '#FFE680',
            boxShadow: `0 0 ${p.size * 2}px rgba(251,191,36,0.8)`,
          }}
          initial={{ x: 0, y: 0, opacity: 1, scale: 1 }}
          animate={{
            x: p.x,
            y: p.y,
            opacity: [1, 1, 0],
            scale: [1, 1.2, 0.3],
            rotate: p.rotate,
          }}
          transition={{
            duration: 1.6,
            delay: p.delay,
            ease: 'easeOut',
            times: [0, 0.5, 1],
          }}
        />
      ))}

      {/* 中央文字：LEVEL UP! + 等级数字 */}
      <div className="relative text-center">
        <motion.div
          className="text-5xl sm:text-6xl font-black tracking-wider"
          style={{
            background: 'linear-gradient(180deg, #FFE680 0%, #FBBF24 50%, #FF9500 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            textShadow: '0 0 40px rgba(251,191,36,0.6)',
            fontFamily: '"Anthropic Sans", system-ui, sans-serif',
          }}
          initial={{ scale: 0.3, opacity: 0, y: 30 }}
          animate={{ scale: [0.3, 1.2, 1], opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        >
          LEVEL UP!
        </motion.div>

        <motion.div
          className="mt-3 text-3xl sm:text-4xl font-bold text-amber-300"
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: [0, 1.3, 1], opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.25, ease: 'easeOut' }}
          style={{ textShadow: '0 0 20px rgba(251,191,36,0.8)' }}
        >
          Lv.{instance.newLevel}
        </motion.div>

        {instance.expAwarded > 0 && (
          <motion.div
            className="mt-1 text-sm text-amber-200/80 font-medium"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            +{instance.expAwarded} EXP
          </motion.div>
        )}
      </div>

      {/* 顶部底部金色装饰线 */}
      <motion.div
        className="absolute left-0 right-0 h-px"
        style={{ top: '30%', background: 'linear-gradient(90deg, transparent, rgba(251,191,36,0.6), transparent)' }}
        initial={{ scaleX: 0, opacity: 0 }}
        animate={{ scaleX: 1, opacity: [0, 1, 0] }}
        transition={{ duration: 1.2, delay: 0.2 }}
      />
      <motion.div
        className="absolute left-0 right-0 h-px"
        style={{ bottom: '30%', background: 'linear-gradient(90deg, transparent, rgba(255,149,0,0.6), transparent)' }}
        initial={{ scaleX: 0, opacity: 0 }}
        animate={{ scaleX: 1, opacity: [0, 1, 0] }}
        transition={{ duration: 1.2, delay: 0.3 }}
      />
    </motion.div>
  )
}
