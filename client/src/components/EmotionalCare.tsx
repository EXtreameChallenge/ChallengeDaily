import { useEffect, useMemo, useRef, useState } from 'react'
import { Sparkles, Heart, PartyPopper, Coffee, Quote, Sunrise } from 'lucide-react'
import { getQuote, getTodayStats, getTrendStats, getMorningInsights, type MorningInsight } from '../api/client'

/**
 * P8-2：情感化设计组件
 * 集成三块能力：
 *  1. 每日一句（带渐变背景与图标）
 *  2. 里程碑庆祝（连续打卡 N 天 / 累计 N 小时 / 今日首个番茄等触发庆祝条幅）
 *  3. 低谷关怀（当前时长过短或纯摸鱼时显示温馨提示，避免"效率低"等负面表述）
 *
 * 用户偏好：活泼可爱温馨，不肉麻；上午必须鼓励性；不出现"效率低/有点散"等词。
 */

// ─── 低谷关怀文案池 ──────────────────────────────
const LOWPOINT_MESSAGES = [
  '今天才刚开始，慢慢热身也挺好的呀~',
  '不着急，先泡杯茶，把状态找回来',
  '每个高效的一天，都从一杯水开始',
  '心还没到位？没关系，先打开一个文档热热身',
  '今天即使只专注 25 分钟，也是一次小小的胜利',
  '节奏由你定义，不必和别人比较',
  '小步前进，比较快~',
  '记得对自己温柔一点',
]

// ─── 里程碑触发条件 ──────────────────────────────
interface Milestone {
  icon: typeof Sparkles
  text: string
  color: string
}

function pickMilestone(opts: {
  todayMin: number
  streakDays: number
  totalActiveDays: number
  captureCount: number
}): Milestone | null {
  const { todayMin, streakDays, totalActiveDays, captureCount } = opts
  // 优先级：连续打卡 > 累计活跃 > 当日成就
  if (streakDays >= 30) {
    return { icon: PartyPopper, text: `哇！已连续专注 ${streakDays} 天，这节奏太棒了！`, color: 'rgba(168,85,247,0.18)' }
  }
  if (streakDays >= 7) {
    return { icon: Sparkles, text: `连续 ${streakDays} 天打卡中，习惯正在养成~`, color: 'rgba(34,197,94,0.18)' }
  }
  if (totalActiveDays >= 100) {
    return { icon: PartyPopper, text: `累计活跃 ${totalActiveDays} 天，每一笔记录都在塑造更好的你`, color: 'rgba(251,146,60,0.18)' }
  }
  if (todayMin >= 240) {
    return { icon: Sparkles, text: `今天已专注 ${Math.floor(todayMin / 60)} 小时，深度工作满分！`, color: 'rgba(34,197,94,0.18)' }
  }
  if (todayMin >= 120 && captureCount >= 30) {
    return { icon: Heart, text: `今天的节奏很稳，继续这样的好状态~`, color: 'rgba(236,72,153,0.18)' }
  }
  return null
}

function pickLowpoint(todayMin: number, hour: number): string | null {
  // 仅在上午到下午早段（6-16 点）且今日时长较短时显示
  if (hour < 6 || hour > 16) return null
  if (todayMin >= 60) return null // 已专注 1 小时以上不再提示
  return LOWPOINT_MESSAGES[Math.floor(Math.random() * LOWPOINT_MESSAGES.length)]
}

