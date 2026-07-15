import { useState, useEffect, useCallback, useRef } from 'react'
import { Trophy, Lock, Sparkles, Crown, Calendar, History, Share2, Download, X } from 'lucide-react'
import { getAchievements, checkAchievements, getQuote, getSeason, getSeasonHistory, type Achievement, type SeasonData, type SeasonHistoryItem } from '../api/client'
import { useToast } from '../components/Toast'

const ALL_BADGES = [
  { code: 'first_pomodoro', name: '初心者', desc: '完成第一个番茄钟', icon: '🌱', hidden: false, group: '专注' },
  { code: 'pomodoro_100', name: '百斩', desc: '累计完成100个番茄钟', icon: '💯', hidden: false, group: '专注' },
  { code: 'pomodoro_1000', name: '千时', desc: '累计专注1000小时', icon: '⏰', hidden: false, group: '专注' },
  { code: 'streak_7', name: '连续7天', desc: '连续7天完成专注', icon: '🔥', hidden: false, group: '专注' },
  { code: 'streak_30', name: '坚持不懈', desc: '连续30天完成专注', icon: '💎', hidden: false, group: '专注' },
  { code: 'deep_master', name: '深度大师', desc: '单日深度工作≥4小时', icon: '🧠', hidden: false, group: '深度' },
  { code: 'early_bird', name: '早起鸟', desc: '6:00前开始专注', icon: '🐦', hidden: false, group: '深度' },
  { code: 'night_owl', name: '夜猫子', desc: '23:00后仍在专注', icon: '🦉', hidden: false, group: '深度' },
  { code: 'full_clear', name: '全勤奖', desc: '一天完成所有待办', icon: '✨', hidden: false, group: '效率' },
  { code: 'efficiency_king', name: '效率之王', desc: '日专注效率≥80%', icon: '👑', hidden: false, group: '效率' },
  // P6-4：隐藏彩蛋成就（未解锁时显示为 ???）
  { code: 'polymath', name: '多面手', desc: '一天内涉及8个以上分类', icon: '🎭', hidden: true, group: '彩蛋' },
  { code: 'zen_master', name: '禅定', desc: '连续4小时不切换分类', icon: '🧘', hidden: true, group: '彩蛋' },
  { code: 'century_mark', name: '百日修行', desc: '累计记录100天活动', icon: '🏛️', hidden: true, group: '彩蛋' },
  // P13-3：新增 3 个隐藏彩蛋成就
  { code: 'night_owl_7', name: '夜猫子修行', desc: '连续7天23点后仍在专注', icon: '🌙', hidden: true, group: '彩蛋' },
  { code: 'habit_master', name: '习惯养成大师', desc: '连续30天打卡任意习惯', icon: '⭐', hidden: true, group: '彩蛋' },
  { code: 'ai_explorer', name: 'AI 探索者', desc: '累计与 AI 对话 100 次', icon: '🤖', hidden: true, group: '彩蛋' },
]

const BADGE_GROUPS = ['专注', '深度', '效率', '彩蛋']

