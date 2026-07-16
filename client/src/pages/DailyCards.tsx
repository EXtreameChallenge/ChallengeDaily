import { useState, useEffect, useCallback } from 'react'
import {
  ChevronLeft, ChevronRight, Calendar, Loader2, CheckCircle, Flame, Timer,
  BarChart3, Trophy, Sparkles, FileText, TrendingUp,
} from 'lucide-react'
import { getDailyCard, getDailyCardText, getTodayStr, formatLocalDate, type DailyCardData } from '../api/client'
import { useToast } from '../components/Toast'

const GRADE_COLORS: Record<string, string> = {
  S: 'text-gold', A: 'text-cd-green', B: 'text-cd-accent', C: 'text-yellow-400', D: 'text-cd-text-tertiary',
}

const WEEKDAY_LABELS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function formatDate(d: string) {
  const date = new Date(d + 'T00:00:00')
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${WEEKDAY_LABELS[date.getDay()]}`
}

export default function DailyCards() {
  const toast = useToast()
  const [currentDate, setCurrentDate] = useState(getTodayStr())
  const [card, setCard] = useState<DailyCardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [copying, setCopying] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getDailyCard(currentDate)
      setCard(data)
    } catch {
      setCard(null)
    } finally {
      setLoading(false)
    }
  }, [currentDate])

  useEffect(() => { load() }, [load])

  const goPrev = () => {
    const d = new Date(currentDate + 'T00:00:00')
    d.setDate(d.getDate() - 1)
    setCurrentDate(formatLocalDate(d))
  }
  const goNext = () => {
    const d = new Date(currentDate + 'T00:00:00')
    d.setDate(d.getDate() + 1)
    if (d <= new Date()) setCurrentDate(formatLocalDate(d))
  }
  const goToday = () => setCurrentDate(getTodayStr())

  const handleCopyText = async () => {
    setCopying(true)
    try {
      const { text } = await getDailyCardText(currentDate)
      if (!text) { toast.error('暂无数据'); return }
      await navigator.clipboard.writeText(text)
      toast.success('已复制到剪贴板')
    } catch {
      toast.error('复制失败')
    } finally {
      setCopying(false)
    }
  }

  const s = card?.summary
  const hasData = s && (s.total_tasks > 0 || s.total_focus_min > 0 || s.total_work_min > 0)
  const gradeColor = s ? GRADE_COLORS[s.grade] || 'text-cd-text' : ''

  return (
    <div className="max-w-3xl mx-auto">
      {/* 顶部日期导航 */}
      <div className="flex items-center justify-between mb-6">
        <button onClick={goPrev} className="p-2 rounded-lg bg-cd-bg-input border border-white/5 text-cd-text-secondary hover:bg-white/5 transition">
          <ChevronLeft size={20} />
        </button>
        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-cd-accent" />
          <h1 className="text-xl font-bold text-cd-text">{formatDate(currentDate)}</h1>
          {currentDate === getTodayStr() && (
            <span className="px-2 py-0.5 rounded text-[10px] bg-cd-green/20 text-cd-green">今天</span>
          )}
        </div>
        <button onClick={goNext} disabled={currentDate >= getTodayStr()} className="p-2 rounded-lg bg-cd-bg-input border border-white/5 text-cd-text-secondary hover:bg-white/5 transition disabled:opacity-30">
          <ChevronRight size={20} />
        </button>
      </div>

      {/* 快速跳转 */}
      <div className="flex items-center gap-2 mb-6">
        <button onClick={goToday} className="px-3 py-1 rounded-lg text-xs bg-cd-bg-input text-cd-text-secondary hover:bg-white/5 transition">
          回到今天
        </button>
        <input
          type="date"
          value={currentDate}
          max={getTodayStr()}
          onChange={e => e.target.value && setCurrentDate(e.target.value)}
          className="px-2 py-1 rounded-lg text-xs bg-cd-bg-input border border-white/5 text-cd-text"
        />
        {hasData && (
          <button onClick={handleCopyText} disabled={copying}
            className="ml-auto flex items-center gap-1 px-3 py-1 rounded-lg text-xs bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-50">
            {copying ? <Loader2 size={12} className="animate-spin" /> : <FileText size={12} />}
            复制卡片文本
          </button>
        )}
      </div>

      {/* 卡片内容 */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 size={24} className="animate-spin text-cd-text-tertiary" />
        </div>
      ) : !card || !hasData ? (
        <div className="text-center py-20">
          <div className="w-16 h-16 rounded-full bg-cd-bg-input flex items-center justify-center mx-auto mb-4">
            <Calendar size={28} className="text-cd-text-tertiary" />
          </div>
          <p className="text-sm text-cd-text-secondary mb-1">这一天没有活动记录</p>
          <p className="text-xs text-cd-text-tertiary">试试选择其他日期</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* 评分卡 */}
          <div className="bg-gradient-to-br from-cd-bg-card to-cd-bg-card/80 rounded-xl border border-cd-accent/20 p-6">
            <div className="flex items-center gap-4">
              {/* 评分圆环 */}
              <div className="relative w-20 h-20 shrink-0">
                <svg className="w-20 h-20 -rotate-90" viewBox="0 0 80 80">
                  <circle cx="40" cy="40" r="34" fill="none" stroke="currentColor" strokeWidth="4" className="text-cd-border opacity-30" />
                  <circle cx="40" cy="40" r="34" fill="none" stroke="currentColor" strokeWidth="4"
                    className="text-cd-accent transition-all"
                    strokeDasharray={`${(s!.productivity_score / 100) * 213.6} 213.6`}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className={`text-2xl font-bold ${gradeColor}`}>{s!.grade}</span>
                  <span className="text-[10px] text-cd-text-tertiary">{s!.productivity_score}分</span>
                </div>
              </div>

              {/* 概览 */}
              <div className="flex-1">
                <div className="text-sm font-semibold text-cd-text mb-2 flex items-center gap-1">
                  <Sparkles size={14} className="text-cd-accent" /> 生产力概览
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="flex items-center gap-1.5">
                    <CheckCircle size={12} className="text-cd-green" />
                    <span className="text-cd-text-secondary">{s!.total_tasks} 个任务完成</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Timer size={12} className="text-cd-accent" />
                    <span className="text-cd-text-secondary">{s!.total_focus_min} 分钟专注</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <BarChart3 size={12} className="text-blue-400" />
                    <span className="text-cd-text-secondary">{s!.total_work_min} 分钟工作</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Flame size={12} className="text-orange-400" />
                    <span className="text-cd-text-secondary">{s!.total_habits} 个习惯打卡</span>
                  </div>
                </div>
              </div>
            </div>

            {/* 活动时间范围 */}
            {card!.activity_first_ts && card!.activity_last_ts && (
              <div className="mt-4 pt-3 border-t border-white/5 text-xs text-cd-text-tertiary">
                活动记录：{card!.activity_first_ts.substring(11, 16)} — {card!.activity_last_ts.substring(11, 16)}
                {card!.pomodoro_quality && (
                  <span className="ml-3">
                    专注质量：{card!.pomodoro_quality.grade}（{card!.pomodoro_quality.score}分）
                  </span>
                )}
              </div>
            )}
          </div>

          {/* 详细数据网格 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 待办完成 */}
            {card!.todos_completed.length > 0 && (
              <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4">
                <div className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-1.5">
                  <CheckCircle size={14} className="text-cd-green" /> 已完成待办
                  <span className="text-xs text-cd-text-tertiary font-normal">({card!.todos_count})</span>
                </div>
                <div className="space-y-1.5">
                  {card!.todos_completed.map(t => (
                    <div key={t.id} className="flex items-center gap-2 text-xs">
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-cd-bg-input text-cd-text-secondary shrink-0">{t.category}</span>
                      <span className="text-cd-text flex-1 truncate">{t.title}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 专注会话 */}
            {card!.pomodoro_sessions.length > 0 && (
              <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4">
                <div className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-1.5">
                  <Timer size={14} className="text-cd-accent" /> 专注会话
                  <span className="text-xs text-cd-text-tertiary font-normal">({card!.pomodoro_count}次 / {card!.pomodoro_total_min}min)</span>
                </div>
                <div className="space-y-1.5">
                  {card!.pomodoro_sessions.map(ps => (
                    <div key={ps.id} className="flex items-center gap-2 text-xs">
                      <span className="text-cd-text flex-1 truncate">{ps.task || '未命名'}</span>
                      <span className="text-cd-text-tertiary">{ps.duration_min}min</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 工作分布 */}
            {Object.keys(card!.activity_categories).length > 0 && (
              <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4">
                <div className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-1.5">
                  <TrendingUp size={14} className="text-blue-400" /> 工作分布
                  <span className="text-xs text-cd-text-tertiary font-normal">({card!.activity_total_min}min)</span>
                </div>
                <div className="space-y-1.5">
                  {Object.entries(card!.activity_categories).map(([cat, dur]) => {
                    const pct = card!.activity_total_min > 0 ? (dur / card!.activity_total_min) * 100 : 0
                    return (
                      <div key={cat} className="flex items-center gap-2 text-xs">
                        <span className="text-cd-text-secondary w-16 shrink-0 truncate">{cat}</span>
                        <div className="flex-1 h-1.5 bg-cd-bg-input rounded-full overflow-hidden">
                          <div className="h-full bg-cd-accent/60 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                        <span className="text-cd-text-tertiary w-12 text-right shrink-0">{dur}min</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 习惯打卡 */}
            {card!.habits_logged.length > 0 && (
              <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4">
                <div className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-1.5">
                  <Flame size={14} className="text-orange-400" /> 习惯打卡
                  <span className="text-xs text-cd-text-tertiary font-normal">({card!.habits_count})</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {card!.habits_logged.map(h => (
                    <div key={h.habit_id} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-cd-bg-input text-xs">
                      {h.color && <span className="w-2 h-2 rounded-full" style={{ background: h.color }} />}
                      <span className="text-cd-text">{h.name}</span>
                      <span className="text-cd-text-tertiary">×{h.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 成就解锁 */}
            {card!.achievements_unlocked.length > 0 && (
              <div className="bg-cd-bg-card rounded-xl border border-white/5 p-4 md:col-span-2">
                <div className="text-sm font-semibold text-cd-text mb-3 flex items-center gap-1.5">
                  <Trophy size={14} className="text-yellow-400" /> 解锁成就
                  <span className="text-xs text-cd-text-tertiary font-normal">({card!.achievements_count})</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {card!.achievements_unlocked.map(a => (
                    <div key={a.code} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-cd-bg-input">
                      <span className="text-lg">{a.icon}</span>
                      <div className="min-w-0">
                        <div className="text-xs font-medium text-cd-text">{a.name}</div>
                        <div className="text-[10px] text-cd-text-tertiary truncate">{a.description}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
