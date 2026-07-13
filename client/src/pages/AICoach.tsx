import { useState } from 'react'
import {
  Sparkles,
  FileText,
  Target,
  Bot,
  Loader2,
  Star,
  Lightbulb,
  Check,
  X,
  RefreshCw,
} from 'lucide-react'
import {
  aiWeeklyReview,
  aiGoalProgressComment,
  aiSmartSchedule,
  assignTodo,
  type WeeklyReview,
  type GoalProgressComment,
  type ScheduleSuggestion,
} from '../api/client'

// ── 评分圆环 ──
function ScoreRing({ score }: { score: number }) {
  const radius = 32
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference
  const color = score >= 80 ? '#10b981' : score >= 60 ? '#f59e0b' : '#ef4444'
  return (
    <div className="relative shrink-0">
      <svg width="80" height="80" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r={radius} fill="none" stroke="var(--cd-border)" strokeWidth="6" />
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 40 40)"
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-lg font-bold" style={{ color }}>
          {score}
        </span>
        <span className="text-[9px] text-cd-text-tertiary">分</span>
      </div>
    </div>
  )
}

// ── 加载动画 ──
function LoadingBlock({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-cd-text-tertiary">
      <Loader2 size={28} className="animate-spin mb-3 text-cd-green" />
      <p className="text-sm">{text}</p>
    </div>
  )
}

