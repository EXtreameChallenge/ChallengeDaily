import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Flame, Check, Zap, Link2, Lightbulb, X } from 'lucide-react'
import { getHabits, logHabit, deleteHabit, updateHabit, autoCheckHabits, createHabit, getHabitRecommendations, getTodayStr, type Habit, type HabitLog, type HabitSuggestion } from '../api/client'
import { useToast } from '../components/Toast'
import HabitCreateModal from '../components/HabitCreateModal'

const CATEGORIES = ['开发', '测试', '运维', '数据分析', '产品', '设计', '管理', '文档', '会议', '沟通', '学习', '生活']

export default function Habits() {
  const [habits, setHabits] = useState<Habit[]>([])
  const [logs, setLogs] = useState<HabitLog[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [autoChecking, setAutoChecking] = useState(false)
  const [editingCat, setEditingCat] = useState<number | null>(null)
  const [suggestions, setSuggestions] = useState<HabitSuggestion[]>([])
  const [showSuggest, setShowSuggest] = useState(false)
  const [suggestLoading, setSuggestLoading] = useState(false)
  const [adoptingName, setAdoptingName] = useState<string | null>(null)
  const toast = useToast()

  const load = useCallback(async () => {
    try {
      const { habits: h, logs: l } = await getHabits()
      setHabits(h)
      setLogs(l)
    } catch {
      toast.error('加载习惯数据失败')
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleLog = async (habitId: number) => {
    try {
      await logHabit(habitId)
      load()
    } catch {
      toast.error('打卡失败')
    }
  }

  const handleAutoCheck = async () => {
    setAutoChecking(true)
    try {
      const res = await autoCheckHabits()
      if (res.count > 0) {
        toast.success(`自动打卡 ${res.count} 个习惯：${res.auto_logged.map(a => a.habit_name).join('、')}`)
        load()
      } else {
        toast.success('已检查，暂无满足自动打卡条件的习惯')
      }
    } catch {
      toast.error('自动检查失败')
    } finally {
      setAutoChecking(false)
    }
  }

  const handleSetAutoCategory = async (habitId: number, cat: string) => {
    try {
      await updateHabit(habitId, { auto_category: cat || null })
      toast.success(cat ? `已关联分类「${cat}」` : '已取消自动关联')
      setEditingCat(null)
      load()
    } catch {
      toast.error('更新失败')
    }
  }

  const handleDelete = async (id: number) => {
    if (!window.confirm('确定删除该习惯？相关打卡记录不会删除。')) return
    try {
      await deleteHabit(id)
      toast.success('习惯已删除')
      load()
    } catch {
      toast.error('删除失败，请重试')
    }
  }

  // P14-2：加载智能推荐
  const handleLoadSuggestions = async () => {
    if (showSuggest) { setShowSuggest(false); return }
    setSuggestLoading(true)
    setShowSuggest(true)
    try {
      const res = await getHabitRecommendations(5)
      setSuggestions(res.suggestions || [])
    } catch {
      toast.error('推荐加载失败')
      setShowSuggest(false)
    } finally {
      setSuggestLoading(false)
    }
  }

  // P14-2：采纳推荐 → 创建习惯
  const handleAdopt = async (s: HabitSuggestion) => {
    setAdoptingName(s.name)
    try {
      await createHabit({ name: s.name, target_count: s.target_count, period: s.period })
      toast.success(`已采纳「${s.name}」`)
      setSuggestions(prev => prev.filter(x => x.name !== s.name))
      load()
    } catch {
      toast.error('创建失败，请重试')
    } finally {
      setAdoptingName(null)
    }
  }

  const today = getTodayStr()
  const todayLogs = logs.filter(l => l.log_date === today)
  const todayLogMap = new Map(todayLogs.map(l => [l.habit_id, l.count]))

  // 计算连续天数
  const getStreak = (habitId: number) => {
    const habitLogs = logs.filter(l => l.habit_id === habitId).sort((a, b) => b.log_date.localeCompare(a.log_date))
    let streak = 0
    let checkDate = new Date()
    for (const log of habitLogs) {
      const logDate = new Date(log.log_date)
      const diffDays = Math.floor((checkDate.getTime() - logDate.getTime()) / (1000 * 60 * 60 * 24))
      if (diffDays <= 1) {
        streak++
        checkDate = logDate
      } else break
    }
    return streak
  }

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <Flame className="text-orange-400" /> 习惯追踪
        </h1>
        <div className="flex items-center gap-2">
          <button onClick={handleLoadSuggestions}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border transition text-sm ${
              showSuggest
                ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                : 'bg-amber-500/15 text-amber-400 border-amber-500/25 hover:bg-amber-500/25'
            }`}>
            <Lightbulb size={16} /> {suggestLoading ? '推荐中...' : '智能推荐'}
          </button>
          <button onClick={handleAutoCheck} disabled={autoChecking}
            className="flex items-center gap-1.5 px-3 py-2 bg-purple-500/15 text-purple-400 rounded-lg border border-purple-500/25 hover:bg-purple-500/25 transition text-sm disabled:opacity-50">
            <Zap size={16} /> {autoChecking ? '检查中...' : '自动打卡'}
          </button>
          <button onClick={() => setModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 transition">
            <Plus size={18} /> 新建习惯
          </button>
        </div>
      </div>

      <HabitCreateModal open={modalOpen} onClose={() => setModalOpen(false)} onCreated={load} />

      {/* P14-2：智能推荐面板 */}
      {showSuggest && (
        <div className="mb-6 bg-gradient-to-br from-amber-500/10 to-orange-500/5 rounded-xl border border-amber-500/20 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-cd-text flex items-center gap-1.5">
              <Lightbulb size={14} className="text-amber-400" /> 智能习惯推荐
              <span className="text-[10px] text-cd-text-tertiary font-normal ml-1">基于近 30 天行为数据</span>
            </h2>
            <button onClick={() => setShowSuggest(false)} className="text-cd-text-tertiary hover:text-cd-text">
              <X size={14} />
            </button>
          </div>
          {suggestLoading ? (
            <div className="text-center py-6 text-cd-text-tertiary text-sm animate-pulse">正在分析行为数据...</div>
          ) : suggestions.length === 0 ? (
            <div className="text-center py-6 text-cd-text-tertiary text-sm">
              暂无推荐。继续使用一段时间后，系统将根据你的高频活动分类给出建议。
            </div>
          ) : (
            <div className="space-y-2">
              {suggestions.map(s => (
                <div key={s.name} className="flex items-center gap-3 bg-cd-bg-card/60 rounded-lg p-3 border border-white/5">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-cd-text">{s.name}</span>
                      <span className="text-[10px] text-cd-text-tertiary bg-cd-bg-input px-1.5 py-0.5 rounded">
                        每日 {s.target_count} 次
                      </span>
                      {s.auto_category && (
                        <span className="text-[10px] text-purple-400 flex items-center gap-0.5 bg-purple-500/10 px-1.5 py-0.5 rounded">
                          <Link2 size={10} />{s.auto_category}
                        </span>
                      )}
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        s.source === 'behavior' ? 'text-amber-400 bg-amber-500/10' : 'text-cd-text-tertiary bg-cd-bg-input'
                      }`}>
                        {s.source === 'behavior' ? '行为驱动' : '经典推荐'}
                      </span>
                    </div>
                    <p className="text-xs text-cd-text-secondary mt-1">{s.reason}</p>
                  </div>
                  <button
                    onClick={() => handleAdopt(s)}
                    disabled={adoptingName === s.name}
                    className="shrink-0 px-3 py-1.5 text-xs bg-cd-green/20 text-cd-green rounded-md border border-cd-green/30 hover:bg-cd-green/30 transition disabled:opacity-50"
                  >
                    {adoptingName === s.name ? '采纳中...' : '采纳'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {habits.length === 0 ? (
        <div className="text-center py-12 text-cd-text-secondary">
          <Flame size={48} className="mx-auto mb-3 opacity-30" />
          <p>暂无习惯，点击右上角新建</p>
        </div>
      ) : (
        <div className="space-y-3">
          {habits.map(habit => {
            const todayCount = todayLogMap.get(habit.id) || 0
            const streak = getStreak(habit.id)
            const completed = todayCount >= habit.target_count
            return (
              <div key={habit.id} className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: habit.color }} />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-cd-text font-medium">{habit.name}</span>
                      {streak > 0 && <span className="text-xs text-orange-400 flex items-center gap-1"><Flame size={12} />{streak}天</span>}
                      {habit.auto_category && (
                        <span className="text-[10px] text-purple-400 flex items-center gap-0.5 bg-purple-500/10 px-1.5 py-0.5 rounded">
                          <Link2 size={10} />{habit.auto_category}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-cd-text-secondary mt-0.5">每日目标 {habit.target_count} 次 · 今日 {todayCount}/{habit.target_count}</div>
                  </div>
                  {/* 自动关联分类设置 */}
                  {editingCat === habit.id ? (
                    <select
                      autoFocus
                      value={habit.auto_category || ''}
                      onChange={e => handleSetAutoCategory(habit.id, e.target.value)}
                      onBlur={() => setEditingCat(null)}
                      className="text-xs bg-cd-bg-input border border-cd-border rounded px-1.5 py-1 text-cd-text focus:outline-none focus:border-cd-accent/50"
                    >
                      <option value="">取消关联</option>
                      {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  ) : (
                    <button
                      onClick={() => setEditingCat(habit.id)}
                      title="设置自动关联分类"
                      className={`text-cd-text-secondary hover:text-purple-400 transition p-1 ${habit.auto_category ? 'text-purple-400' : ''}`}
                    >
                      <Link2 size={14} />
                    </button>
                  )}
                  <button onClick={() => handleLog(habit.id)} disabled={completed}
                    className={`w-10 h-10 rounded-full flex items-center justify-center transition ${
                      completed ? 'bg-green-500/20 text-green-400' : 'bg-cd-accent/20 text-cd-accent hover:bg-cd-accent/30'
                    } disabled:opacity-60`}>
                    <Check size={20} />
                  </button>
                  <button onClick={() => handleDelete(habit.id)} className="text-cd-text-secondary hover:text-red-400 transition">
                    <Trash2 size={16} />
                  </button>
                </div>
                {habit.target_count > 1 && (
                  <div className="mt-2 flex gap-1">
                    {Array.from({ length: habit.target_count }).map((_, i) => (
                      <div key={i} className={`flex-1 h-1.5 rounded-full ${i < todayCount ? '' : 'bg-cd-bg-input'}`}
                        style={{ backgroundColor: i < todayCount ? habit.color : undefined }} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
