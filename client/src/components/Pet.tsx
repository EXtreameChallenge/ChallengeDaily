import { useEffect, useRef, useState, useCallback } from 'react'
import { getTodayStats, getCoachStatus, getPetMood, type CoachStatus, type PetMood } from '../api/client'

// ─── 宠物形象定义 ──────────────────────────────
type PetStyle = 'yuexinmao' | 'codex' | 'claude' | 'cat'

interface PetConfig {
  id: PetStyle
  name: string
  color: string
  accent: string
  width: number
  height: number
}

const PET_CONFIGS: Record<PetStyle, PetConfig> = {
  yuexinmao: { id: 'yuexinmao', name: '月薪帽', color: '#7B68EE', accent: '#FFD93D', width: 160, height: 160 },
  codex: { id: 'codex', name: 'Codex', color: '#19C37D', accent: '#10A37F', width: 160, height: 160 },
  claude: { id: 'claude', name: 'Claude', color: '#D97757', accent: '#CC785C', width: 160, height: 160 },
  cat: { id: 'cat', name: '小黑猫', color: '#7B68EE', accent: '#937CFF', width: 160, height: 160 },
}

const IDLE_MESSAGES = [
  '在吗？', '今天也要加油哦~', '我在这儿陪着你', '喵~', '休息一下吧',
  '记得喝水哦', '有我在，不孤单', '工作辛苦了', '要开心呀',
]

const WORK_MESSAGES = [
  '努力工作中~', '专注模式开启！', '加油加油！', '今天进展不错！',
  '保持节奏~', '你是最棒的！', '再坚持一下~', '效率满满！',
]

const ENCOURAGE_MESSAGES = [
  '你可以的！', '相信自己！', '每一步都算数', '慢慢来，比较快',
  '你已经很棒了', '不要放弃哦', '坚持就是胜利',
]

// P7-3: 情绪状态定义（P12-4: 新增 milestone 庆祝情绪）
type Mood = 'idle' | 'focused' | 'flowing' | 'distracted' | 'overworked' | 'sleepy' | 'milestone'

const MOOD_LABELS: Record<Mood, string> = {
  idle: '悠闲',
  focused: '专注',
  flowing: '心流',
  distracted: '摸鱼中',
  overworked: '过劳',
  sleepy: '困倦',
  milestone: '🎉 庆祝',
}

const MOOD_MESSAGES: Record<Mood, string[]> = {
  idle: ['在吗？', '今天也要加油哦~', '我在这儿陪着你', '喵~'],
  focused: ['专注模式开启！', '加油加油！', '今天进展不错！', '效率满满！'],
  flowing: ['哇，你进入心流了！', '不去打扰你，专注就好~', '这个状态太棒了！', '心流中的你最帅！'],
  distracted: ['嗯…又在摸鱼了？', '回来工作啦~', '我知道你有更好的选择', '要不要试试番茄钟？'],
  overworked: ['该休息了！', '连续工作太久啦', '喝杯水吧~', '身体是革命的本钱哦'],
  sleepy: ['困了吗？', '小憩一下也不错', '记得早点休息~'],
  milestone: ['哇！达成里程碑啦！', '恭喜你，太厉害啦~', '这份坚持，值得庆祝！', '为你骄傲~'],
}

