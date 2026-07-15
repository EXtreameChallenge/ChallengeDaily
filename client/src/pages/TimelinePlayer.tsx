import { useState, useEffect, useCallback, useRef } from 'react'
import { Play, Pause, RotateCcw, ChevronLeft, ChevronRight, Loader2, Sparkles, Flame, Trophy, Calendar, Clock } from 'lucide-react'
import { getRecentHeatmap, getAchievements, getQuote } from '../api/client'

interface YearSlide {
  type: 'cover' | 'streak' | 'active_days' | 'focus_hours' | 'achievements' | 'quote' | 'end'
  title: string
  emoji: string
  value?: string | number
  subtitle?: string
  detail?: string
  color: string
}

export default function TimelinePlayer() {
  const [loading, setLoading] = useState(true)
  const [slides, setSlides] = useState<YearSlide[]>([])
  const [current, setCurrent] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [year] = useState(() => new Date().getFullYear())
  const playTimerRef = useRef<number | undefined>(undefined)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // 拉取近 365 天热力图数据 + 成就 + 格言
      const [heatmapRes, achRes, quoteRes] = await Promise.all([
        getRecentHeatmap(120).catch(() => ({ days: 0, data: [] })),
        getAchievements().catch(() => ({ achievements: [] })),
        getQuote().catch(() => ({ quote: '' })),
      ])
      const days = heatmapRes.data || []
      const totalMin = days.reduce((s, d) => s + (d.total_min || 0), 0)
      const totalHours = Math.round(totalMin / 60)
      const activeDays = days.filter(d => (d.total_min || 0) > 0).length
      // 计算当前连续天数
      let streak = 0
      const today = new Date()
      for (let i = 0; i < days.length; i++) {
        const d = new Date(today)
        d.setDate(today.getDate() - i)
        const ds = d.toISOString().slice(0, 10)
        const day = days.find(x => x.date === ds)
        if (day && day.total_min > 0) streak++
        else if (i > 0) break
      }
      const unlocked = (achRes.achievements || []).filter(a => a.unlocked_at)
      const topApp = days
        .map(d => d.top_app)
        .filter(Boolean)
        .reduce<Record<string, number>>((acc, app) => { acc[app] = (acc[app] || 0) + 1; return acc }, {})
      const favApp = Object.entries(topApp).sort((a, b) => b[1] - a[1])[0]?.[0] || '—'

      const built: YearSlide[] = [
        { type: 'cover', title: `我的 ${year}`, emoji: '🎬', subtitle: '年度时间线回放', detail: '一键回顾这一年你的专注与成长', color: '#7B68EE' },
        { type: 'focus_hours', title: '总专注时长', emoji: '⏰', value: `${totalHours}`, subtitle: '小时', detail: `近 ${days.length} 天累计的专注时间，相当于 ${Math.round(totalHours / 24)} 个完整日夜`, color: '#22c55e' },
        { type: 'active_days', title: '活跃天数', emoji: '📅', value: activeDays, subtitle: '天', detail: `记录了至少一次专注活动的天数，覆盖率 ${days.length > 0 ? Math.round(activeDays / days.length * 100) : 0}%`, color: '#3b82f6' },
        { type: 'streak', title: '当前连续', emoji: '🔥', value: streak, subtitle: '天', detail: streak > 0 ? '正在燃烧的连续专注记录，继续保持！' : '今天开始新的连续记录吧', color: '#f97316' },
        { type: 'achievements', title: '已解锁成就', emoji: '🏆', value: unlocked.length, subtitle: '枚', detail: unlocked.slice(0, 5).map(a => `${a.icon} ${a.name}`).join(' · ') || '继续努力解锁更多成就', color: '#fbbf24' },
        { type: 'quote', title: '今日格言', emoji: '✨', subtitle: quoteRes.quote || '不积跬步，无以至千里。', detail: '愿你在新的一年继续前行', color: '#a855f7' },
        { type: 'end', title: '未完待续', emoji: '🚀', subtitle: `${year + 1}，再出发`, detail: '时间会见证每一份坚持，期待你创造更多可能', color: '#ec4899' },
      ]
      setSlides(built)
    } finally {
      setLoading(false)
    }
  }, [year])

  useEffect(() => { load() }, [load])

  // 自动播放
  useEffect(() => {
    if (!playing) {
      if (playTimerRef.current) { window.clearTimeout(playTimerRef.current); playTimerRef.current = undefined }
      return
    }
    if (current >= slides.length - 1) {
      setPlaying(false)
      return
    }
    playTimerRef.current = window.setTimeout(() => {
      setCurrent(c => Math.min(c + 1, slides.length - 1))
    }, 3500)
    return () => { if (playTimerRef.current) window.clearTimeout(playTimerRef.current) }
  }, [playing, current, slides.length])

  const handlePlay = () => {
    if (current >= slides.length - 1) setCurrent(0)
    setPlaying(p => !p)
  }
  const handleReset = () => { setPlaying(false); setCurrent(0) }
  const goPrev = () => { setPlaying(false); setCurrent(c => Math.max(0, c - 1)) }
  const goNext = () => { setPlaying(false); setCurrent(c => Math.min(slides.length - 1, c + 1)) }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-6 h-6 text-cd-green animate-spin" />
      </div>
    )
  }

  if (slides.length === 0) {
    return (
      <div className="text-center py-20 text-cd-text-tertiary">
        <p>暂无数据可回放，继续使用一段时间后再来看看</p>
      </div>
    )
  }

  const slide = slides[current]
  const progress = slides.length > 1 ? (current / (slides.length - 1)) * 100 : 0

  return (
    <div className="min-h-screen max-w-3xl mx-auto flex flex-col">
      {/* 页头 */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
            <Sparkles className="text-cd-accent" /> 时间线回放
          </h1>
          <p className="text-xs text-cd-text-tertiary mt-1">一键回放你的年度精彩瞬间</p>
        </div>
        <span className="text-xs text-cd-text-tertiary">{current + 1} / {slides.length}</span>
      </div>

      {/* 主舞台 */}
      <div
        className="relative rounded-2xl overflow-hidden border border-white/5 transition-all duration-500"
        style={{
          background: `linear-gradient(135deg, ${slide.color}22, ${slide.color}05)`,
          minHeight: 420,
        }}
      >
        {/* 进度条 */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-white/5 z-10">
          <div
            className="h-full transition-all duration-500"
            style={{ width: `${progress}%`, background: slide.color }}
          />
        </div>

        {/* 内容 */}
        <div
          key={current}
          className="flex flex-col items-center justify-center text-center px-8 py-12 animate-[fadeIn_0.5s_ease]"
          style={{ minHeight: 420 }}
        >
          <div className="text-7xl mb-4 animate-[bounceIn_0.6s_ease]">{slide.emoji}</div>
          <h2 className="text-sm font-medium text-cd-text-secondary mb-2 uppercase tracking-widest">
            {slide.title}
          </h2>
          {slide.value !== undefined && (
            <div
              className="text-7xl md:text-8xl font-bold mb-2 tabular-nums animate-[scaleIn_0.6s_ease]"
              style={{ color: slide.color }}
            >
              {slide.value}
            </div>
          )}
          {slide.subtitle && !slide.value && (
            <div className="text-2xl md:text-3xl font-bold text-cd-text mb-3 px-4 leading-relaxed">
              {slide.subtitle}
            </div>
          )}
          {slide.value !== undefined && slide.subtitle && (
            <div className="text-lg text-cd-text-secondary mb-3">{slide.subtitle}</div>
          )}
          {!slide.value && slide.title && slide.type === 'cover' && (
            <div className="text-2xl md:text-3xl font-bold text-cd-text mb-3">{slide.subtitle}</div>
          )}
          {slide.detail && (
            <p className="text-sm text-cd-text-tertiary max-w-md leading-relaxed mt-2">
              {slide.detail}
            </p>
          )}
        </div>

        {/* 左右导航按钮 */}
        <button
          onClick={goPrev}
          disabled={current === 0}
          className="absolute left-3 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-black/20 hover:bg-black/40 text-white flex items-center justify-center transition disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronLeft size={18} />
        </button>
        <button
          onClick={goNext}
          disabled={current === slides.length - 1}
          className="absolute right-3 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-black/20 hover:bg-black/40 text-white flex items-center justify-center transition disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {/* 控制条 */}
      <div className="mt-5 flex items-center justify-center gap-3">
        <button
          onClick={handleReset}
          className="w-10 h-10 rounded-full bg-cd-bg-card border border-cd-border text-cd-text-secondary hover:text-cd-text flex items-center justify-center transition"
          title="重置"
        >
          <RotateCcw size={16} />
        </button>
        <button
          onClick={handlePlay}
          className="w-14 h-14 rounded-full text-white flex items-center justify-center transition hover:scale-105 shadow-lg"
          style={{ background: slide.color }}
          title={playing ? '暂停' : '播放'}
        >
          {playing ? <Pause size={22} /> : <Play size={22} className="ml-0.5" />}
        </button>
        <div className="w-10" />
      </div>

      {/* 缩略图导航 */}
      <div className="mt-5 flex items-center justify-center gap-1.5 flex-wrap">
        {slides.map((s, i) => (
          <button
            key={i}
            onClick={() => { setPlaying(false); setCurrent(i) }}
            className={`w-2 h-2 rounded-full transition-all ${
              i === current ? 'w-6' : 'opacity-40 hover:opacity-70'
            }`}
            style={{ background: i === current ? s.color : 'var(--cd-text-tertiary)' }}
            title={s.title}
          />
        ))}
      </div>

      {/* 内联动画样式 */}
      <style>{`
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
        @keyframes bounceIn { 0% { transform: scale(0.3); opacity: 0 } 60% { transform: scale(1.1); opacity: 1 } 100% { transform: scale(1) } }
        @keyframes scaleIn { 0% { transform: scale(0.5); opacity: 0 } 100% { transform: scale(1); opacity: 1 } }
      `}</style>
    </div>
  )
}