export default function EmotionalCare() {
  const [quote, setQuote] = useState('')
  const [todayMin, setTodayMin] = useState(0)
  const [captureCount, setCaptureCount] = useState(0)
  const [streakDays, setStreakDays] = useState(0)
  const [totalActiveDays, setTotalActiveDays] = useState(0)
  const [showCelebration, setShowCelebration] = useState(false)
  const [morningInsights, setMorningInsights] = useState<MorningInsight[]>([])
  const prevMilestoneKey = useRef<string>('')

  useEffect(() => {
    let cancelled = false
    const fetchAll = async () => {
      try {
        const [q, stats, trend, insights] = await Promise.all([
          getQuote().catch(() => ({ quote: '' })),
          getTodayStats().catch(() => null),
          getTrendStats(30).catch(() => ({ trend: [] as any[] })),
          getMorningInsights().catch(() => ({ insights: [] as MorningInsight[] })),
        ])
        if (cancelled) return
        setQuote((q as any)?.quote || '')
        if (stats) {
          setTodayMin(Math.round(stats.total_duration_min || 0))
          setCaptureCount(stats.total_activities || 0)
        }
        // 计算连续打卡天数（最近 30 天内末端连续有数据的长度）
        const trendArr = (trend as any)?.trend || []
        let streak = 0
        for (let i = trendArr.length - 1; i >= 0; i--) {
          if ((trendArr[i]?.duration_min || 0) > 0) streak++
          else break
        }
        setStreakDays(streak)
        const activeDays = trendArr.filter((d: any) => (d?.duration_min || 0) > 0).length
        setTotalActiveDays(activeDays)
        // P9-2：晨报洞察
        setMorningInsights((insights as any)?.insights || [])
      } catch {}
    }
    fetchAll()
    // 每 5 分钟刷新一次
    const id = window.setInterval(fetchAll, 300000)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [])

  const milestone = useMemo(
    () => pickMilestone({ todayMin, streakDays, totalActiveDays, captureCount }),
    [todayMin, streakDays, totalActiveDays, captureCount],
  )

  // 里程碑首次出现时弹出庆祝动画（基于 key 去重）
  useEffect(() => {
    if (!milestone) return
    const key = milestone.text
    if (key !== prevMilestoneKey.current) {
      prevMilestoneKey.current = key
      setShowCelebration(true)
      const t = window.setTimeout(() => setShowCelebration(false), 4000)
      return () => window.clearTimeout(t)
    }
  }, [milestone])

  const hour = new Date().getHours()
  const lowpointMsg = useMemo(() => pickLowpoint(todayMin, hour), [todayMin, hour])

  if (!quote && !milestone && !lowpointMsg && morningInsights.length === 0) return null

  return (
    <div className="space-y-2">
      {/* P9-2：晨报洞察 */}
      {morningInsights.length > 0 && (
        <div className="space-y-1.5">
          {morningInsights.map((ins, i) => {
            const colorMap: Record<string, string> = {
              positive: 'rgba(34,197,94,0.12)',
              suggestion: 'rgba(59,130,246,0.12)',
              warning: 'rgba(251,146,60,0.12)',
              care: 'rgba(236,72,153,0.12)',
              fun: 'rgba(168,85,247,0.12)',
            }
            const borderMap: Record<string, string> = {
              positive: 'rgba(34,197,94,0.3)',
              suggestion: 'rgba(59,130,246,0.3)',
              warning: 'rgba(251,146,60,0.3)',
              care: 'rgba(236,72,153,0.3)',
              fun: 'rgba(168,85,247,0.3)',
            }
            return (
              <div
                key={i}
                className="flex items-start gap-2 px-4 py-2.5 rounded-xl border"
                style={{
                  background: colorMap[ins.type] || colorMap.suggestion,
                  borderColor: borderMap[ins.type] || borderMap.suggestion,
                }}
              >
                <Sunrise size={14} className="text-amber-500 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-cd-text">{ins.title}</p>
                  <p className="text-xs text-cd-text-secondary mt-0.5 leading-relaxed">{ins.body}</p>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 每日一句 */}
      {quote && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-purple-400/20 bg-gradient-to-r from-purple-500/8 via-pink-500/5 to-amber-500/8">
          <Quote size={14} className="text-purple-400 shrink-0" />
          <p className="text-sm text-cd-text-secondary italic flex-1 truncate">{quote}</p>
        </div>
      )}

      {/* 里程碑庆祝 */}
      {milestone && (
        <div
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-transparent transition-all"
          style={{
            background: milestone.color,
            borderColor: milestone.color.replace(/0\.18\)/, '0.35)'),
            animation: showCelebration ? 'celebrate-pop 0.6s ease-out' : undefined,
          }}
        >
          <milestone.icon size={16} className="shrink-0" style={{ color: milestone.color.replace(/0\.18\)/, '1)') }} />
          <p className="text-sm text-cd-text font-medium flex-1">{milestone.text}</p>
        </div>
      )}

      {/* 低谷关怀 */}
      {lowpointMsg && !milestone && (
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-amber-400/20 bg-gradient-to-r from-amber-500/8 to-orange-500/8">
          <Coffee size={14} className="text-amber-500 shrink-0" />
          <p className="text-sm text-cd-text-secondary flex-1">{lowpointMsg}</p>
        </div>
      )}

      <style>{`
        @keyframes celebrate-pop {
          0% { transform: scale(0.95); opacity: 0; }
          50% { transform: scale(1.03); opacity: 1; }
          100% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  )
}