export default function Pet() {
  const [style, setStyle] = useState<PetStyle>(() => {
    const saved = localStorage.getItem('cd_pet_style')
    return (saved as PetStyle) || 'yuexinmao'
  })
  const [hover, setHover] = useState(false)
  const [bubbleText, setBubbleText] = useState('')
  const [bubbleVisible, setBubbleVisible] = useState(false)
  const [currentActivity, setCurrentActivity] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [happy, setHappy] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [eyeBlink, setEyeBlink] = useState(false)
  const [tailWag, setTailWag] = useState(0)
  const [distractionAlert, setDistractionAlert] = useState<{ app: string; count: number } | null>(null)
  const [mood, setMood] = useState<Mood>('idle')
  const [coachStatus, setCoachStatus] = useState<CoachStatus | null>(null)
  const [focusMin, setFocusMin] = useState(0)
  // P12-4: 宠物情绪化数据（来自后端 /api/pet/mood）
  const [streakDays, setStreakDays] = useState(0)
  const [celebrate, setCelebrate] = useState(false)

  const config = PET_CONFIGS[style]

  const dragStartRef = useRef<{ x: number; y: number } | null>(null)
  const bubbleTimer = useRef<number | null>(null)
  const happyTimer = useRef<number | null>(null)
  const blinkTimer = useRef<number | null>(null)
  const tailTimer = useRef<number | null>(null)
  const idleMsgTimer = useRef<number | null>(null)

  const refreshActivity = useCallback(async () => {
    try {
      const stats = await getTodayStats()
      setCurrentActivity(stats.current_activity || null)
      setFocusMin(Math.round(stats.total_duration_min || 0))
    } catch {}
  }, [])

  const showBubble = useCallback((text: string, duration = 3000) => {
    setBubbleText(text)
    setBubbleVisible(true)
    if (bubbleTimer.current) window.clearTimeout(bubbleTimer.current)
    bubbleTimer.current = window.setTimeout(() => setBubbleVisible(false), duration)
  }, [])

  useEffect(() => {
    refreshActivity()
    // 60秒轮询（Pet活动状态不需要高频刷新，Sidebar已有30秒轮询同接口）
    const id = window.setInterval(refreshActivity, 60000)
    return () => window.clearInterval(id)
  }, [refreshActivity])

  // P7-3: 行为教练状态轮询（30秒）+ 情绪联动
  useEffect(() => {
    const pollCoach = async () => {
      try {
        const status = await getCoachStatus()
        setCoachStatus(status)
        // 根据教练状态计算情绪
        if (status.alerts.some(a => a.type === 'overwork')) {
          setMood('overworked')
        } else if (status.in_flow) {
          setMood('flowing')
        } else if (status.distraction_minutes >= 15) {
          setMood('distracted')
        } else if (status.work_minutes >= 25) {
          setMood('focused')
        } else if (!status.current_category) {
          setMood('idle')
        } else {
          setMood(status.distraction_minutes > 0 ? 'distracted' : 'focused')
        }
        // 行为教练告警 → 气泡提示
        if (status.alerts.length > 0) {
          const alert = status.alerts[0]
          showBubble(alert.message, 6000)
        } else if (status.urge_surfing) {
          showBubble(status.urge_surfing.quote, 8000)
        } else if (status.smart_break) {
          // P16-2: 智能休息建议（心流结束后提示）
          showBubble(status.smart_break.message, 7000)
        }
      } catch {}
    }
    pollCoach()
    const id = window.setInterval(pollCoach, 30000)
    return () => window.clearInterval(id)
  }, [showBubble])

  // P12-4: 宠物情绪化 — 轮询 /api/pet/mood（60秒，里程碑优先级最高）
  useEffect(() => {
    let cancelled = false
    const pollPetMood = async () => {
      try {
        const data = await getPetMood()
        if (cancelled) return
        setStreakDays(data.streak_days)
        // 里程碑情绪优先级最高，覆盖教练状态计算的 mood
        if (data.mood === 'milestone') {
          setMood('milestone')
          setCelebrate(true)
          showBubble(data.message, 8000)
          window.setTimeout(() => setCelebrate(false), 6000)
        } else if (data.streak_days > 0 && data.focus_min === 0) {
          // 数据空窗期但历史有打卡 → 悠闲情绪
          setMood('idle')
        }
      } catch {}
    }
    pollPetMood()
    const id = window.setInterval(pollPetMood, 60000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [showBubble])

  useEffect(() => {
    const blink = () => {
      setEyeBlink(true)
      window.setTimeout(() => setEyeBlink(false), 150)
      const nextBlink = 2000 + Math.random() * 4000
      blinkTimer.current = window.setTimeout(blink, nextBlink)
    }
    blinkTimer.current = window.setTimeout(blink, 3000)
    return () => { if (blinkTimer.current) window.clearTimeout(blinkTimer.current) }
  }, [])

  useEffect(() => {
    const wag = () => {
      setTailWag(prev => (prev + 1) % 4)
      tailTimer.current = window.setTimeout(wag, 800)
    }
    tailTimer.current = window.setTimeout(wag, 800)
    return () => { if (tailTimer.current) window.clearTimeout(tailTimer.current) }
  }, [])

  useEffect(() => {
    const showIdle = () => {
      // P7-3: 使用情绪消息池替代固定消息
      const pool = MOOD_MESSAGES[mood] || (currentActivity ? WORK_MESSAGES : IDLE_MESSAGES)
      const msg = pool[Math.floor(Math.random() * pool.length)]
      showBubble(msg, 4000)
      idleMsgTimer.current = window.setTimeout(showIdle, 30000 + Math.random() * 30000)
    }
    idleMsgTimer.current = window.setTimeout(showIdle, 10000)
    return () => { if (idleMsgTimer.current) window.clearTimeout(idleMsgTimer.current) }
  }, [currentActivity, mood])

  useEffect(() => {
    return () => {
      if (happyTimer.current) window.clearTimeout(happyTimer.current)
      if (bubbleTimer.current) window.clearTimeout(bubbleTimer.current)
      if (blinkTimer.current) window.clearTimeout(blinkTimer.current)
      if (tailTimer.current) window.clearTimeout(tailTimer.current)
      if (idleMsgTimer.current) window.clearTimeout(idleMsgTimer.current)
    }
  }, [])

  // 监听分心告警（来自 Focus 番茄钟检测）→ 宠物变红 + 气泡提示
  useEffect(() => {
    if (!window.electronAPI?.onDistractionAlert) return
    window.electronAPI.onDistractionAlert((data) => {
      setDistractionAlert(data)
      showBubble(`别分心！${data.app}`, 5000)
      // 10 秒后自动恢复
      if (happyTimer.current) window.clearTimeout(happyTimer.current)
      happyTimer.current = window.setTimeout(() => setDistractionAlert(null), 10000)
    })
  }, [showBubble])

  const handlePetClick = useCallback(() => {
    if (isDragging) return
    setHappy(true)
    if (happyTimer.current) window.clearTimeout(happyTimer.current)
    happyTimer.current = window.setTimeout(() => setHappy(false), 1000)
    const msg = ENCOURAGE_MESSAGES[Math.floor(Math.random() * ENCOURAGE_MESSAGES.length)]
    showBubble(msg, 3500)
  }, [isDragging, showBubble])

  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('[data-pet-no-drag]')) return
    e.preventDefault()
    dragStartRef.current = { x: e.clientX, y: e.clientY }
    setIsDragging(false)
  }

  useEffect(() => {
    const handleMove = (e: MouseEvent) => {
      if (!dragStartRef.current) return
      const dx = e.clientX - dragStartRef.current.x
      const dy = e.clientY - dragStartRef.current.y
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
        setIsDragging(true)
      }
      if (window.electronAPI?.petWindowDrag) {
        window.electronAPI.petWindowDrag(dx, dy)
      }
      dragStartRef.current = { x: e.clientX, y: e.clientY }
    }
    const handleUp = () => {
      dragStartRef.current = null
      window.setTimeout(() => setIsDragging(false), 50)
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
    showBubble(`切换为${PET_CONFIGS[next].name}~`, 2000)
  }

  const renderPet = () => {
    switch (style) {
      case 'yuexinmao': return <YueXinMao happy={happy} eyeBlink={eyeBlink} tailWag={tailWag} />
      case 'codex': return <CodexPet happy={happy} eyeBlink={eyeBlink} />
      case 'claude': return <ClaudePet happy={happy} eyeBlink={eyeBlink} />
      case 'cat': return <CatPet happy={happy} eyeBlink={eyeBlink} tailWag={tailWag} />
      default: return <YueXinMao happy={happy} eyeBlink={eyeBlink} tailWag={tailWag} />
    }
  }

  return (
    <div
      className="pet-container"
      style={{
        width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'flex-end', paddingBottom: '8px',
        cursor: isDragging ? 'grabbing' : 'grab', position: 'relative', background: 'transparent',
        userSelect: 'none', WebkitUserSelect: 'none',
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setMenuOpen(false) }}
      onMouseDown={handleMouseDown}
      onClick={handlePetClick}
      onContextMenu={(e) => {
        if ((e.target as HTMLElement).closest('[data-pet-no-drag]')) return
        e.preventDefault()
        setMenuOpen(prev => !prev)
      }}
    >
      {/* 气泡 — 在宠物上方 */}
      <div style={{
        position: 'absolute', bottom: '100%', left: '50%',
        transform: `translateX(-50%) translateY(${bubbleVisible ? '0' : '10px'})`,
        opacity: bubbleVisible ? 1 : 0, transition: 'all 0.3s ease',
        marginBottom: '8px', minWidth: '120px', maxWidth: '200px',
        padding: '8px 12px', borderRadius: '12px', fontSize: '12px',
        lineHeight: 1.5, textAlign: 'center', pointerEvents: 'none', zIndex: 100,
        background: 'rgba(30, 30, 40, 0.92)', color: '#fff',
        border: '1px solid rgba(255,255,255,0.1)', boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
        backdropFilter: 'blur(8px)',
      }}>
        {bubbleText}
        <span style={{
          position: 'absolute', left: '50%', top: '100%', transform: 'translateX(-50%)',
          width: 0, height: 0, borderLeft: '6px solid transparent',
          borderRight: '6px solid transparent', borderTop: '6px solid rgba(30, 30, 40, 0.92)',
        }} />
      </div>

      {/* 菜单 */}
      {menuOpen && (
        <div data-pet-no-drag style={{
          position: 'absolute', bottom: '100%', left: '50%', transform: 'translateX(-50%)',
          marginBottom: '8px', padding: '6px', borderRadius: '12px', display: 'flex',
          flexDirection: 'column', gap: '4px', minWidth: '100px', zIndex: 200,
          background: 'rgba(30, 30, 40, 0.95)', border: '1px solid rgba(255,255,255,0.08)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)', backdropFilter: 'blur(12px)',
        }}>
          {(Object.keys(PET_CONFIGS) as PetStyle[]).map(p => (
            <button key={p} data-pet-no-drag onClick={(e) => { e.stopPropagation(); handleStyleChange(p) }}
              style={{
                display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px',
                borderRadius: '8px', border: 'none', fontSize: '12px', cursor: 'pointer',
                background: style === p ? 'rgba(255,255,255,0.1)' : 'transparent',
                color: style === p ? PET_CONFIGS[p].color : '#ccc', transition: 'all 0.2s',
              }}>
              <span style={{ fontSize: '16px' }}>
                {p === 'yuexinmao' ? '🐱' : p === 'codex' ? '💚' : p === 'claude' ? '🟠' : '🐱'}
              </span>
              {PET_CONFIGS[p].name}
            </button>
          ))}
        </div>
      )}

      {/* 宠物本体 */}
      <div style={{
        width: config.width, height: config.height, position: 'relative',
        transition: 'transform 0.2s ease, filter 0.3s ease',
        transform: hover && !isDragging ? 'scale(1.05)' : 'scale(1)',
        filter: distractionAlert ? 'drop-shadow(0 0 8px rgba(239,68,68,0.8)) hue-rotate(-20deg) saturate(1.5)' : 'drop-shadow(0 4px 8px rgba(0,0,0,0.2))',
      }}>
        {hover && (
          <button data-pet-no-drag onClick={(e) => { e.stopPropagation(); window.electronAPI?.togglePet(false) }}
            style={{
              position: 'absolute', top: '-4px', right: '-4px', zIndex: 20, width: '20px', height: '20px',
              borderRadius: '50%', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '12px', cursor: 'pointer', opacity: 0.7, background: 'rgba(60,60,70,0.8)', color: '#aaa',
            }} title="隐藏宠物">×</button>
        )}
        {hover && (
          <button data-pet-no-drag onClick={(e) => { e.stopPropagation(); setMenuOpen(prev => !prev) }}
            style={{
              position: 'absolute', top: '-4px', left: '-4px', zIndex: 20, width: '20px', height: '20px',
              borderRadius: '50%', border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '10px', cursor: 'pointer', opacity: 0.7, background: 'rgba(60,60,70,0.8)', color: '#aaa',
            }} title="切换形象">⚙</button>
        )}
        {renderPet()}
      </div>

      {/* P7-3: 情绪状态指示器 + 专注时长 + 连续打卡（P12-4） */}
      <div style={{
        position: 'absolute', bottom: '2px', left: '50%', transform: 'translateX(-50%)',
        display: 'flex', alignItems: 'center', gap: '4px', padding: '1px 6px',
        borderRadius: '8px', fontSize: '9px', fontWeight: 500, whiteSpace: 'nowrap',
        background: mood === 'distracted' ? 'rgba(239,68,68,0.2)' :
                    mood === 'overworked' ? 'rgba(251,146,60,0.2)' :
                    mood === 'flowing' ? 'rgba(168,85,247,0.2)' :
                    mood === 'focused' ? 'rgba(34,197,94,0.2)' :
                    mood === 'milestone' ? 'rgba(250,204,21,0.25)' :
                    'rgba(120,120,140,0.15)',
        color: mood === 'distracted' ? '#ef4444' :
               mood === 'overworked' ? '#fb923c' :
               mood === 'flowing' ? '#a855f7' :
               mood === 'focused' ? '#22c55e' :
               mood === 'milestone' ? '#facc15' : '#888',
        border: `1px solid ${mood === 'distracted' ? 'rgba(239,68,68,0.3)' :
                          mood === 'overworked' ? 'rgba(251,146,60,0.3)' :
                          mood === 'flowing' ? 'rgba(168,85,247,0.3)' :
                          mood === 'focused' ? 'rgba(34,197,94,0.3)' :
                          mood === 'milestone' ? 'rgba(250,204,21,0.4)' : 'rgba(120,120,140,0.2)'}`,
        pointerEvents: 'none', zIndex: 10,
      }}>
        <span>{MOOD_LABELS[mood]}</span>
        {focusMin > 0 && <span style={{ opacity: 0.6 }}>· {Math.floor(focusMin / 60)}h{focusMin % 60}m</span>}
        {streakDays > 0 && <span style={{ opacity: 0.6 }}>· 🔥{streakDays}d</span>}
      </div>

      {/* P12-4: 里程碑庆祝动画（彩屑飘落） */}
      {celebrate && (
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden', zIndex: 50 }}>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} style={{
              position: 'absolute',
              left: `${(i * 8.33) % 100}%`,
              top: '-10px',
              width: '6px', height: '6px',
              background: ['#fbbf24', '#f87171', '#34d399', '#60a5fa', '#a78bfa', '#f472b6'][i % 6],
              borderRadius: '50%',
              animation: `pet-confetti ${2 + (i % 3) * 0.5}s ease-in ${i * 0.1}s forwards`,
            }} />
          ))}
          <style>{`@keyframes pet-confetti { 0% { transform: translateY(0) rotate(0); opacity: 1 } 100% { transform: translateY(200px) rotate(720deg); opacity: 0 } }`}</style>
        </div>
      )}
    </div>
  )
}

