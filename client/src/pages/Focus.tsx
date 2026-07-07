import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Play, Pause, Square, SkipForward, Coffee, Brain, Zap } from 'lucide-react'
import { startPomodoro, stopPomodoro, getPomodoroStats, getTodayTodos, type PomodoroSession, type TodoV2 } from '../api/client'
import WhiteNoise from '../components/WhiteNoise'

type Phase = 'idle' | 'working' | 'break'

export default function Focus() {
  const [phase, setPhase] = useState<Phase>('idle')
  const [remaining, setRemaining] = useState(25 * 60)
  const [task, setTask] = useState('')
  const [duration, setDuration] = useState(25)
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [interruptedCount, setInterruptedCount] = useState(0)
  const [todayCount, setTodayCount] = useState(0)
  const [todayMin, setTodayMin] = useState(0)
  const [streak, setStreak] = useState(0)
  const [weekStats, setWeekStats] = useState<Array<{ d: string; cnt: number; total_min: number }>>([])
  const [immersive, setImmersive] = useState(false)
  const [todayTodos, setTodayTodos] = useState<TodoV2[]>([])
  const [selectedTodoId, setSelectedTodoId] = useState<number | null>(null)
  const [searchParams] = useSearchParams()
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const startTimeRef = useRef<string>('')
  const durationRef = useRef(25)
  const autoSelectedRef = useRef(false)

  const loadStats = useCallback(async () => {
    try {
      const data = await getPomodoroStats('week')
      setTodayCount(data.today.count)
      setTodayMin(data.today.total_min)
      setStreak(data.streak)
      setWeekStats(data.stats)
    } catch {}
  }, [])

  useEffect(() => { loadStats() }, [loadStats])

  // 加载今日任务
  const loadTodos = useCallback(async () => {
    try {
      const { todos } = await getTodayTodos()
      setTodayTodos(todos.filter(t => t.status !== 'completed' && t.status !== 'archived'))
    } catch {}
  }, [])

  useEffect(() => { loadTodos() }, [loadTodos])

  // 从 URL 参数 ?todo_id=xxx 自动选中对应任务
  useEffect(() => {
    if (autoSelectedRef.current || todayTodos.length === 0) return
    const todoIdParam = searchParams.get('todo_id')
    if (todoIdParam) {
      const id = parseInt(todoIdParam, 10)
      if (!isNaN(id)) {
        setSelectedTodoId(id)
        const todo = todayTodos.find(t => t.id === id)
        if (todo) setTask(todo.title)
      }
    }
    autoSelectedRef.current = true
  }, [todayTodos, searchParams])

  // 倒计时
  useEffect(() => {
    if (phase === 'idle') return
    timerRef.current = setInterval(() => {
      setRemaining(prev => {
        if (prev <= 1) {
          // 时间到
          if (phase === 'working') {
            handleWorkComplete()
          } else {
            handleBreakComplete()
          }
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [phase])

  // 切换应用时记录中断
  useEffect(() => {
    if (phase !== 'working') return
    const handler = () => setInterruptedCount(c => c + 1)
    document.addEventListener('visibilitychange', handler)
    return () => document.removeEventListener('visibilitychange', handler)
  }, [phase])

  const handleStart = async () => {
    const now = new Date().toISOString().replace('T', ' ').substring(0, 19)
    startTimeRef.current = now
    durationRef.current = duration
    setRemaining(duration * 60)
    setInterruptedCount(0)
    setPhase('working')
    try {
      const res = await startPomodoro({ task, duration_min: duration, category: '开发', todo_id: selectedTodoId ?? undefined })
      setSessionId(res.id)
    } catch {}
  }

  const handleWorkComplete = async () => {
    if (sessionId) {
      try { await stopPomodoro({ id: sessionId, status: 'completed', interrupted_count: interruptedCount }) } catch {}
    }
    setSessionId(null)
    setPhase('break')
    setRemaining(5 * 60)
    setTodayCount(c => c + 1)
    setTodayMin(m => m + duration)
    // 通知
    if (window.electronAPI?.showNotification) {
      window.electronAPI.showNotification({ title: '专注完成！', body: `休息5分钟，你今天已完成${todayCount + 1}个番茄钟` })
    }
  }

  const handleBreakComplete = () => {
    setPhase('idle')
    setRemaining(duration * 60)
    loadStats()
  }

  const handleStop = async () => {
    if (sessionId) {
      try { await stopPomodoro({ id: sessionId, status: 'interrupted', interrupted_count: interruptedCount }) } catch {}
    }
    setSessionId(null)
    setPhase('idle')
    setRemaining(duration * 60)
    loadStats()
  }

  const handleSkip = () => {
    if (phase === 'working') handleWorkComplete()
    else handleBreakComplete()
  }

  const mins = Math.floor(remaining / 60)
  const secs = remaining % 60
  const progress = phase === 'idle' ? 0 : ((duration * 60 - remaining) / (duration * 60)) * 100
  const circumference = 2 * Math.PI * 120
  const offset = circumference - (progress / 100) * circumference

  // 沉浸模式
  if (immersive && phase !== 'idle') {
    return (
      <div className="fixed inset-0 z-50 bg-black flex flex-col items-center justify-center" onClick={() => setImmersive(false)}>
        <div className="text-white/40 text-sm mb-4">{phase === 'working' ? '专注中' : '休息中'} · 点击退出沉浸</div>
        <div className="text-white text-[120px] font-bold tabular-nums leading-none">
          {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
        </div>
        {task && <div className="text-white/60 text-xl mt-6">{task}</div>}
        <div className="mt-8"><WhiteNoise autoPlay={true} /></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-cd-text mb-6">专注模式</h1>
      
      {/* 番茄钟主体 */}
      <div className="flex flex-col items-center mb-8">
        <div className="relative w-[280px] h-[280px] mb-6">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 280 280">
            <circle cx="140" cy="140" r="120" fill="none" stroke="#2D2D2D" strokeWidth="12" />
            <circle
              cx="140" cy="140" r="120" fill="none"
              stroke={phase === 'working' ? '#7B68EE' : phase === 'break' ? '#22c55e' : '#2D2D2D'}
              strokeWidth="12" strokeLinecap="round"
              strokeDasharray={circumference} strokeDashoffset={offset}
              className="transition-all duration-1000 ease-linear"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-5xl font-bold text-cd-text tabular-nums">
              {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
            </span>
            <span className="text-sm text-cd-text-secondary mt-2">
              {phase === 'working' ? '专注中' : phase === 'break' ? '休息中' : '准备开始'}
            </span>
            {interruptedCount > 0 && phase === 'working' && (
              <span className="text-xs text-orange-400 mt-1">中断 {interruptedCount} 次</span>
            )}
          </div>
        </div>

        {/* 任务输入 */}
        {phase === 'idle' && (
          <div className="w-full max-w-md space-y-3">
            {/* 关联任务 */}
            {todayTodos.length > 0 ? (
              <select
                value={selectedTodoId ?? ''}
                onChange={e => {
                  const val = e.target.value
                  if (val === '') {
                    setSelectedTodoId(null)
                  } else {
                    const id = parseInt(val, 10)
                    setSelectedTodoId(id)
                    const todo = todayTodos.find(t => t.id === id)
                    if (todo) setTask(todo.title)
                  }
                }}
                className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-4 py-3 text-cd-text focus:outline-none focus:border-purple-400/40"
              >
                <option value="">选择关联任务（可选）</option>
                {[...todayTodos]
                  .sort((a, b) => a.priority - b.priority)
                  .map(t => (
                    <option key={t.id} value={t.id}>
                      [P{t.priority}] {t.title} ({t.target_min}min)
                    </option>
                  ))}
              </select>
            ) : (
              <div className="text-xs text-cd-text-secondary bg-cd-bg-card rounded-lg px-4 py-3 border border-white/5">
                今日还没有分配任务，<a href="#/week-plan" className="text-purple-300 hover:underline">前往周计划分配</a>
              </div>
            )}
            <input
              type="text" value={task} onChange={e => setTask(e.target.value)}
              placeholder="这次专注要做什么？"
              className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-4 py-3 text-cd-text placeholder:text-cd-text-secondary focus:outline-none focus:border-purple-400/40"
            />
            <div className="flex gap-2">
              {[15, 25, 45, 60].map(m => (
                <button key={m} onClick={() => setDuration(m)}
                  className={`flex-1 py-2 rounded-lg text-sm transition ${duration === m ? 'bg-purple-500/20 text-purple-300 border border-purple-400/30' : 'bg-cd-bg-input text-cd-text-secondary border border-white/5'}`}>
                  {m}分钟
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 控制按钮 */}
        <div className="flex gap-3 mt-6">
          {phase === 'idle' && (
            <button onClick={handleStart}
              className="px-8 py-3 bg-purple-500/20 text-purple-300 rounded-xl border border-purple-400/30 hover:bg-purple-500/30 transition flex items-center gap-2 font-medium">
              <Play size={20} /> 开始专注
            </button>
          )}
          {phase !== 'idle' && (
            <>
              <button onClick={handleStop}
                className="px-6 py-3 bg-red-500/10 text-red-400 rounded-xl border border-red-400/20 hover:bg-red-500/20 transition flex items-center gap-2">
                <Square size={18} /> 停止
              </button>
              <button onClick={handleSkip}
                className="px-6 py-3 bg-cd-bg-input text-cd-text-secondary rounded-xl border border-white/5 hover:bg-white/5 transition flex items-center gap-2">
                <SkipForward size={18} /> 跳过
              </button>
              <button onClick={() => setImmersive(true)}
                className="px-6 py-3 bg-cd-bg-input text-cd-text-secondary rounded-xl border border-white/5 hover:bg-white/5 transition flex items-center gap-2">
                <Brain size={18} /> 沉浸
              </button>
            </>
          )}
        </div>
      </div>

      {/* 白噪音 */}
      <div className="mb-8">
        <WhiteNoise autoPlay={false} />
      </div>

      {/* 今日统计 */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-purple-400">{todayCount}</div>
          <div className="text-sm text-cd-text-secondary mt-1">今日番茄</div>
        </div>
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-gold">{todayMin}</div>
          <div className="text-sm text-cd-text-secondary mt-1">专注分钟</div>
        </div>
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-orange-400">{streak}</div>
          <div className="text-sm text-cd-text-secondary mt-1">连续天数</div>
        </div>
      </div>

      {/* 本周趋势 */}
      {weekStats.length > 0 && (
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <h3 className="text-sm text-cd-text-secondary mb-3">本周专注</h3>
          <div className="flex gap-2 items-end h-32">
            {weekStats.map((s, i) => {
              const max = Math.max(...weekStats.map(w => w.total_min), 100)
              const h = (s.total_min / max) * 100
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div className="text-xs text-cd-text-secondary">{s.cnt}</div>
                  <div className="w-full bg-purple-500/20 rounded-t" style={{ height: `${h}%`, minHeight: '4px' }} />
                  <div className="text-xs text-cd-text-secondary">{s.d.substring(5)}</div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
