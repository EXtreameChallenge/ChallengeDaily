import { useEffect, useRef, useState, useCallback } from 'react'
import { getTodayStats } from '../api/client'

type PetStyle = 'cat' | 'robot' | 'ghost'

interface PetProps {
  visible: boolean
  onToggle?: (visible: boolean) => void
}

const PET_STYLES: { id: PetStyle; name: string; color: string }[] = [
  { id: 'cat', name: '小黑猫', color: '#7B68EE' },
  { id: 'robot', name: '机器人', color: '#5B8DEF' },
  { id: 'ghost', name: '小幽灵', color: '#00CEC9' },
]

const REST_MESSAGES = [
  '该休息一下啦~',
  '喝口水吧',
  '起来走走吧',
  '放松一下眼睛~',
]

const WORK_MESSAGES = [
  '努力工作中~',
  '专注模式开启！',
  '加油加油！',
  '今天进展不错！',
  '保持节奏~',
]

export default function Pet({ visible, onToggle }: PetProps) {
  const [style, setStyle] = useState<PetStyle>(() => {
    const saved = localStorage.getItem('cd_pet_style')
    return (saved as PetStyle) || 'cat'
  })
  const [position, setPosition] = useState<{ x: number; y: number }>(() => {
    const saved = localStorage.getItem('cd_pet_position')
    if (saved) {
      try {
        return JSON.parse(saved)
      } catch {}
    }
    return { x: 24, y: 120 }
  })
  const positionRef = useRef(position)
  useEffect(() => { positionRef.current = position }, [position])

  const [hover, setHover] = useState(false)
  const [bubbleText, setBubbleText] = useState('')
  const [bubbleVisible, setBubbleVisible] = useState(false)
  const [currentActivity, setCurrentActivity] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [happy, setHappy] = useState(false)

  const dragRef = useRef<{ startX: number; startY: number; initialX: number; initialY: number } | null>(null)
  const didDragRef = useRef(false)
  const bubbleTimer = useRef<number | null>(null)

  // 读取当前工作状态
  const refreshActivity = useCallback(async () => {
    try {
      const stats = await getTodayStats()
      setCurrentActivity(stats.current_activity || null)
    } catch {
      // 后端不可达时保持旧值
    }
  }, [])

  useEffect(() => {
    if (!visible) return
    refreshActivity()
    const id = window.setInterval(refreshActivity, 30000)
    return () => window.clearInterval(id)
  }, [visible, refreshActivity])

  // 初始打招呼
  useEffect(() => {
    if (!visible) return
    const timer = window.setTimeout(() => {
      showBubble(PET_STYLES.find(p => p.id === style)?.name + ' 来陪你~' || '陪你工作~')
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [visible, style])

  const showBubble = useCallback((text: string, duration = 3000) => {
    setBubbleText(text)
    setBubbleVisible(true)
    if (bubbleTimer.current) window.clearTimeout(bubbleTimer.current)
    bubbleTimer.current = window.setTimeout(() => setBubbleVisible(false), duration)
  }, [])

  // 点击宠物显示气泡
  const handlePetClick = useCallback(() => {
    if (didDragRef.current) return
    setHappy(true)
    window.setTimeout(() => setHappy(false), 800)

    const pool = currentActivity ? [currentActivity, ...WORK_MESSAGES] : WORK_MESSAGES
    const msg = pool[Math.floor(Math.random() * pool.length)]
    showBubble(msg, 3500)
  }, [currentActivity, showBubble])

  // 拖拽逻辑
  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('[data-pet-no-drag]')) return
    e.preventDefault()
    didDragRef.current = false
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      initialX: position.x,
      initialY: position.y,
    }
  }

  useEffect(() => {
    const handleMove = (e: MouseEvent) => {
      if (!dragRef.current) return
      const dx = e.clientX - dragRef.current.startX
      const dy = e.clientY - dragRef.current.startY
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
        didDragRef.current = true
      }
      const newX = Math.max(0, Math.min(window.innerWidth - 120, dragRef.current.initialX + dx))
      const newY = Math.max(48, Math.min(window.innerHeight - 120, dragRef.current.initialY + dy))
      setPosition({ x: newX, y: newY })
    }
    const handleUp = () => {
      if (dragRef.current) {
        localStorage.setItem('cd_pet_position', JSON.stringify(positionRef.current))
      }
      dragRef.current = null
      window.setTimeout(() => {
        didDragRef.current = false
      }, 60)
    }
    window.addEventListener('mousemove', handleMove)
    window.addEventListener('mouseup', handleUp)
    return () => {
      window.removeEventListener('mousemove', handleMove)
      window.removeEventListener('mouseup', handleUp)
    }
  }, [])

  const handleStyleChange = (next: PetStyle) => {
    setStyle(next)
    localStorage.setItem('cd_pet_style', next)
    setMenuOpen(false)
    const name = PET_STYLES.find(p => p.id === next)?.name || ''
    showBubble(`切换为${name}~`, 2000)
  }

  if (!visible) return null

  return (
    <div
      className="fixed z-[9999] select-none"
      style={{ left: position.x, top: position.y }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setMenuOpen(false) }}
    >
      {/* 气泡 */}
      <div
        className={`absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full min-w-[140px] max-w-[260px] px-3 py-2 rounded-xl text-xs leading-relaxed text-center shadow-lg pointer-events-none transition-all duration-300 ${
          bubbleVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
        }`}
        style={{
          background: 'var(--cd-card)',
          color: 'var(--cd-text)',
          border: '1px solid var(--cd-border)',
          boxShadow: 'var(--cd-shadow)',
        }}
      >
        {bubbleText}
        <span
          className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0"
          style={{
            borderLeft: '6px solid transparent',
            borderRight: '6px solid transparent',
            borderTop: '6px solid var(--cd-border)',
          }}
        />
      </div>

      {/* 形象切换菜单 */}
      {menuOpen && (
        <div
          className="absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full mb-2 px-1.5 py-1.5 rounded-xl flex flex-col gap-0.5 min-w-[90px]"
          style={{
            background: 'var(--cd-card)',
            border: '1px solid var(--cd-border)',
            boxShadow: 'var(--cd-shadow)',
          }}
        >
          {PET_STYLES.map(p => (
            <button
              key={p.id}
              data-pet-no-drag
              onClick={() => handleStyleChange(p.id)}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-colors ${
                style === p.id ? 'font-medium' : ''
              }`}
              style={{
                background: style === p.id ? 'var(--cd-selected)' : 'transparent',
                color: style === p.id ? p.color : 'var(--cd-text)',
              }}
            >
              <span className="text-base leading-none">{p.id === 'cat' ? '🐱' : p.id === 'robot' ? '🤖' : '👻'}</span>
              {p.name}
            </button>
          ))}
        </div>
      )}

      {/* 宠物本体 */}
      <div
        className="relative w-20 h-20 cursor-grab active:cursor-grabbing"
        onMouseDown={handleMouseDown}
        onClick={handlePetClick}
        onContextMenu={(e) => {
          if ((e.target as HTMLElement).closest('[data-pet-no-drag]')) return
          e.preventDefault()
          setMenuOpen(prev => !prev)
        }}
      >
        {/* 关闭按钮 */}
        {hover && (
          <button
            data-pet-no-drag
            onClick={(e) => {
              e.stopPropagation()
              onToggle?.(false)
            }}
            className="absolute -top-1 -right-1 z-20 w-5 h-5 rounded-full flex items-center justify-center text-[10px] opacity-80 hover:opacity-100 transition-opacity"
            style={{ background: 'var(--cd-bg-tertiary)', color: 'var(--cd-text-tertiary)' }}
            title="隐藏宠物"
          >
            ×
          </button>
        )}

        {/* 设置按钮 */}
        {hover && (
          <button
            data-pet-no-drag
            onClick={(e) => {
              e.stopPropagation()
              setMenuOpen(prev => !prev)
            }}
            className="absolute -top-1 -left-1 z-20 w-5 h-5 rounded-full flex items-center justify-center text-[10px] opacity-80 hover:opacity-100 transition-opacity"
            style={{ background: 'var(--cd-bg-tertiary)', color: 'var(--cd-text-tertiary)' }}
            title="切换形象"
          >
            ⚙
          </button>
        )}

        <div className={`w-full h-full transition-transform duration-200 ${hover ? 'scale-110' : ''} ${happy ? 'animate-pet-bounce' : 'animate-pet-float'}`}>
          {style === 'cat' && <CatSvg happy={happy || hover} />}
          {style === 'robot' && <RobotSvg happy={happy || hover} />}
          {style === 'ghost' && <GhostSvg happy={happy || hover} />}
        </div>
      </div>

      {/* 定时休息提醒 */}
      <RestReminder onShow={showBubble} />
    </div>
  )
}

// ─── 定时休息提醒 ──────────────────────────────
function RestReminder({ onShow }: { onShow: (text: string, duration?: number) => void }) {
  useEffect(() => {
    const id = window.setInterval(() => {
      const msg = REST_MESSAGES[Math.floor(Math.random() * REST_MESSAGES.length)]
      onShow(msg, 5000)
    }, 45 * 60 * 1000)
    return () => window.clearInterval(id)
  }, [onShow])
  return null
}

// ─── SVG 形象 ──────────────────────────────────
function CatSvg({ happy }: { happy: boolean }) {
  return (
    <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-md">
      <defs>
        <linearGradient id="catBody" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#937CFF" />
          <stop offset="100%" stopColor="#7B68EE" />
        </linearGradient>
      </defs>
      {/* 尾巴 */}
      <path
        d="M70 70 Q90 60 88 40 Q86 25 75 30"
        fill="none"
        stroke="#7B68EE"
        strokeWidth="8"
        strokeLinecap="round"
        className="origin-bottom-left animate-pet-tail"
      />
      {/* 身体 */}
      <ellipse cx="50" cy="62" rx="34" ry="30" fill="url(#catBody)" />
      {/* 耳朵 */}
      <path d="M24 38 L18 14 L40 28 Z" fill="#7B68EE" />
      <path d="M76 38 L82 14 L60 28 Z" fill="#7B68EE" />
      {/* 眼睛 */}
      <g className="animate-pet-blink">
        <ellipse cx="38" cy="52" rx="5" ry={happy ? '3' : '6'} fill="#1A1A1A" />
        <ellipse cx="62" cy="52" rx="5" ry={happy ? '3' : '6'} fill="#1A1A1A" />
      </g>
      {/* 腮红 */}
      <circle cx="30" cy="62" r="4" fill="#FF8A80" opacity="0.6" />
      <circle cx="70" cy="62" r="4" fill="#FF8A80" opacity="0.6" />
      {/* 嘴巴 */}
      <path
        d={happy ? 'M42 68 Q50 76 58 68' : 'M46 70 Q50 73 54 70'}
        fill="none"
        stroke="#1A1A1A"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      {/* 胡须 */}
      <g stroke="#FFF" strokeWidth="1.5" strokeLinecap="round" opacity="0.7">
        <line x1="20" y1="58" x2="8" y2="55" />
        <line x1="20" y1="64" x2="8" y2="66" />
        <line x1="80" y1="58" x2="92" y2="55" />
        <line x1="80" y1="64" x2="92" y2="66" />
      </g>
    </svg>
  )
}

function RobotSvg({ happy }: { happy: boolean }) {
  return (
    <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-md">
      <defs>
        <linearGradient id="robotBody" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#74B9FF" />
          <stop offset="100%" stopColor="#5B8DEF" />
        </linearGradient>
      </defs>
      {/* 天线 */}
      <line x1="50" y1="20" x2="50" y2="8" stroke="#5B8DEF" strokeWidth="3" strokeLinecap="round" />
      <circle cx="50" cy="6" r="4" fill="#FFD93D" className="animate-pulse" />
      {/* 身体 */}
      <rect x="22" y="28" width="56" height="52" rx="14" fill="url(#robotBody)" />
      {/* 屏幕脸 */}
      <rect x="30" y="38" width="40" height="26" rx="8" fill="#1A1A1A" />
      {/* 眼睛 */}
      <g className="animate-pet-blink">
        <circle cx="40" cy="51" r="4" fill={happy ? '#00CEC9' : '#FFF'} />
        <circle cx="60" cy="51" r="4" fill={happy ? '#00CEC9' : '#FFF'} />
      </g>
      {/* 嘴巴/状态灯 */}
      {happy ? (
        <path d="M44 60 Q50 65 56 60" fill="none" stroke="#00CEC9" strokeWidth="2" strokeLinecap="round" />
      ) : (
        <rect x="46" y="60" width="8" height="2" rx="1" fill="#FFF" />
      )}
      {/* 手臂 */}
      <path d="M16 46 Q10 54 16 62" fill="none" stroke="#5B8DEF" strokeWidth="5" strokeLinecap="round" />
      <path d="M84 46 Q90 54 84 62" fill="none" stroke="#5B8DEF" strokeWidth="5" strokeLinecap="round" />
      {/* 腿 */}
      <rect x="34" y="78" width="10" height="10" rx="3" fill="#4A90E2" />
      <rect x="56" y="78" width="10" height="10" rx="3" fill="#4A90E2" />
    </svg>
  )
}

function GhostSvg({ happy }: { happy: boolean }) {
  return (
    <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-md">
      <defs>
        <linearGradient id="ghostBody" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#A8F0E8" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#00CEC9" stopOpacity="0.85" />
        </linearGradient>
      </defs>
      {/* 身体 */}
      <path
        d="M30 80 Q25 70 25 50 Q25 20 50 20 Q75 20 75 50 Q75 70 70 80 Q63 72 58 80 Q53 72 48 80 Q43 72 38 80 Q33 72 30 80 Z"
        fill="url(#ghostBody)"
      />
      {/* 眼睛 */}
      <g className="animate-pet-blink">
        <circle cx="40" cy="46" r="5" fill="#1A1A1A" />
        <circle cx="60" cy="46" r="5" fill="#1A1A1A" />
      </g>
      {/* 腮红 */}
      <ellipse cx="32" cy="54" rx="4" ry="2.5" fill="#FF8A80" opacity="0.5" />
      <ellipse cx="68" cy="54" rx="4" ry="2.5" fill="#FF8A80" opacity="0.5" />
      {/* 嘴巴 */}
      <path
        d={happy ? 'M44 58 Q50 64 56 58' : 'M46 60 Q50 58 54 60'}
        fill="none"
        stroke="#1A1A1A"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      {/* 小星星装饰 */}
      <circle cx="22" cy="36" r="2" fill="#FFF" opacity="0.8" className="animate-pulse" />
      <circle cx="78" cy="40" r="1.5" fill="#FFF" opacity="0.6" className="animate-pulse" style={{ animationDelay: '0.5s' }} />
    </svg>
  )
}