// ─── SVG 形象 ────────────────────────────────────

function YueXinMao({ happy, eyeBlink, tailWag }: { happy: boolean; eyeBlink: boolean; tailWag: number }) {
  const tailAngle = tailWag % 2 === 0 ? 8 : -8
  return (
    <svg viewBox="0 0 160 160" style={{ width: '100%', height: '100%', filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.2))' }}>
      <defs>
        <linearGradient id="yxmBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#9B8AE8" /><stop offset="100%" stopColor="#7B68EE" /></linearGradient>
        <linearGradient id="yxmHat" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#FFD93D" /><stop offset="100%" stopColor="#F0C040" /></linearGradient>
      </defs>
      <g style={{ transformOrigin: '100px 110px', transform: `rotate(${tailAngle}deg)`, transition: 'transform 0.4s ease' }}>
        <path d="M110 110 Q130 100 135 80 Q138 65 125 70" fill="none" stroke="#7B68EE" strokeWidth="7" strokeLinecap="round" />
      </g>
      <ellipse cx="80" cy="105" rx="42" ry="36" fill="url(#yxmBody)" />
      <path d="M42 62 L34 32 L58 48 Z" fill="#7B68EE" />
      <path d="M118 62 L126 32 L102 48 Z" fill="#7B68EE" />
      <ellipse cx="80" cy="38" rx="35" ry="10" fill="#E8A838" />
      <path d="M55 38 L55 22 Q80 12 105 22 L105 38 Z" fill="url(#yxmHat)" />
      <rect x="75" y="12" width="10" height="8" rx="2" fill="#E8A838" />
      <text x="80" y="34" textAnchor="middle" fontSize="10" fontWeight="bold" fill="#8B6914" fontFamily="sans-serif">$</text>
      <ellipse cx="62" cy="78" rx="6" ry={eyeBlink ? '1.5' : '7'} fill="#1A1A1A" style={{ transition: 'ry 0.1s' }} />
      <ellipse cx="98" cy="78" rx="6" ry={eyeBlink ? '1.5' : '7'} fill="#1A1A1A" style={{ transition: 'ry 0.1s' }} />
      {!eyeBlink && <><circle cx="64" cy="75" r="2" fill="#FFF" opacity="0.7" /><circle cx="100" cy="75" r="2" fill="#FFF" opacity="0.7" /></>}
      <circle cx="50" cy="88" r="6" fill="#FF8A80" opacity="0.5" />
      <circle cx="110" cy="88" r="6" fill="#FF8A80" opacity="0.5" />
      <path d={happy ? 'M68 95 Q80 104 92 95' : 'M74 97 Q80 100 86 97'} fill="none" stroke="#1A1A1A" strokeWidth="2.5" strokeLinecap="round" />
      <ellipse cx="52" cy="132" rx="8" ry="6" fill="#9B8AE8" />
      <ellipse cx="108" cy="132" rx="8" ry="6" fill="#9B8AE8" />
      <g stroke="#FFF" strokeWidth="1.2" strokeLinecap="round" opacity="0.5">
        <line x1="38" y1="82" x2="22" y2="78" /><line x1="38" y1="88" x2="22" y2="92" />
        <line x1="122" y1="82" x2="138" y2="78" /><line x1="122" y1="88" x2="138" y2="92" />
      </g>
    </svg>
  )
}

