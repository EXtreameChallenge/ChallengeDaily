/**
 * 赛季排行榜组件 — 基于匿名 benchmark 的群组对比
 * 参考 Habitica 赛季排名，隐私优先设计
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Trophy, Crown, TrendingUp, TrendingDown, Minus, Upload,
  X, ChevronLeft, ChevronRight, Shield, Loader2, Target,
} from 'lucide-react'
import {
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer,
  Tooltip,
} from 'recharts'
import {
  getSeasonLeaderboard, getSeasonLeaderboardSummary, submitSeasonScore,
  type SeasonLeaderboardData, type SeasonSummaryData,
} from '../api/client'
import { useToast } from './Toast'

interface Props {
  open: boolean
  onClose: () => void
}

const METRICS = [
  { key: 'productivity', label: '生产力' },
  { key: 'exp', label: '经验值' },
  { key: 'habit_streak', label: '习惯连续' },
  { key: 'focus_min', label: '专注时长' },
]

// 奖牌颜色（金银铜）：#FFD700 / #C0C0C0 / #CD7F32
const MEDAL_EMOJI = ['🥇', '🥈', '🥉']

// 紫橙渐变（用于我的位置高亮）
const MY_GRADIENT = 'linear-gradient(135deg, #7B68EE 0%, #F0A030 100%)'

/** 根据 avatar_seed 生成确定性彩色头像 */
function AvatarCircle({ seed, name, size = 32 }: { seed: string; name: string; size?: number }) {
  const isMe = seed === 'me'
  const color = useMemo(() => {
    if (isMe) return MY_GRADIENT
    // 由 seed 哈希出 HSL 颜色
    let h = 0
    for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) & 0xFFFFFFFF
    const hue = Math.abs(h) % 360
    return `hsl(${hue}, 55%, 55%)`
  }, [seed, isMe])

  const initial = isMe ? '我' : (name?.[0] || '?')
  return (
    <div
      className="flex items-center justify-center rounded-full font-bold text-white shrink-0"
      style={{
        width: size, height: size,
        background: color,
        fontSize: size * 0.4,
        border: isMe ? '2px solid #F0A030' : 'none',
      }}
    >
      {initial}
    </div>
  )
}