export default function AICoach() {
  // 周复盘
  const [reviewLoading, setReviewLoading] = useState(false)
  const [review, setReview] = useState<WeeklyReview | null>(null)
  const [reviewError, setReviewError] = useState('')

  // 目标点评
  const [goalLevel, setGoalLevel] = useState<'month' | 'week' | 'day'>('week')
  const [goalProgress, setGoalProgress] = useState(65)
  const [goalLoading, setGoalLoading] = useState(false)
  const [goalComment, setGoalComment] = useState<GoalProgressComment | null>(null)
  const [goalError, setGoalError] = useState('')

  // 智能排程
  const [scheduleLoading, setScheduleLoading] = useState(false)
  const [suggestions, setSuggestions] = useState<ScheduleSuggestion[]>([])
  const [scheduleMsg, setScheduleMsg] = useState('')
  const [scheduleError, setScheduleError] = useState('')
  const [adoptedIds, setAdoptedIds] = useState<Set<number | null>>(new Set())
  const [ignoredIds, setIgnoredIds] = useState<Set<number | null>>(new Set())

  const handleWeeklyReview = async () => {
    setReviewLoading(true)
    setReviewError('')
    setReview(null)
    try {
      const result = await aiWeeklyReview()
      setReview(result)
    } catch (e: any) {
      setReviewError(e?.message || '周复盘生成失败，请稍后重试')
    } finally {
      setReviewLoading(false)
    }
  }

  const handleGoalComment = async () => {
    setGoalLoading(true)
    setGoalError('')
    setGoalComment(null)
    try {
      const result = await aiGoalProgressComment(goalLevel, goalProgress)
      setGoalComment(result)
    } catch (e: any) {
      setGoalError(e?.message || '点评生成失败，请稍后重试')
    } finally {
      setGoalLoading(false)
    }
  }

  const handleSmartSchedule = async () => {
    setScheduleLoading(true)
    setScheduleError('')
    setSuggestions([])
    setScheduleMsg('')
    setAdoptedIds(new Set())
    setIgnoredIds(new Set())
    try {
      const result = await aiSmartSchedule()
      setSuggestions(result.suggestions || [])
      setScheduleMsg(result.message || '')
    } catch (e: any) {
      setScheduleError(e?.message || '智能排程生成失败，请稍后重试')
    } finally {
      setScheduleLoading(false)
    }
  }

  const handleAdopt = async (s: ScheduleSuggestion) => {
    if (s.todo_id == null) return
    try {
      await assignTodo({ todo_id: s.todo_id, assigned_date: s.suggested_day })
      setAdoptedIds(prev => new Set(prev).add(s.todo_id))
    } catch (e: any) {
      setScheduleError(e?.message || '采纳失败，请稍后重试')
    }
  }

  const handleIgnore = (s: ScheduleSuggestion) => {
    if (s.todo_id == null) return
    setIgnoredIds(prev => new Set(prev).add(s.todo_id))
  }

  const levelLabel: Record<string, string> = { month: '月目标', week: '周目标', day: '日目标' }

  return (
    <div className="max-w-4xl mx-auto pb-8">
      {/* 标题 */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <Sparkles size={24} className="text-cd-green" />
          AI 教练
        </h1>
        <p className="text-sm text-cd-text-tertiary mt-1">
          让 AI 帮你更好地管理时间 ✨ 温馨陪伴，活泼复盘，告别流水账
        </p>
      </div>

      <div className="space-y-4">
        {/* 📝 本周复盘 */}
        <section className="bg-cd-bg-secondary border border-cd-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-cd-green/15 text-cd-green">
                <FileText size={20} />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-cd-text">本周复盘</h2>
                <p className="text-xs text-cd-text-tertiary mt-0.5">AI 基于本周数据生成温馨复盘</p>
              </div>
            </div>
            <button
              onClick={handleWeeklyReview}
              disabled={reviewLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cd-green text-white text-xs font-medium hover:opacity-90 disabled:opacity-50"
            >
              {reviewLoading ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              {review ? '重新生成' : '生成复盘'}
            </button>
          </div>

          {/* 内容区 */}
          {reviewLoading ? (
            <LoadingBlock text="AI 正在翻阅你这一周的数据，马上就好~" />
          ) : reviewError ? (
            <div className="px-4 py-3 rounded-lg bg-cd-red/10 border border-cd-red/20 text-sm text-cd-red">
              {reviewError}
            </div>
          ) : review ? (
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                <ScoreRing score={review.score} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-cd-text-tertiary mb-1">复盘小结</div>
                  <div className="text-sm text-cd-text leading-relaxed whitespace-pre-wrap">
                    {review.review}
                  </div>
                </div>
              </div>

              {review.highlights?.length > 0 && (
                <div>
                  <div className="text-xs text-cd-text-tertiary mb-2 flex items-center gap-1">
                    <Star size={12} className="text-cd-gold" /> 本周亮点
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {review.highlights.map((h, i) => (
                      <span
                        key={i}
                        className="px-2.5 py-1 rounded-full bg-cd-gold/15 text-cd-gold text-xs border border-cd-gold/20"
                      >
                        ✨ {h}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {review.suggestions?.length > 0 && (
                <div>
                  <div className="text-xs text-cd-text-tertiary mb-2 flex items-center gap-1">
                    <Lightbulb size={12} className="text-cd-green" /> 下周建议
                  </div>
                  <ul className="space-y-1.5">
                    {review.suggestions.map((s, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-cd-text-secondary">
                        <span className="text-cd-green shrink-0 mt-0.5">→</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-sm text-cd-text-tertiary">
              点击「生成复盘」让 AI 帮你回顾这一周 🌿
            </div>
          )}
        </section>

        {/* 🎯 目标进度点评 */}
        <section className="bg-cd-bg-secondary border border-cd-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-cd-blue/15 text-cd-blue">
                <Target size={20} />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-cd-text">目标进度点评</h2>
                <p className="text-xs text-cd-text-tertiary mt-0.5">AI 鼓励性点评，绝不泼冷水</p>
              </div>
            </div>
            <button
              onClick={handleGoalComment}
              disabled={goalLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cd-green text-white text-xs font-medium hover:opacity-90 disabled:opacity-50"
            >
              {goalLoading ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
              生成点评
            </button>
          </div>

          {/* 选择器 */}
          <div className="flex items-center gap-4 mb-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-cd-text-tertiary">层级</span>
              <div className="flex bg-cd-bg rounded-lg p-0.5 border border-cd-border">
                {(['month', 'week', 'day'] as const).map(lv => (
                  <button
                    key={lv}
                    onClick={() => setGoalLevel(lv)}
                    className={`px-3 py-1 rounded-md text-xs transition-colors ${
                      goalLevel === lv
                        ? 'bg-cd-green text-white'
                        : 'text-cd-text-secondary hover:text-cd-text'
                    }`}
                  >
                    {levelLabel[lv]}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2 flex-1 max-w-xs">
              <span className="text-xs text-cd-text-tertiary">进度</span>
              <input
                type="range"
                min="0"
                max="100"
                value={goalProgress}
                onChange={e => setGoalProgress(Number(e.target.value))}
                className="flex-1 accent-cd-green"
              />
              <span className="text-xs text-cd-text font-medium w-8 text-right">{goalProgress}%</span>
            </div>
          </div>

          {/* 内容区 */}
          {goalLoading ? (
            <LoadingBlock text="AI 正在为你加油打气，稍等一下下~" />
          ) : goalError ? (
            <div className="px-4 py-3 rounded-lg bg-cd-red/10 border border-cd-red/20 text-sm text-cd-red">
              {goalError}
            </div>
          ) : goalComment ? (
            <div className="space-y-3">
              <div className="px-4 py-3 rounded-lg bg-cd-bg border border-cd-border">
                <div className="text-sm text-cd-text leading-relaxed whitespace-pre-wrap">
                  {goalComment.comment}
                </div>
              </div>
              {goalComment.encouragement && (
                <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-cd-green/10 border border-cd-green/20">
                  <Sparkles size={14} className="text-cd-green shrink-0" />
                  <span className="text-sm text-cd-green font-medium">{goalComment.encouragement}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-8 text-sm text-cd-text-tertiary">
              选择层级和进度，让 AI 给你一点鼓励 🌱
            </div>
          )}
        </section>

        {/* 🤖 智能排程建议 */}
        <section className="bg-cd-bg-secondary border border-cd-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-cd-purple/15 text-cd-purple">
                <Bot size={20} />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-cd-text">智能排程建议</h2>
                <p className="text-xs text-cd-text-tertiary mt-0.5">基于历史高效时段，给待分配任务排个期</p>
              </div>
            </div>
            <button
              onClick={handleSmartSchedule}
              disabled={scheduleLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cd-green text-white text-xs font-medium hover:opacity-90 disabled:opacity-50"
            >
              {scheduleLoading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              {suggestions.length > 0 ? '重新分析' : '开始分析'}
            </button>
          </div>

          {/* 内容区 */}
          {scheduleLoading ? (
            <LoadingBlock text="AI 正在分析你的高效时段，马上出建议~" />
          ) : scheduleError ? (
            <div className="px-4 py-3 rounded-lg bg-cd-red/10 border border-cd-red/20 text-sm text-cd-red">
              {scheduleError}
            </div>
          ) : suggestions.length > 0 ? (
            <div className="space-y-2">
              {scheduleMsg && (
                <div className="text-xs text-cd-text-tertiary px-3 py-2 rounded-lg bg-cd-bg border border-cd-border">
                  💡 {scheduleMsg}
                </div>
              )}
              {suggestions.map((s, i) => {
                const adopted = s.todo_id != null && adoptedIds.has(s.todo_id)
                const ignored = s.todo_id != null && ignoredIds.has(s.todo_id)
                return (
                  <div
                    key={`${s.todo_id}-${i}`}
                    className={`flex items-center gap-3 px-4 py-3 rounded-lg border transition-colors ${
                      adopted
                        ? 'bg-cd-green/10 border-cd-green/30'
                        : ignored
                          ? 'bg-cd-bg border-cd-border opacity-50'
                          : 'bg-cd-bg border-cd-border'
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-cd-text">
                          任务 #{s.todo_id ?? '?'}
                        </span>
                        <span className="px-2 py-0.5 rounded bg-cd-green/15 text-cd-green text-[11px] font-medium">
                          {s.suggested_day} {s.suggested_time}
                        </span>
                      </div>
                      <div className="text-xs text-cd-text-tertiary mt-1">{s.reason}</div>
                    </div>
                    {adopted ? (
                      <span className="flex items-center gap-1 text-xs text-cd-green font-medium">
                        <Check size={14} /> 已采纳
                      </span>
                    ) : ignored ? (
                      <span className="flex items-center gap-1 text-xs text-cd-text-tertiary">
                        <X size={14} /> 已忽略
                      </span>
                    ) : (
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => handleAdopt(s)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-cd-green text-white text-[11px] font-medium hover:opacity-90"
                        >
                          <Check size={12} /> 采纳
                        </button>
                        <button
                          onClick={() => handleIgnore(s)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-cd-bg-secondary text-cd-text-tertiary text-[11px] hover:text-cd-text border border-cd-border"
                        >
                          <X size={12} /> 忽略
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ) : scheduleMsg ? (
            <div className="text-center py-8 text-sm text-cd-text-tertiary">{scheduleMsg}</div>
          ) : (
            <div className="text-center py-8 text-sm text-cd-text-tertiary">
              点击「开始分析」，AI 会根据你的高效时段给待分配任务排期 🤖
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
