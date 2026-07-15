import { useState, useEffect, useCallback } from 'react'
import { Target, Plus, Trash2, CheckCircle2, Circle, Calendar, TrendingUp, X, Smile } from 'lucide-react'
import { getGoals, createGoal, updateGoal, deleteGoal, getMoodHeatmap, type Goal, type MoodEntry } from '../api/client'
import { useToast } from '../components/Toast'
import dayjs from 'dayjs'

const CATEGORIES = [
  { value: 'personal', label: '个人', color: '#6366f1' },
  { value: 'work', label: '工作', color: '#3b82f6' },
  { value: 'health', label: '健康', color: '#10b981' },
  { value: 'learning', label: '学习', color: '#f59e0b' },
  { value: 'finance', label: '财务', color: '#ef4444' },
]
const TIMEFRAMES = [
  { value: 'yearly', label: '年度' },
  { value: 'quarterly', label: '季度' },
  { value: 'monthly', label: '月度' },
]

// 心情 emoji 映射
const MOOD_EMOJI: Record<string, string> = {
  'great': '😄', 'good': '🙂', 'okay': '😐', 'bad': '😕', 'terrible': '😢',
  'happy': '😄', 'excited': '🤩', 'calm': '😌', 'tired': '😴', 'stressed': '😣',
  'proud': '🌟', 'focused': '🎯', 'balanced': '☕', 'scattered': '🍃', 'warm': '🌸',
}