/** 月份选择器 */
function MonthSelector({ month, onChange }: { month: string; onChange: (m: string) => void }) {
  const shift = (delta: number) => {
    try {
      const y = parseInt(month.slice(0, 4))
      const m = parseInt(month.slice(4, 6))
      let ny = y, nm = m + delta
      if (nm < 1) { nm = 12; ny -= 1 }
      if (nm > 12) { nm = 1; ny += 1 }
      onChange(`${ny}${String(nm).padStart(2, '0')}`)
    } catch { /* ignore */ }
  }
  const fmt = (m: string) => {
    try { return `${m.slice(0, 4)}年${parseInt(m.slice(4, 6))}月` } catch { return m }
  }
  // M7 修复：用本地时间获取当前月份，避免 UTC 导致跨时区错月
  // toISOString() 返回 UTC，东八区 0-8 点会得到上个月
  const now = new Date()
  const currentMonth = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}`
  const isCurrent = month === currentMonth

  return (
    <div className="flex items-center gap-2">
      <button onClick={() => shift(-1)} className="p-1 rounded-lg hover:bg-cd-hover text-cd-text-secondary">
        <ChevronLeft size={16} />
      </button>
      <span className="text-sm font-medium text-cd-text min-w-[90px] text-center">{fmt(month)}</span>
      <button onClick={() => shift(1)} disabled={isCurrent}
        className="p-1 rounded-lg hover:bg-cd-hover text-cd-text-secondary disabled:opacity-30 disabled:cursor-not-allowed">
        <ChevronRight size={16} />
      </button>
    </div>
  )
}

export default function SeasonLeaderboard({ open, onClose }: Props) {
  const toast = useToast()
  const [data, setData] = useState<SeasonLeaderboardData | null>(null)
  const [summary, setSummary] = useState<SeasonSummaryData | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  // M7 修复：用本地时间获取当前月份（避免 UTC 错月）
  const [month, setMonth] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`
  })
  const [metric, setMetric] = useState('productivity')
  const [participated, setParticipated] = useState(false)

  // M4 修复：切换月份时重置 participated 状态（避免上月已提交状态误显示到本月）
  const handleMonthChange = useCallback((m: string) => {
    setMonth(m)
    setParticipated(false)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [lb, sm] = await Promise.all([
        getSeasonLeaderboard(month, metric),
        getSeasonLeaderboardSummary(month).catch(() => null),
      ])
      setData(lb)
      setSummary(sm)
    } catch (err: any) {
      toast.error(err.message || '加载排行榜失败')
    } finally {
      setLoading(false)
    }
  }, [month, metric, toast])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      const res = await submitSeasonScore(month)
      setParticipated(true)
      toast.success(res.message || '已参与匿名排名')
      // 重新加载
      load()
    } catch (err: any) {
      toast.error(err.message || '提交失败')
    } finally {
      setSubmitting(false)
    }
  }

  // H3 修复：Modal 焦点管理 — ESC 键关闭 + 打开时聚焦 + role/aria 无障碍
  // 注意：hooks 必须在 early return 之前调用，否则违反 React Hooks 规则
  const modalRef = useRef<HTMLDivElement>(null)
  const titleId = useMemo(() => `season-lb-title-${Math.random().toString(36).slice(2, 8)}`, [])
  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    // 打开时聚焦 Modal（让屏幕阅读器立即进入对话框）
    const timer = setTimeout(() => modalRef.current?.focus(), 50)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      clearTimeout(timer)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
      role="presentation"
    >
      <motion.div
        ref={modalRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        className="flex flex-col rounded-2xl w-full max-w-3xl shadow-2xl overflow-hidden focus:outline-none"
        style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', maxHeight: '92vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-5 py-3.5 shrink-0" style={{ borderBottom: '1px solid var(--cd-border)' }}>
          <h2 id={titleId} className="text-base font-bold text-cd-text flex items-center gap-2">
            <Trophy size={18} className="text-cd-gold" /> 赛季排行榜
          </h2>
          <button onClick={onClose} aria-label="关闭" className="text-cd-text-secondary hover:text-cd-text transition p-1 rounded-lg hover:bg-cd-hover">
            <X size={18} />
          </button>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5" style={{ minHeight: 0 }}>
          {loading && !data ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="animate-spin text-cd-purple" size={32} />
            </div>
          ) : data ? (
            <>
              {/* 顶部控制栏 */}
              <div className="flex items-center justify-between flex-wrap gap-3">
                <MonthSelector month={month} onChange={handleMonthChange} />
                <div className="flex items-center gap-1 bg-cd-bg-secondary rounded-2xl p-1">
                  {METRICS.map(m => (
                    <button
                      key={m.key}
                      onClick={() => setMetric(m.key)}
                      className={`px-2.5 py-1 text-xs rounded-2xl transition ${
                        metric === m.key ? 'bg-cd-purple text-white' : 'text-cd-text-secondary hover:text-cd-text'
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* 我的排名卡片 */}
              <MyRankCard data={data} summary={summary} />

              {/* Top 10 排行榜 */}
              <TopLeaderboard data={data} />

              {/* 分数分布直方图 */}
              <DistributionChart data={data} />

              {/* 赛季成就进度 */}
              <SeasonGoals data={data} />

              {/* 维度对比雷达图 */}
              {summary && <DimensionRadar summary={summary} />}

              {/* 隐私声明 + 提交按钮 */}
              <div className="flex items-start gap-3 p-3 rounded-2xl" style={{ background: 'var(--cd-bg-secondary)' }}>
                <Shield size={16} className="text-cd-green shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-cd-text-secondary leading-relaxed">
                    {data.privacy_note || '排行榜基于匿名数据，不含真实用户身份。'}
                  </div>
                  <button
                    onClick={handleSubmit}
                    disabled={submitting || participated}
                    className="mt-2 flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-2xl transition disabled:opacity-50"
                    style={{
                      background: participated ? 'var(--cd-green)' : 'var(--cd-purple)',
                      color: '#fff',
                    }}
                  >
                    {submitting ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                    {participated ? '已参与匿名排名' : '参与匿名排名'}
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="text-center py-20 text-cd-text-secondary">暂无数据</div>
          )}
        </div>
      </motion.div>
    </div>
  )
}

// ── 我的排名卡片 ──────────────────────────────────
function MyRankCard({ data, summary }: { data: SeasonLeaderboardData; summary: SeasonSummaryData | null }) {
  const rankChange = summary?.rank_change ?? 0
  const ChangeIcon = rankChange > 0 ? TrendingUp : rankChange < 0 ? TrendingDown : Minus
  const changeColor = rankChange > 0 ? 'text-cd-green' : rankChange < 0 ? 'text-cd-red' : 'text-cd-text-tertiary'

  return (
    <div
      className="rounded-2xl p-5 relative overflow-hidden"
      style={{
        background: 'linear-gradient(135deg, rgba(123,104,238,0.12) 0%, rgba(240,160,48,0.08) 100%)',
        border: '2px solid transparent',
        backgroundImage: 'linear-gradient(var(--cd-card), var(--cd-card)), linear-gradient(135deg, var(--cd-accent), #F0A030)',
        backgroundOrigin: 'border-box',
        backgroundClip: 'padding-box, border-box',
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {/* 大字号排名 */}
          <div className="text-center">
            <AnimatePresence mode="wait">
              <motion.div
                key={data.my_rank}
                initial={{ opacity: 0, y: -10, scale: 0.8 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 10, scale: 0.8 }}
                transition={{ duration: 0.3 }}
                className="text-4xl font-black"
                style={{ color: 'var(--cd-text)' }}
              >
                #{data.my_rank}
              </motion.div>
            </AnimatePresence>
            <div className="text-xs text-cd-text-tertiary mt-0.5">/ {data.total_users} 人</div>
          </div>
          {/* 分数 + 变化 */}
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-2xl font-bold" style={{ color: 'var(--cd-text)' }}>
                {data.my_score.toFixed(1)}
              </span>
              <span className="text-xs text-cd-text-tertiary">{data.metric_label}</span>
            </div>
            <div className={`flex items-center gap-1 text-xs mt-1 ${changeColor}`}>
              <ChangeIcon size={12} />
              {rankChange > 0 ? `↑${rankChange} 位` : rankChange < 0 ? `↓${Math.abs(rankChange)} 位` : '持平'}
              <span className="text-cd-text-tertiary ml-1">vs 上月</span>
            </div>
          </div>
        </div>
        {/* 百分位徽章 */}
        <div
          className="flex flex-col items-center justify-center rounded-full px-4 py-2"
          style={{ background: MY_GRADIENT, minWidth: 80 }}
        >
          <span className="text-lg font-black text-white">Top {Math.max(0.1, 100 - data.percentile).toFixed(0)}%</span>
          <span className="text-[10px] text-white/80">百分位</span>
        </div>
      </div>
      {summary?.summary_text && (
        <div className="mt-3 text-xs text-cd-text-secondary leading-relaxed">{summary.summary_text}</div>
      )}
    </div>
  )
}

// ── Top 10 排行榜列表 ──────────────────────────────
function TopLeaderboard({ data }: { data: SeasonLeaderboardData }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-1.5">
        <Crown size={14} className="text-cd-gold" /> Top 排行
      </h3>
      <div className="space-y-1.5">
        {data.top_users.map((u, idx) => {
          const isTop3 = u.rank <= 3
          const isMe = u.is_me
          // 判断是否是分隔符（我在 10 名外时的"..."占位）
          const isSeparator = idx > 0 && u.rank > 10 && data.top_users[idx - 1].rank <= 10
          return (
            <div key={`${u.rank}-${u.avatar_seed}-${idx}`}>
              {isSeparator && (
                <div className="text-center text-cd-text-tertiary text-xs py-1">···</div>
              )}
              <motion.div
                initial={false}
                animate={{ opacity: 1 }}
                className={`flex items-center gap-3 px-3 py-2 rounded-2xl transition ${
                  isMe ? 'bg-cd-purple/10' : 'hover:bg-cd-hover'
                }`}
                style={isMe ? { border: '1px solid', borderImage: MY_GRADIENT + ' 1' } : undefined}
              >
                {/* 排名/奖牌 */}
                <div className="w-7 text-center shrink-0">
                  {isTop3 ? (
                    <span className="text-lg">{MEDAL_EMOJI[u.rank - 1]}</span>
                  ) : (
                    <span className="text-sm font-bold text-cd-text-secondary">{u.rank}</span>
                  )}
                </div>
                {/* 头像 */}
                <AvatarCircle seed={u.avatar_seed} name={u.anonymous_name} size={28} />
                {/* 名称 */}
                <span className={`flex-1 text-sm truncate ${isMe ? 'font-bold text-cd-purple' : 'text-cd-text'}`}>
                  {u.anonymous_name}
                </span>
                {/* 分数 */}
                <span className="text-sm font-semibold" style={{ color: isMe ? 'var(--cd-purple)' : 'var(--cd-text)' }}>
                  {u.score.toFixed(1)}
                </span>
              </motion.div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── 分数分布直方图 ──────────────────────────────────
function DistributionChart({ data }: { data: SeasonLeaderboardData }) {
  const maxCount = Math.max(...data.distribution.map(d => d.count), 1)
  return (
    <div>
      <h3 className="text-sm font-semibold text-cd-text mb-3">分数分布</h3>
      <div className="flex items-end justify-between gap-1.5 h-32 px-1">
        {data.distribution.map((bin, i) => {
          const heightPct = (bin.count / maxCount) * 100
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1 group">
              <div className="text-[10px] text-cd-text-tertiary opacity-0 group-hover:opacity-100 transition">
                {bin.count}
              </div>
              <div className="w-full flex-1 flex items-end" style={{ minHeight: 0 }}>
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: `${heightPct}%` }}
                  transition={{ duration: 0.4, delay: i * 0.05 }}
                  className="w-full rounded-t"
                  style={{
                    height: `${heightPct}%`,
                    minHeight: bin.count > 0 ? 4 : 0,
                    background: bin.is_mine ? MY_GRADIENT : 'var(--cd-bg-tertiary, rgba(128,128,128,0.2))',
                  }}
                />
              </div>
              <div className={`text-[9px] ${bin.is_mine ? 'text-cd-purple font-bold' : 'text-cd-text-tertiary'}`}>
                {bin.range}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── 赛季成就进度 ──────────────────────────────────
function SeasonGoals({ data }: { data: SeasonLeaderboardData }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-1.5">
        <Target size={14} className="text-cd-purple" /> 赛季成就
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {data.season_goals.map(g => {
          const pct = g.target > 0 ? Math.min(100, (g.my_progress / g.target) * 100) : 0
          return (
            <div
              key={g.key}
              className={`rounded-2xl p-2.5 border ${g.completed ? 'bg-cd-gold/10 border-cd-gold/30' : 'bg-cd-bg-secondary border-white/5'}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-medium text-cd-text truncate">{g.name}</span>
                <span className={`text-[10px] ${g.completed ? 'text-cd-gold' : 'text-cd-text-tertiary'}`}>
                  {g.completed ? '✓ 已完成' : `${g.my_progress}/${g.target}`}
                </span>
              </div>
              <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.5 }}
                  className={`h-full rounded-full ${g.completed ? '' : ''}`}
                  style={{ background: g.completed ? 'var(--cd-gold)' : MY_GRADIENT }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── 维度对比雷达图 ──────────────────────────────────
function DimensionRadar({ summary }: { summary: SeasonSummaryData }) {
  // 将各维度归一化到 0-100（用 group_avg 作为 50 基准）
  const radarData = summary.dimensions.map(d => {
    const myNorm = d.group_avg > 0 ? Math.min(100, (d.my_value / d.group_avg) * 50) : (d.my_value > 0 ? 75 : 0)
    const groupNorm = 50
    return {
      dimension: d.label,
      我: Math.round(myNorm),
      群组均值: groupNorm,
    }
  })

  return (
    <div>
      <h3 className="text-sm font-semibold text-cd-text mb-3">六维对比 vs 群组均值</h3>
      <div style={{ width: '100%', height: 240 }}>
        <ResponsiveContainer>
          <RadarChart data={radarData} outerRadius="70%">
            <PolarGrid stroke="var(--cd-border)" />
            <PolarAngleAxis dataKey="dimension" tick={{ fill: 'var(--cd-text-secondary)', fontSize: 11 }} />
            <PolarRadiusAxis domain={[0, 100]} tick={{ fill: 'var(--cd-text-tertiary)', fontSize: 9 }} angle={90} />
            <Radar name="群组均值" dataKey="群组均值" stroke="#888" fill="#888" fillOpacity={0.15} />
            <Radar name="我" dataKey="我" stroke="#7B68EE" fill="#7B68EE" fillOpacity={0.35} />
            <Tooltip
              contentStyle={{
                background: 'var(--cd-card)',
                border: '1px solid var(--cd-border)',
                borderRadius: 8,
                fontSize: 12,
              }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center justify-center gap-4 mt-1">
        <span className="flex items-center gap-1.5 text-xs text-cd-text-secondary">
          <span className="w-2.5 h-2.5 rounded-lg" style={{ background: 'var(--cd-accent)' }} /> 我
        </span>
        <span className="flex items-center gap-1.5 text-xs text-cd-text-secondary">
          <span className="w-2.5 h-2.5 rounded-lg" style={{ background: '#888' }} /> 群组均值
        </span>
      </div>
    </div>
  )
}
