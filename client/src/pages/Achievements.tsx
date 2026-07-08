import { useState, useEffect, useCallback, useRef } from 'react'
import { Trophy, Lock, Sparkles } from 'lucide-react'
import { getAchievements, checkAchievements, getQuote, type Achievement } from '../api/client'
import { useToast } from '../components/Toast'

const ALL_BADGES = [
  { code: 'first_pomodoro', name: '初心者', desc: '完成第一个番茄钟', icon: '🌱' },
  { code: 'pomodoro_100', name: '百斩', desc: '累计完成100个番茄钟', icon: '💯' },
  { code: 'pomodoro_1000', name: '千时', desc: '累计专注1000小时', icon: '⏰' },
  { code: 'streak_7', name: '连续7天', desc: '连续7天完成专注', icon: '🔥' },
  { code: 'streak_30', name: '坚持不懈', desc: '连续30天完成专注', icon: '💎' },
  { code: 'deep_master', name: '深度大师', desc: '单日深度工作≥4小时', icon: '🧠' },
  { code: 'early_bird', name: '早起鸟', desc: '6:00前开始专注', icon: '🐦' },
  { code: 'night_owl', name: '夜猫子', desc: '23:00后仍在专注', icon: '🦉' },
  { code: 'full_clear', name: '全勤奖', desc: '一天完成所有待办', icon: '✨' },
  { code: 'efficiency_king', name: '效率之王', desc: '日专注效率≥80%', icon: '👑' },
]

export default function Achievements() {
  const [achievements, setAchievements] = useState<Achievement[]>([])
  const [quote, setQuote] = useState('')
  const [newlyUnlocked, setNewlyUnlocked] = useState<string[]>([])
  const toast = useToast()
  // 用于在组件卸载时清理 newlyUnlocked 的 setTimeout
  const unlockTimerRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    return () => { if (unlockTimerRef.current) clearTimeout(unlockTimerRef.current) }
  }, [])

  const load = useCallback(async () => {
    try {
      const [aRes, qRes] = await Promise.all([getAchievements(), getQuote()])
      setAchievements(aRes.achievements)
      setQuote(qRes.quote)
    } catch { toast.error('加载成就数据失败') }
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleCheck = async () => {
    try {
      const { unlocked } = await checkAchievements()
      if (unlocked.length > 0) {
        setNewlyUnlocked(unlocked.map(u => `${u.icon} ${u.name}`))
        if (unlockTimerRef.current) clearTimeout(unlockTimerRef.current)
        unlockTimerRef.current = window.setTimeout(() => setNewlyUnlocked([]), 5000)
        load()
      }
    } catch { toast.error('检查成就失败') }
  }

  useEffect(() => { const t = setTimeout(handleCheck, 2000); return () => clearTimeout(t) }, [])

  const unlockedCodes = new Set(achievements.map(a => a.code))

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <Trophy className="text-gold" /> 成就墙
        </h1>
        <span className="text-sm text-cd-text-secondary">{achievements.length}/{ALL_BADGES.length} 已解锁</span>
      </div>

      {/* 格言 */}
      {quote && (
        <div className="bg-gradient-to-r from-cd-accent/10 to-gold/10 rounded-xl p-4 border border-cd-accent/20 mb-6">
          <p className="text-base text-cd-text italic leading-relaxed">{quote}</p>
        </div>
      )}

      {/* 新解锁通知 */}
      {newlyUnlocked.length > 0 && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4 mb-6">
          <div className="flex items-center gap-2 text-green-400 font-medium mb-1">
            <Sparkles size={18} /> 新成就解锁！
          </div>
          {newlyUnlocked.map((u, i) => <div key={i} className="text-cd-text">{u}</div>)}
        </div>
      )}

      {/* 徽章网格 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {ALL_BADGES.map(badge => {
          const unlocked = unlockedCodes.has(badge.code)
          return (
            <div key={badge.code} className={`rounded-xl p-4 border text-center transition ${
              unlocked ? 'bg-cd-bg-card border-gold/20' : 'bg-cd-bg-card border-white/5 opacity-40'
            }`}>
              <div className="text-4xl mb-2">{unlocked ? badge.icon : '🔒'}</div>
              <div className={`text-sm font-medium ${unlocked ? 'text-cd-text' : 'text-cd-text-secondary'}`}>{badge.name}</div>
              <div className="text-xs text-cd-text-secondary mt-1">{badge.desc}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