export default function Achievements() {
  const [achievements, setAchievements] = useState<Achievement[]>([])
  const [quote, setQuote] = useState('')
  const [newlyUnlocked, setNewlyUnlocked] = useState<string[]>([])
  const [season, setSeason] = useState<SeasonData | null>(null)
  const [seasonHistory, setSeasonHistory] = useState<SeasonHistoryItem[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [shareModal, setShareModal] = useState(false)
  const [shareImg, setShareImg] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const toast = useToast()
  const unlockTimerRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    return () => { if (unlockTimerRef.current) clearTimeout(unlockTimerRef.current) }
  }, [])

  const load = useCallback(async () => {
    try {
      const [aRes, qRes, sRes] = await Promise.all([
        getAchievements(),
        getQuote(),
        getSeason().catch(() => null),
      ])
      setAchievements(aRes.achievements)
      setQuote(qRes.quote)
      if (sRes) setSeason(sRes)
    } catch { toast.error('加载成就数据失败') }
  }, [toast])

  // P13-3：加载赛季历史
  const loadHistory = useCallback(async () => {
    try {
      const res = await getSeasonHistory(6)
      setSeasonHistory(res.history || [])
    } catch { /* 静默失败 */ }
  }, [])
  useEffect(() => { loadHistory() }, [loadHistory])

  useEffect(() => { load() }, [load])

  // P15-2：生成分享卡片（Canvas 绘制，无需外部依赖）
  const handleShare = async () => {
    setShareModal(true)
    setGenerating(true)
    setShareImg(null)
    try {
      // 等待模态框渲染
      await new Promise(r => setTimeout(r, 50))
      const canvas = document.createElement('canvas')
      const W = 1080, H = 1350
      canvas.width = W
      canvas.height = H
      const ctx = canvas.getContext('2d')
      if (!ctx) throw new Error('Canvas 不可用')

      const unlocked = achievements.filter(a => a.unlocked_at)
      const unlockedCount = unlocked.length
      const totalCount = ALL_BADGES.length
      const completionRate = totalCount > 0 ? Math.round(unlockedCount / totalCount * 100) : 0

      // 背景渐变
      const bg = ctx.createLinearGradient(0, 0, W, H)
      bg.addColorStop(0, '#1a1330')
      bg.addColorStop(0.5, '#2d1b4e')
      bg.addColorStop(1, '#1a1330')
      ctx.fillStyle = bg
      ctx.fillRect(0, 0, W, H)

      // 装饰光晕
      const glow = ctx.createRadialGradient(W / 2, 380, 50, W / 2, 380, 400)
      glow.addColorStop(0, 'rgba(240, 160, 48, 0.3)')
      glow.addColorStop(1, 'rgba(240, 160, 48, 0)')
      ctx.fillStyle = glow
      ctx.fillRect(0, 0, W, H)

      // 标题
      ctx.textAlign = 'center'
      ctx.fillStyle = '#fbbf24'
      ctx.font = 'bold 56px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText('🏆 我的成就墙', W / 2, 180)

      ctx.fillStyle = '#a78bfa'
      ctx.font = '28px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText('ChallengeDaily · 时间见证坚持', W / 2, 230)

      // 主数据圆环
      const cx = W / 2, cy = 520, r = 180
      ctx.strokeStyle = 'rgba(255,255,255,0.1)'
      ctx.lineWidth = 28
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.stroke()

      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 28
      ctx.lineCap = 'round'
      ctx.beginPath()
      ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + (completionRate / 100) * Math.PI * 2)
      ctx.stroke()

      ctx.fillStyle = '#fff'
      ctx.font = 'bold 96px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(`${completionRate}%`, cx, cy + 20)
      ctx.fillStyle = '#a78bfa'
      ctx.font = '26px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText('成就完成率', cx, cy + 60)

      // 统计行
      ctx.fillStyle = '#fff'
      ctx.font = 'bold 42px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(`${unlockedCount} / ${totalCount}`, W / 2, 820)
      ctx.fillStyle = '#9ca3af'
      ctx.font = '22px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText('已解锁徽章', W / 2, 860)

      // 已解锁徽章网格（最多展示 12 个）
      const showBadges = unlocked.slice(0, 12)
      const cols = 6
      const rows = Math.ceil(showBadges.length / cols)
      const badgeSize = 80
      const gapX = 24
      const gapY = 24
      const totalW = cols * badgeSize + (cols - 1) * gapX
      const startX = (W - totalW) / 2 + badgeSize / 2
      const startY = 940
      ctx.font = '48px sans-serif'
      ctx.textBaseline = 'middle'
      showBadges.forEach((a, i) => {
        const col = i % cols
        const row = Math.floor(i / cols)
        const x = startX + col * (badgeSize + gapX)
        const y = startY + row * (badgeSize + gapY)
        // 背景圆
        ctx.fillStyle = 'rgba(255,255,255,0.08)'
        ctx.beginPath()
        ctx.arc(x, y, badgeSize / 2, 0, Math.PI * 2)
        ctx.fill()
        // emoji
        ctx.fillText(a.icon || '🏆', x, y)
      })
      ctx.textBaseline = 'alphabetic'

      // 底部签名
      ctx.fillStyle = '#6b7280'
      ctx.font = '22px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.textAlign = 'center'
      const dateStr = new Date().toISOString().slice(0, 10)
      ctx.fillText(`${dateStr} · 每一付认真都值得被记录`, W / 2, H - 60)

      // 转为图片
      const dataUrl = canvas.toDataURL('image/png')
      setShareImg(dataUrl)
    } catch (e) {
      console.error(e)
      toast.error('卡片生成失败')
      setShareModal(false)
    } finally {
      setGenerating(false)
    }
  }

  const handleDownloadShare = () => {
    if (!shareImg) return
    const a = document.createElement('a')
    a.href = shareImg
    a.download = `challenge-daily-achievements-${new Date().toISOString().slice(0, 10)}.png`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    toast.success('已保存到下载目录')
  }

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
        <div className="flex items-center gap-3">
          <button
            onClick={handleShare}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-purple-500/15 text-purple-400 rounded-lg border border-purple-500/25 hover:bg-purple-500/25 transition"
          >
            <Share2 size={14} /> 生成分享卡片
          </button>
          <span className="text-sm text-cd-text-secondary">{achievements.length}/{ALL_BADGES.length} 已解锁</span>
        </div>
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

      {/* 徽章网格 — P13-3：按分组展示 */}
      {BADGE_GROUPS.map(group => {
        const groupBadges = ALL_BADGES.filter(b => b.group === group)
        const groupUnlocked = groupBadges.filter(b => unlockedCodes.has(b.code)).length
        return (
          <div key={group} className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-cd-text-secondary">{group}类</h2>
              <span className="text-xs text-cd-text-tertiary">{groupUnlocked}/{groupBadges.length}</span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {groupBadges.map(badge => {
                const unlocked = unlockedCodes.has(badge.code)
                const isHidden = badge.hidden && !unlocked
                return (
                  <div key={badge.code} className={`rounded-xl p-4 border text-center transition ${
                    unlocked ? 'bg-cd-bg-card border-gold/20' : isHidden ? 'bg-cd-bg-card border-white/5 opacity-30' : 'bg-cd-bg-card border-white/5 opacity-40'
                  }`}>
                    <div className="text-4xl mb-2">{unlocked ? badge.icon : isHidden ? '❓' : '🔒'}</div>
                    <div className={`text-sm font-medium ${unlocked ? 'text-cd-text' : 'text-cd-text-secondary'}`}>
                      {isHidden ? '???' : badge.name}
                    </div>
                    <div className="text-xs text-cd-text-secondary mt-1">{isHidden ? '隐藏成就，等待解锁' : badge.desc}</div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      {/* P10-4：本月赛季成就 */}
      {season && (
        <div className="mt-8 bg-gradient-to-br from-purple-500/10 to-gold/5 rounded-xl p-5 border border-purple-400/20">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-cd-text flex items-center gap-2">
              <Crown size={20} className="text-gold" /> 本月赛季
              <span className="text-xs text-cd-text-tertiary font-normal flex items-center gap-1 ml-2">
                <Calendar size={12} />
                {season.start_date} ~ {season.end_date}
              </span>
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-sm text-cd-text-secondary">
                {season.unlocked_count}/{season.total_count} 已解锁
              </span>
              {/* P13-3：赛季历史切换按钮 */}
              {seasonHistory.length > 0 && (
                <button
                  onClick={() => setShowHistory(!showHistory)}
                  className="flex items-center gap-1 text-xs text-cd-purple hover:text-cd-purple/80 transition"
                >
                  <History size={12} />
                  {showHistory ? '收起历史' : '查看历史'}
                </button>
              )}
            </div>
          </div>

          {/* P13-3：赛季历史展示 */}
          {showHistory && seasonHistory.length > 0 && (
            <div className="mb-4 bg-cd-bg-input/50 rounded-lg p-3 border border-white/5">
              <div className="text-xs text-cd-text-tertiary mb-2">近 {seasonHistory.length} 个月赛季回顾</div>
              <div className="flex flex-wrap gap-2">
                {seasonHistory.map(h => (
                  <div key={h.season_key} className="rounded-md px-3 py-1.5 bg-cd-bg-secondary border border-white/5 text-xs">
                    <span className="text-cd-text-secondary">{h.season_key}</span>
                    <span className="text-cd-text-tertiary mx-1">·</span>
                    <span className="text-gold">{h.unlocked_count}/{h.total_count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {season.achievements.map(a => (
              <div key={a.key} className={`rounded-lg p-3 border transition ${
                a.unlocked
                  ? 'bg-gold/10 border-gold/30'
                  : 'bg-cd-bg-input border-white/5'
              }`}>
                <div className="flex items-start justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{a.unlocked ? '🏆' : '🎯'}</span>
                    <div>
                      <div className={`text-sm font-medium ${a.unlocked ? 'text-gold' : 'text-cd-text'}`}>
                        {a.name}
                      </div>
                      <div className="text-[10px] text-cd-text-tertiary">{a.desc}</div>
                    </div>
                  </div>
                  {a.unlocked && (
                    <span className="text-[10px] text-gold bg-gold/10 px-2 py-0.5 rounded">已解锁</span>
                  )}
                </div>
                {/* 进度条 */}
                <div className="mt-2">
                  <div className="flex items-center justify-between text-[10px] text-cd-text-tertiary mb-1">
                    <span>{a.current} / {a.target}</span>
                    <span>{a.progress_pct}%</span>
                  </div>
                  <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${a.unlocked ? 'bg-gold' : 'bg-purple-400'}`}
                      style={{ width: `${a.progress_pct}%` }}
                    />
                  </div>
                </div>
                {a.unlocked && a.reward && (
                  <div className="mt-2 text-[10px] text-gold/80">奖励称号：{a.reward}</div>
                )}
              </div>
            ))}
          </div>
          <div className="mt-3 text-[10px] text-cd-text-tertiary text-center">
            每月 1 号重置赛季，挑战自己赢取月度专属称号
          </div>
        </div>
      )}

      {/* P15-2：分享卡片模态框 */}
      {shareModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setShareModal(false)}
        >
          <div
            className="bg-cd-bg-card rounded-2xl border border-cd-border p-6 max-w-md w-full"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-cd-text flex items-center gap-2">
                <Share2 size={18} className="text-purple-400" /> 成就分享卡片
              </h3>
              <button
                onClick={() => setShareModal(false)}
                className="text-cd-text-tertiary hover:text-cd-text"
              >
                <X size={18} />
              </button>
            </div>
            {generating ? (
              <div className="flex flex-col items-center justify-center py-16">
                <div className="w-8 h-8 border-3 border-purple-400 border-t-transparent rounded-full animate-spin mb-3" />
                <p className="text-sm text-cd-text-tertiary">正在生成精美卡片...</p>
              </div>
            ) : shareImg ? (
              <>
                <img
                  src={shareImg}
                  alt="成就分享卡片"
                  className="w-full rounded-lg border border-white/5"
                />
                <div className="mt-4 flex gap-2">
                  <button
                    onClick={handleDownloadShare}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-cd-green text-white rounded-lg text-sm font-medium hover:opacity-90 transition"
                  >
                    <Download size={14} /> 保存图片
                  </button>
                  <button
                    onClick={() => {
                      if (navigator.share && shareImg) {
                        fetch(shareImg)
                          .then(r => r.blob())
                          .then(blob => {
                            const file = new File([blob], 'achievements.png', { type: 'image/png' })
                            navigator.share({ title: '我的成就墙', files: [file] }).catch(() => {})
                          })
                      } else {
                        handleDownloadShare()
                      }
                    }}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-purple-500/15 text-purple-400 rounded-lg text-sm font-medium border border-purple-500/25 hover:bg-purple-500/25 transition"
                  >
                    <Share2 size={14} /> 分享
                  </button>
                </div>
                <p className="mt-3 text-[10px] text-cd-text-tertiary text-center">
                  长按图片或点击保存按钮下载到本地
                </p>
              </>
            ) : (
              <div className="text-center py-10 text-cd-text-tertiary text-sm">
                卡片生成失败，请重试
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