function CodexPet({ happy, eyeBlink }: { happy: boolean; eyeBlink: boolean }) {
  return (
    <svg viewBox="0 0 160 160" style={{ width: '100%', height: '100%', filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.2))' }}>
      <defs>
        <linearGradient id="codexBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2DD4A0" /><stop offset="100%" stopColor="#19C37D" /></linearGradient>
      </defs>
      <line x1="80" y1="28" x2="80" y2="12" stroke="#19C37D" strokeWidth="3" strokeLinecap="round" />
      <circle cx="80" cy="10" r="5" fill="#FFD93D"><animate attributeName="opacity" values="1;0.5;1" dur="2s" repeatCount="indefinite" /></circle>
      <rect x="38" y="32" width="84" height="72" rx="20" fill="url(#codexBody)" />
      <rect x="48" y="44" width="64" height="44" rx="12" fill="#0D3328" />
      <rect x="58" y="56" width="12" height={eyeBlink ? '2' : '10'} rx="3" fill={happy ? '#2DD4A0' : '#FFF'} style={{ transition: 'height 0.1s' }} />
      <rect x="90" y="56" width="12" height={eyeBlink ? '2' : '10'} rx="3" fill={happy ? '#2DD4A0' : '#FFF'} style={{ transition: 'height 0.1s' }} />
      {happy ? <path d="M70 74 Q80 82 90 74" fill="none" stroke="#2DD4A0" strokeWidth="2.5" strokeLinecap="round" /> : <rect x="74" y="74" width="12" height="3" rx="1.5" fill="#FFF" opacity="0.6" />}
      <path d="M32 52 Q22 64 32 76" fill="none" stroke="#19C37D" strokeWidth="6" strokeLinecap="round" />
      <path d="M128 52 Q138 64 128 76" fill="none" stroke="#19C37D" strokeWidth="6" strokeLinecap="round" />
      <rect x="56" y="100" width="16" height="14" rx="5" fill="#17A86B" />
      <rect x="88" y="100" width="16" height="14" rx="5" fill="#17A86B" />
      <circle cx="80" cy="108" r="3" fill="#FFD93D"><animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite" /></circle>
    </svg>
  )
}