export default function Goals() {
  const { toast } = useToast()
  const [goals, setGoals] = useState<Goal[]>([])
  const [loading, setLoading] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [moodData, setMoodData] = useState<MoodEntry[]>([])
  const [filter, setFilter] = useState<string>('active')

  // 新建目标表单
  const [form, setForm] = useState({
    title: '',
    description: '',
    category: 'personal' as Goal['category'],
    timeframe: 'yearly' as Goal['timeframe'],
    target_date: '',
  })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [goalsRes, moodRes] = await Promise.all([
        getGoals(filter !== 'all' ? filter : undefined),
        getMoodHeatmap(),
      ])
      setGoals(goalsRes.goals)
      setMoodData(moodRes.data)
    } catch { toast('error', '加载失败') }
    setLoading(false)
  }, [filter, toast])

  useEffect(() => { load() }, [load])

  const handleCreate = async () => {
    if (!form.title.trim()) { toast('error', '目标标题不能为空'); return }
    try {
      await createGoal({
        title: form.title,
        description: form.description,
        category: form.category,
        timeframe: form.timeframe,
        target_date: form.target_date || undefined,
      })
      toast('success', '目标已创建')
      setShowModal(false)
      setForm({ title: '', description: '', category: 'personal', timeframe: 'yearly', target_date: '' })
      load()
    } catch { toast('error', '创建失败') }
  }

  const handleToggleKR = async (goal: Goal, idx: number) => {
    const newKRs = goal.key_results.map((kr, i) =>
      i === idx ? { ...kr, done: !kr.done } : kr
    )
    const doneCount = newKRs.filter(kr => kr.done).length
    const progress = newKRs.length > 0 ? Math.round((doneCount / newKRs.length) * 100) : goal.progress
    try {
      await updateGoal(goal.id, { key_results: newKRs, progress })
      load()
    } catch { toast('error', '更新失败') }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteGoal(id)
      toast('success', '目标已删除')
      load()
    } catch { toast('error', '删除失败') }
  }

  const handleComplete = async (goal: Goal) => {
    const newStatus = goal.status === 'completed' ? 'active' : 'completed'
    try {
      await updateGoal(goal.id, { status: newStatus, progress: newStatus === 'completed' ? 100 : goal.progress })
      toast('success', newStatus === 'completed' ? '恭喜达成目标！' : '已重新激活')
      load()
    } catch { toast('error', '更新失败') }
  }

  const daysLeft = (targetDate: string) => {
    const diff = dayjs(targetDate).diff(dayjs(), 'day')
    return diff
  }

  // 心情热力图统计
  const moodStats = moodData.reduce((acc, m) => {
    acc[m.mood] = (acc[m.mood] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="max-w-5xl mx-auto p-6">
      {/* 标题区 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-cd-text flex items-center gap-2">
            <Target size={20} className="text-cd-accent" /> 长期目标
          </h1>
          <p className="text-sm text-cd-text-secondary mt-1">年度/季度/月度目标 · 关键结果追踪 · GoalDay集大成</p>
        </div>
        <button onClick={() => setShowModal(true)}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-cd-accent text-white hover:opacity-90 transition">
          <Plus size={14} /> 新建目标
        </button>
      </div>

      {/* 筛选 */}
      <div className="flex gap-2 mb-4">
        {['active', 'completed', 'all'].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-lg text-xs transition ${
              filter === f
                ? 'bg-cd-accent/20 text-cd-accent border border-cd-accent/30'
                : 'bg-cd-bg-card text-cd-text-secondary border border-white/5 hover:bg-white/5'
            }`}>
            {f === 'active' ? '进行中' : f === 'completed' ? '已完成' : '全部'}
          </button>
        ))}
      </div>

      {/* 目标列表 */}
      {loading ? (
        <div className="text-center py-12 text-cd-text-tertiary">加载中...</div>
      ) : goals.length === 0 ? (
        <div className="text-center py-12 text-cd-text-tertiary">
          <Target size={40} className="mx-auto mb-3 opacity-30" />
          <p>还没有目标，点击"新建目标"开始你的长期规划</p>
        </div>
      ) : (
        <div className="space-y-3">
          {goals.map(goal => {
            const cat = CATEGORIES.find(c => c.value === goal.category) || CATEGORIES[0]
            const tf = TIMEFRAMES.find(t => t.value === goal.timeframe) || TIMEFRAMES[0]
            const left = daysLeft(goal.target_date)
            const isCompleted = goal.status === 'completed'
            return (
              <div key={goal.id}
                className={`bg-cd-bg-card rounded-xl p-4 border transition ${
                  isCompleted ? 'border-cd-green/30 opacity-75' : 'border-white/5 hover:border-white/10'
                }`}>
                {/* 顶部行 */}
                <div className="flex items-start gap-3">
                  <div className="w-1 self-stretch rounded-full" style={{ background: goal.color || cat.color }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className={`text-sm font-medium ${isCompleted ? 'text-cd-text-tertiary line-through' : 'text-cd-text'}`}>
                        {goal.title}
                      </h3>
                      <span className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${cat.color}20`, color: cat.color }}>
                        {cat.label}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-cd-text-tertiary">
                        {tf.label}
                      </span>
                    </div>
                    {goal.description && (
                      <p className="text-xs text-cd-text-tertiary mt-1">{goal.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <button onClick={() => handleComplete(goal)}
                      className={`p-1.5 rounded-lg transition ${
                        isCompleted ? 'text-cd-green hover:bg-cd-green/10' : 'text-cd-text-tertiary hover:bg-white/5'
                      }`}
                      title={isCompleted ? '重新激活' : '标记完成'}>
                      {isCompleted ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                    </button>
                    <button onClick={() => handleDelete(goal.id)}
                      className="p-1.5 rounded-lg text-cd-text-tertiary hover:bg-red-500/10 hover:text-red-400 transition">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {/* 进度条 */}
                <div className="mt-3">
                  <div className="flex items-center justify-between text-[10px] text-cd-text-tertiary mb-1">
                    <span>进度</span>
                    <span className="font-medium" style={{ color: goal.color || cat.color }}>{goal.progress}%</span>
                  </div>
                  <div className="h-1.5 bg-cd-bg-secondary rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${goal.progress}%`, background: goal.color || cat.color }} />
                  </div>
                </div>

                {/* 关键结果 */}
                {goal.key_results.length > 0 && (
                  <div className="mt-3 space-y-1">
                    {goal.key_results.map((kr, i) => (
                      <button key={i} onClick={() => handleToggleKR(goal, i)}
                        className="flex items-center gap-2 w-full text-left text-xs hover:bg-white/5 rounded px-2 py-1 transition">
                        {kr.done ? (
                          <CheckCircle2 size={12} className="text-cd-green shrink-0" />
                        ) : (
                          <Circle size={12} className="text-cd-text-tertiary shrink-0" />
                        )}
                        <span className={kr.done ? 'text-cd-text-tertiary line-through' : 'text-cd-text-secondary'}>
                          {kr.text}
                        </span>
                      </button>
                    ))}
                  </div>
                )}

                {/* 底部信息 */}
                <div className="flex items-center gap-3 mt-3 text-[10px] text-cd-text-tertiary">
                  <span className="flex items-center gap-1">
                    <Calendar size={10} /> {dayjs(goal.target_date).format('YYYY-MM-DD')}
                  </span>
                  {!isCompleted && (
                    <span className={`flex items-center gap-1 ${left < 7 ? 'text-orange-400' : left < 30 ? 'text-yellow-400' : ''}`}>
                      <TrendingUp size={10} />
                      {left > 0 ? `还剩 ${left} 天` : left === 0 ? '今天到期' : `已逾期 ${-left} 天`}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 心情热力图 */}
      {moodData.length > 0 && (
        <div className="mt-8 bg-cd-bg-card rounded-xl p-5 border border-white/5">
          <h2 className="text-sm font-semibold text-cd-text mb-4 flex items-center gap-2">
            <Smile size={16} className="text-pink-400" /> 心情趋势
          </h2>
          {/* 心情统计 */}
          <div className="flex flex-wrap gap-3 mb-4">
            {Object.entries(moodStats).map(([mood, count]) => (
              <div key={mood} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cd-bg-secondary">
                <span className="text-lg">{MOOD_EMOJI[mood] || '😊'}</span>
                <span className="text-xs text-cd-text-secondary">{count} 天</span>
              </div>
            ))}
          </div>
          {/* 简易热力图（最近30天） */}
          <div className="flex flex-wrap gap-1">
            {moodData.slice(-30).map((m, i) => (
              <div key={i}
                className="w-7 h-7 rounded flex items-center justify-center text-sm"
                style={{ background: `${MOOD_EMOJI[m.mood] ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.03)'}` }}
                title={`${m.date}: ${m.mood}`}>
                {MOOD_EMOJI[m.mood] || '·'}
              </div>
            ))}
          </div>
          <div className="text-[10px] text-cd-text-tertiary mt-2">最近 {Math.min(30, moodData.length)} 天的心情记录</div>
        </div>
      )}

      {/* 新建目标弹窗 */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowModal(false)}>
          <div className="bg-cd-bg-card rounded-xl p-6 w-full max-w-md border border-cd-border" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-cd-text">新建长期目标</h2>
              <button onClick={() => setShowModal(false)} className="text-cd-text-tertiary hover:text-cd-text">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-cd-text-secondary mb-1 block">目标标题 *</label>
                <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
                  placeholder="例如：2026年阅读50本书"
                  className="w-full px-3 py-2 rounded-lg bg-cd-bg-input border border-cd-border text-sm text-cd-text focus:border-cd-accent outline-none" />
              </div>
              <div>
                <label className="text-xs text-cd-text-secondary mb-1 block">描述</label>
                <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
                  rows={2} placeholder="目标详细描述..."
                  className="w-full px-3 py-2 rounded-lg bg-cd-bg-input border border-cd-border text-sm text-cd-text focus:border-cd-accent outline-none resize-none" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-cd-text-secondary mb-1 block">分类</label>
                  <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value as Goal['category'] })}
                    className="w-full px-3 py-2 rounded-lg bg-cd-bg-input border border-cd-border text-sm text-cd-text focus:border-cd-accent outline-none">
                    {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-cd-text-secondary mb-1 block">周期</label>
                  <select value={form.timeframe} onChange={e => setForm({ ...form, timeframe: e.target.value as Goal['timeframe'] })}
                    className="w-full px-3 py-2 rounded-lg bg-cd-bg-input border border-cd-border text-sm text-cd-text focus:border-cd-accent outline-none">
                    {TIMEFRAMES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-cd-text-secondary mb-1 block">目标日期</label>
                <input type="date" value={form.target_date} onChange={e => setForm({ ...form, target_date: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-cd-bg-input border border-cd-border text-sm text-cd-text focus:border-cd-accent outline-none" />
              </div>
            </div>
            <div className="flex gap-2 mt-5">
              <button onClick={() => setShowModal(false)}
                className="flex-1 px-4 py-2 rounded-lg text-sm bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition">
                取消
              </button>
              <button onClick={handleCreate}
                className="flex-1 px-4 py-2 rounded-lg text-sm bg-cd-accent text-white hover:opacity-90 transition">
                创建目标
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