function ClaudePet({ happy, eyeBlink }: { happy: boolean; eyeBlink: boolean }) {
  return (
    <svg viewBox="0 0 160 160" style={{ width: '100%', height: '100%', filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.2))' }}>
      <defs>
        <linearGradient id="claudeBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#E88B6F" /><stop offset="100%" stopColor="#D97757" /></linearGradient>
      </defs>
      <path d="M110 110 Q130 95 128 75 Q126 60 115 65" fill="none" stroke="#D97757" strokeWidth="8" strokeLinecap="round">
        <animateTransform attributeName="transform" type="rotate" values="0 110 110; 8 110 110; 0 110 110" dur="2s" repeatCount="indefinite" />
      </path>
      <ellipse cx="80" cy="105" rx="40" ry="34" fill="url(#claudeBody)" />
      <path d="M44 58 L36 30 L60 46 Z" fill="#D97757" />
      <path d="M116 58 L124 30 L100 46 Z" fill="#D97757" />
      <ellipse cx="62" cy="72" rx="6" ry={eyeBlink ? '1.5' : '7'} fill="#1A1A1A" style={{ transition: 'ry 0.1s' }} />
      <ellipse cx="98" cy="72" rx="6" ry={eyeBlink ? '1.5' : '7'} fill="#1A1A1A" style={{ transition: 'ry 0.1s' }} />
      {!eyeBlink && <><circle cx="64" cy="69" r="2" fill="#FFF" opacity="0.7" /><circle cx="100" cy="69" r="2" fill="#FFF" opacity="0.7" /></>}
      <circle cx="50" cy="82" r="6" fill="#FF8A80" opacity="0.4" />
      <circle cx="110" cy="82" r="6" fill="#FF8A80" opacity="0.4" />
      <path d={happy ? 'M70 90 Q80 98 90 90' : 'M76 92 Q80 95 84 92'} fill="none" stroke="#1A1A1A" strokeWidth="2.5" strokeLinecap="round" />
      <ellipse cx="52" cy="130" rx="8" ry="6" fill="#E88B6F" />
      <ellipse cx="108" cy="130" rx="8" ry="6" fill="#E88B6F" />
      <g opacity="0.6"><polygon points="30,40 32,45 37,45 33,48 35,53 30,50 25,53 27,48 23,45 28,45" fill="#FFD93D" />
      <polygon points="130,35 131,38 134,38 132,40 133,43 130,41 127,43 128,40 126,38 129,38" fill="#FFD93D" /></g>
    </svg>
  )
}

function CatPet({ happy, eyeBlink, tailWag }: { happy: boolean; eyeBlink: boolean; tailWag: number }) {
  const tailAngle = tailWag % 2 === 0 ? 8 : -8
  return (
    <svg viewBox="0 0 160 160" style={{ width: '100%', height: '100%', filter: 'drop-shadow(0 4px 8px rgba(0,0,0,0.2))' }}>
      <defs>
        <linearGradient id="catBody2" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#937CFF" /><stop offset="100%" stopColor="#7B68EE" /></linearGradient>
      </defs>
      <g style={{ transformOrigin: '100px 110px', transform: `rotate(${tailAngle}deg)`, transition: 'transform 0.4s ease' }}>
        <path d="M110 110 Q130 100 128 80 Q126 65 115 70" fill="none" stroke="#7B68EE" strokeWidth="8" strokeLinecap="round" />
      </g>
      <ellipse cx="80" cy="105" rx="42" ry="36" fill="url(#catBody2)" />
      <path d="M42 58 L34 30 L58 46 Z" fill="#7B68EE" />
      <path d="M118 58 L126 30 L102 46 Z" fill="#7B68EE" />
      <ellipse cx="62" cy="72" rx="6" ry={eyeBlink ? '1.5' : '7'} fill="#1A1A1A" style={{ transition: 'ry 0.1s' }} />
      <ellipse cx="98" cy="72" rx="6" ry={eyeBlink ? '1.5' : '7'} fill="#1A1A1A" style={{ transition: 'ry 0.1s' }} />
      {!eyeBlink && <><circle cx="64" cy="69" r="2" fill="#FFF" opacity="0.7" /><circle cx="100" cy="69" r="2" fill="#FFF" opacity="0.7" /></>}
      <circle cx="50" cy="82" r="6" fill="#FF8A80" opacity="0.5" />
      <circle cx="110" cy="82" r="6" fill="#FF8A80" opacity="0.5" />
      <path d={happy ? 'M68 90 Q80 98 92 90' : 'M74 92 Q80 95 86 92'} fill="none" stroke="#1A1A1A" strokeWidth="2.5" strokeLinecap="round" />
      <ellipse cx="52" cy="130" rx="8" ry="6" fill="#937CFF" />
      <ellipse cx="108" cy="130" rx="8" ry="6" fill="#937CFF" />
      <g stroke="#FFF" strokeWidth="1.2" strokeLinecap="round" opacity="0.5">
        <line x1="38" y1="78" x2="22" y2="74" /><line x1="38" y1="84" x2="22" y2="88" />
        <line x1="122" y1="78" x2="138" y2="74" /><line x1="122" y1="84" x2="138" y2="88" />
      </g>
    </svg>
  )
}
