import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Play, Square, SkipForward, Brain, X } from 'lucide-react'
import { startPomodoro, stopPomodoro, getPomodoroStats, getTodayTodos, formatLocalTimestamp, type TodoV2, POMODORO_SIZES, LONG_BREAK_INTERVAL } from '../api/client'
import WhiteNoise from '../components/WhiteNoise'

type Phase = 'idle' | 'working' | 'short_break' | 'long_break'
type PomodoroSize = 'big' | 'small'

// ── 番茄钟状态持久化 ──
const POMODORO_STORAGE_KEY = 'cd_pomodoro_state_v2'

interface PersistedPomodoro {
  phase: Phase
  startTimestamp: number
  totalSec: number
  task: string
  sessionId: number | null
  interruptedCount: number
  selectedTodoId: number | null
  pomodoroIndex: number      // 当前第几个番茄（1-based）
  totalPomodoros: number     // 计划总番茄数
  pomodoroSize: PomodoroSize // 大/小番茄
  completedPomodoros: number // 本次连续执行中已完成的番茄数
}

function savePomodoroState(state: PersistedPomodoro) {
  try { localStorage.setItem(POMODORO_STORAGE_KEY, JSON.stringify(state)) } catch {}
}

function loadPomodoroState(): PersistedPomodoro | null {
  try {
    const raw = localStorage.getItem(POMODORO_STORAGE_KEY)
    if (!raw) return null
    const data = JSON.parse(raw) as PersistedPomodoro
    if (Date.now() - data.startTimestamp > 6 * 3600 * 1000) {
      clearPomodoroState()
      return null
    }
    return data
  } catch { return null }
}

function clearPomodoroState() {
  try { localStorage.removeItem(POMODORO_STORAGE_KEY) } catch {}
}

export default function Focus() {
  const _initState = useRef<PersistedPomodoro | null>(null)
  if (_initState.current === null) {
    _initState.current = loadPomodoroState()
  }
  const _ps = _initState.current

  const [phase, setPhase] = useState<Phase>(() => {
    if (!_ps || _ps.phase === 'idle') return 'idle'
    const elapsed = Math.floor((Date.now() - _ps.startTimestamp) / 1000)
    if (elapsed >= _ps.totalSec) return 'idle'
    return _ps.phase
  })
  const [remaining, setRemaining] = useState(() => {
    if (!_ps || _ps.phase === 'idle') return 25 * 60
    const elapsed = Math.floor((Date.now() - _ps.startTimestamp) / 1000)
    const left = _ps.totalSec - elapsed
    return left > 0 ? left : 0
  })
  const [task, setTask] = useState(() => _ps?.task ?? '')
  const [sessionId, setSessionId] = useState<number | null>(() => _ps?.sessionId ?? null)
  const [interruptedCount, setInterruptedCount] = useState(() => _ps?.interruptedCount ?? 0)
  const [todayCount, setTodayCount] = useState(0)
  const [todayMin, setTodayMin] = useState(0)
  const [streak, setStreak] = useState(0)
  const [weekStats, setWeekStats] = useState<Array<{ d: string; cnt: number; total_min: number }>>([])
  const [immersive, setImmersive] = useState(false)
  const [todayTodos, setTodayTodos] = useState<TodoV2[]>([])
  const [selectedTodoId, setSelectedTodoId] = useState<number | null>(() => _ps?.selectedTodoId ?? null)
  const [pomodoroIndex, setPomodoroIndex] = useState(() => _ps?.pomodoroIndex ?? 1)
  const [totalPomodoros, setTotalPomodoros] = useState(() => _ps?.totalPomodoros ?? 1)
  const [pomodoroSize, setPomodoroSize] = useState<PomodoroSize>(() => _ps?.pomodoroSize ?? 'big')
  const [completedPomodoros, setCompletedPomodoros] = useState(() => _ps?.completedPomodoros ?? 0)
  const [searchParams] = useSearchParams()
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const autoSelectedRef = useRef(false)
  const handleWorkCompleteRef = useRef<() => void>(() => {})
  const handleBreakCompleteRef = useRef<() => void>(() => {})
  const completingRef = useRef(false)

  const sizeConfig = POMODORO_SIZES[pomodoroSize]

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

  // 恢复持久化状态
  useEffect(() => {
    const ps = loadPomodoroState()
    if (!ps || ps.phase === 'idle') return
    const elapsed = Math.floor((Date.now() - ps.startTimestamp) / 1000)
    if (elapsed >= ps.totalSec) {
      setRemaining(0)
    }
  }, [])

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
    if (autoSelectedRef.current) return
    const todoIdParam = searchParams.get('todo_id')
    if (todoIdParam) {
      const id = parseInt(todoIdParam, 10)
      if (!isNaN(id)) {
        setSelectedTodoId(id)
        // 从任务列表中查找，设置番茄数和大小
        const todo = todayTodos.find(t => t.id === id)
        if (todo) {
          setTask(todo.title)
          setPomodoroSize((todo.pomodoro_size as PomodoroSize) || 'big')
          setTotalPomodoros(todo.estimated_pomodoros || 1)
        }
        autoSelectedRef.current = true
      }
    }
  }, [todayTodos, searchParams])

  // ── 番茄钟悬浮窗同步 ──
  const syncWidget = useCallback((override?: Partial<{ phase: Phase; remaining: number; totalSec: number; task: string; duration: number }>) => {
    const data = {
      phase: override?.phase ?? phase,
      remaining: override?.remaining ?? remaining,
      totalSec: override?.totalSec ?? (phase === 'idle' ? sizeConfig.work * 60 : remaining + (remaining > 0 ? 0 : 0)),
      task: override?.task ?? task,
      duration: override?.duration ?? sizeConfig.work,
    }
    window.electronAPI?.pomodoroWidgetUpdate?.(data)
  }, [phase, remaining, task, sizeConfig])

  // 倒计时
  useEffect(() => {
    if (phase === 'idle') return
    syncWidget()
    timerRef.current = setInterval(() => {
      setRemaining(prev => {
        const next = prev > 0 ? prev - 1 : 0
        const ps = loadPomodoroState()
        if (ps) savePomodoroState({ ...ps, totalSec: ps.totalSec })
        return next
      })
    }, 1000)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [phase, syncWidget])

  // remaining 变化时同步悬浮窗
  useEffect(() => {
    if (phase === 'idle') return
    syncWidget()
  }, [remaining, phase, syncWidget])

  // remaining 归零时触发完成回调
  useEffect(() => {
    if (remaining > 0 || phase === 'idle') {
      completingRef.current = false
      return
    }
    if (completingRef.current) return
    completingRef.current = true
    if (phase === 'working') {
      handleWorkCompleteRef.current()
    } else {
      handleBreakCompleteRef.current()
    }
  }, [remaining, phase])

  // 切换应用时记录中断
  useEffect(() => {
    if (phase !== 'working') return
    const handler = () => setInterruptedCount(c => c + 1)
    document.addEventListener('visibilitychange', handler)
    return () => document.removeEventListener('visibilitychange', handler)
  }, [phase])

  // ── 核心逻辑：开始一个任务的连续番茄执行 ──
  const handleStart = async () => {
    const workSec = sizeConfig.work * 60
    setRemaining(workSec)
    setInterruptedCount(0)
    setPomodoroIndex(1)
    setCompletedPomodoros(0)
    // 如果没有选任务，默认1个番茄；选了任务，读取其预估番茄数
    const todo = selectedTodoId ? todayTodos.find(t => t.id === selectedTodoId) : null
    const totalPomo = todo?.estimated_pomodoros || 1
    setTotalPomodoros(totalPomo)
    setPhase('working')

    savePomodoroState({
      phase: 'working',
      startTimestamp: Date.now(),
      totalSec: workSec,
      task,
      sessionId: null,
      interruptedCount: 0,
      selectedTodoId,
      pomodoroIndex: 1,
      totalPomodoros: totalPomo,
      pomodoroSize,
      completedPomodoros: 0,
    })
    syncWidget({ phase: 'working', remaining: workSec, totalSec: workSec, task })

    try {
      const category = todo?.category || '开发'
      const res = await startPomodoro({
        task,
        duration_min: sizeConfig.work,
        category,
        todo_id: selectedTodoId ?? undefined,
        pomodoro_index: 1,
        total_pomodoros: totalPomo,
      })
      setSessionId(res.id)
      // 后端可能根据 todo 自动调整了 duration_min 和 total_pomodoros
      if (res.total_pomodoros && res.total_pomodoros > 1) {
        setTotalPomodoros(res.total_pomodoros)
      }
      if (res.duration_min && res.duration_min !== sizeConfig.work) {
        // 后端根据 todo.pomodoro_size 调整了工作时长
        setRemaining(res.duration_min * 60)
      }
      const ps = loadPomodoroState()
      if (ps) savePomodoroState({ ...ps, sessionId: res.id, totalPomodoros: res.total_pomodoros || totalPomo })
    } catch {}
  }

  // ── 工作番茄完成 → 判断进入短休息还是长休息 ──
  const handleWorkComplete = async () => {
    if (sessionId) {
      try { await stopPomodoro({ id: sessionId, status: 'completed', interrupted_count: interruptedCount }) } catch {}
    }
    const newCompleted = completedPomodoros + 1
    setCompletedPomodoros(newCompleted)
    setTodayCount(c => c + 1)
    setTodayMin(m => m + sizeConfig.work)

    // 判断：是否所有预估番茄都已完成？
    const allDone = newCompleted >= totalPomodoros

    if (allDone) {
      // 全部完成 → 长休息
      const breakSec = sizeConfig.long_break * 60
      setPhase('long_break')
      setRemaining(breakSec)
      savePomodoroState({
        phase: 'long_break',
        startTimestamp: Date.now(),
        totalSec: breakSec,
        task,
        sessionId: null,
        interruptedCount: 0,
        selectedTodoId,
        pomodoroIndex,
        totalPomodoros,
        pomodoroSize,
        completedPomodoros: newCompleted,
      })
      syncWidget({ phase: 'long_break', remaining: breakSec, totalSec: breakSec, task })
      // 通知
      if (window.electronAPI?.showNotification) {
        window.electronAPI.showNotification({ title: '任务完成！', body: `${totalPomodoros}个番茄钟全部完成，长休息${sizeConfig.long_break}分钟` })
      }
    } else {
      // 还有番茄 → 短休息（每4个番茄一次长休息）
      const isLongBreak = newCompleted % LONG_BREAK_INTERVAL === 0
      const breakSec = (isLongBreak ? sizeConfig.long_break : sizeConfig.short_break) * 60
      const breakPhase = isLongBreak ? 'long_break' : 'short_break'
      setPhase(breakPhase)
      setRemaining(breakSec)
      savePomodoroState({
        phase: breakPhase,
        startTimestamp: Date.now(),
        totalSec: breakSec,
        task,
        sessionId: null,
        interruptedCount: 0,
        selectedTodoId,
        pomodoroIndex,
        totalPomodoros,
        pomodoroSize,
        completedPomodoros: newCompleted,
      })
      syncWidget({ phase: breakPhase, remaining: breakSec, totalSec: breakSec, task })
      if (window.electronAPI?.showNotification) {
        window.electronAPI.showNotification({ title: '番茄完成！', body: `第${newCompleted}/${totalPomodoros}个，休息${isLongBreak ? sizeConfig.long_break : sizeConfig.short_break}分钟` })
      }
    }
    setSessionId(null)
  }

  // ── 休息完成 → 自动进入下一个工作番茄（或全部结束回到 idle） ──
  const handleBreakComplete = () => {
    const allDone = completedPomodoros >= totalPomodoros

    if (allDone) {
      // 所有番茄完成 → 回到 idle
      setPhase('idle')
      setRemaining(sizeConfig.work * 60)
      clearPomodoroState()
      loadStats()
      window.electronAPI?.pomodoroWidgetHide?.()
      return
    }

    // 还有番茄 → 自动开始下一个工作番茄
    const nextIndex = completedPomodoros + 1
    const workSec = sizeConfig.work * 60
    setPomodoroIndex(nextIndex)
    setRemaining(workSec)
    setInterruptedCount(0)
    setPhase('working')

    savePomodoroState({
      phase: 'working',
      startTimestamp: Date.now(),
      totalSec: workSec,
      task,
      sessionId: null,
      interruptedCount: 0,
      selectedTodoId,
      pomodoroIndex: nextIndex,
      totalPomodoros,
      pomodoroSize,
      completedPomodoros,
    })
    syncWidget({ phase: 'working', remaining: workSec, totalSec: workSec, task })

    // 异步记录到后端
    startPomodoro({
      task,
      duration_min: sizeConfig.work,
      category: todayTodos.find(t => t.id === selectedTodoId)?.category || '开发',
      todo_id: selectedTodoId ?? undefined,
      pomodoro_index: nextIndex,
      total_pomodoros: totalPomodoros,
    }).then(res => {
      setSessionId(res.id)
      const ps = loadPomodoroState()
      if (ps) savePomodoroState({ ...ps, sessionId: res.id })
    }).catch(() => {})
  }

  useEffect(() => { handleWorkCompleteRef.current = handleWorkComplete }, [handleWorkComplete])
  useEffect(() => { handleBreakCompleteRef.current = handleBreakComplete }, [handleBreakComplete])

  const handleStop = async () => {
    if (sessionId) {
      try { await stopPomodoro({ id: sessionId, status: 'interrupted', interrupted_count: interruptedCount }) } catch {}
    }
    setSessionId(null)
    setPhase('idle')
    setRemaining(sizeConfig.work * 60)
    clearPomodoroState()
    loadStats()
    window.electronAPI?.pomodoroWidgetHide?.()
  }

  const handleSkip = () => {
    if (completingRef.current) return
    completingRef.current = true
    if (phase === 'working') handleWorkComplete()
    else handleBreakComplete()
  }

  const mins = Math.floor(remaining / 60)
  const secs = remaining % 60
  const currentPhaseTotalSec = phase === 'working'
    ? sizeConfig.work * 60
    : phase === 'short_break'
    ? sizeConfig.short_break * 60
    : phase === 'long_break'
    ? sizeConfig.long_break * 60
    : sizeConfig.work * 60
  const progress = phase === 'idle' ? 0 : ((currentPhaseTotalSec - remaining) / currentPhaseTotalSec) * 100
  const circumference = 2 * Math.PI * 120
  const offset = circumference - (progress / 100) * circumference

  const phaseLabel = phase === 'working' ? '专注中'
    : phase === 'short_break' ? '短休息'
    : phase === 'long_break' ? '长休息'
    : '准备开始'

  const phaseColor = phase === 'working' ? '#7B68EE'
    : (phase === 'short_break' || phase === 'long_break') ? '#22c55e'
    : '#2D2D2D'

  // 番茄进度指示器
  const pomodoroProgressDots = () => {
    const dots = []
    for (let i = 1; i <= totalPomodoros; i++) {
      const isDone = i <= completedPomodoros
      const isCurrent = i === pomodoroIndex && phase === 'working'
      dots.push(
        <span key={i} className={`text-lg ${isDone ? 'opacity-100' : isCurrent ? 'opacity-80 animate-pulse' : 'opacity-25'}`}>
          🍅
        </span>
      )
    }
    return dots
  }

  // 沉浸模式
  if (immersive && phase !== 'idle') {
    return (
      <div className="fixed inset-0 z-50 bg-black flex flex-col items-center justify-center select-none">
        <button onClick={() => setImmersive(false)}
          className="absolute top-6 right-6 text-white/30 hover:text-white/70 transition p-2 rounded-full hover:bg-white/5"
          title="退出沉浸模式">
          <X size={24} />
        </button>
        <div className="text-white/40 text-sm mb-2">{phaseLabel}</div>
        {/* 番茄进度 */}
        {totalPomodoros > 1 && (
          <div className="flex gap-1 mb-4">{pomodoroProgressDots()}</div>
        )}
        <div className="text-white text-[120px] font-bold tabular-nums leading-none">
          {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
        </div>
        {task && <div className="text-white/60 text-xl mt-6">{task}</div>}
        <div className="text-white/30 text-sm mt-2">
          {totalPomodoros > 1 && `第 ${pomodoroIndex}/${totalPomodoros} 个`}
        </div>
        <div className="mt-8"><WhiteNoise autoPlay={false} /></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold text-cd-text mb-6">专注模式</h1>

      {/* 番茄钟主体 */}
      <div className="flex flex-col items-center mb-8">
        <div className="relative w-[280px] h-[280px] mb-4">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 280 280">
            <circle cx="140" cy="140" r="120" fill="none" stroke="#2D2D2D" strokeWidth="12" />
            <circle
              cx="140" cy="140" r="120" fill="none"
              stroke={phaseColor}
              strokeWidth="12" strokeLinecap="round"
              strokeDasharray={circumference} strokeDashoffset={offset}
              className="transition-all duration-1000 ease-linear"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-5xl font-bold text-cd-text tabular-nums">
              {String(mins).padStart(2, '0')}:{String(secs).padStart(2, '0')}
            </span>
            <span className="text-sm text-cd-text-secondary mt-2">{phaseLabel}</span>
            {interruptedCount > 0 && phase === 'working' && (
              <span className="text-xs text-orange-400 mt-1">中断 {interruptedCount} 次</span>
            )}
          </div>
        </div>

        {/* 番茄进度指示 */}
        {phase !== 'idle' && totalPomodoros > 1 && (
          <div className="flex items-center gap-1.5 mb-4">
            {pomodoroProgressDots()}
            <span className="text-sm text-cd-text-secondary ml-2 tabular-nums">
              {completedPomodoros}/{totalPomodoros}
            </span>
          </div>
        )}

        {/* 任务输入区（idle 时显示） */}
        {phase === 'idle' && (
          <div className="w-full max-w-md space-y-3">
            {todayTodos.length > 0 ? (
              <select
                value={selectedTodoId ?? ''}
                onChange={e => {
                  const val = e.target.value
                  if (val === '') {
                    setSelectedTodoId(null)
                    setPomodoroSize('big')
                    setTotalPomodoros(1)
                  } else {
                    const id = parseInt(val, 10)
                    setSelectedTodoId(id)
                    const todo = todayTodos.find(t => t.id === id)
                    if (todo) {
                      setTask(todo.title)
                      setPomodoroSize((todo.pomodoro_size as PomodoroSize) || 'big')
                      setTotalPomodoros(todo.estimated_pomodoros || 1)
                    }
                  }
                }}
                className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-4 py-3 text-cd-text focus:outline-none focus:border-cd-accent/40"
              >
                <option value="">选择关联任务（可选）</option>
                {[...todayTodos]
                  .sort((a, b) => a.priority - b.priority)
                  .map(t => (
                    <option key={t.id} value={t.id}>
                      [P{t.priority}] {t.title} ({t.estimated_pomodoros || 1}🍅 {t.pomodoro_size === 'small' ? '小' : '大'})
                    </option>
                  ))}
              </select>
            ) : (
              <div className="text-xs text-cd-text-secondary bg-cd-bg-card rounded-lg px-4 py-3 border border-white/5">
                今日还没有分配任务，<a href="#/week-plan" className="text-cd-accent hover:underline">前往周计划分配</a>
              </div>
            )}
            <input
              type="text" value={task} onChange={e => setTask(e.target.value)}
              placeholder="这次专注要做什么？"
              className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-4 py-3 text-cd-text placeholder:text-cd-text-secondary focus:outline-none focus:border-cd-accent/40"
            />
            {/* 番茄大小选择 */}
            <div className="flex gap-2">
              {(['big', 'small'] as PomodoroSize[]).map(s => {
                const cfg = POMODORO_SIZES[s]
                return (
                  <button key={s} onClick={() => setPomodoroSize(s)}
                    className={`flex-1 py-2.5 rounded-lg text-sm transition border ${
                      pomodoroSize === s
                        ? 'bg-cd-accent/20 text-cd-accent border-cd-accent/30'
                        : 'bg-cd-bg-input text-cd-text-secondary border-white/5'
                    }`}>
                    <div className="font-medium">{s === 'big' ? '大番茄' : '小番茄'}</div>
                    <div className="text-[10px] opacity-60">{cfg.work}+{cfg.short_break}min</div>
                  </button>
                )
              })}
            </div>
            {/* 预估番茄数 */}
            <div className="flex items-center gap-3">
              <span className="text-sm text-cd-text-secondary">预估番茄</span>
              <div className="flex items-center gap-2 bg-cd-bg-input border border-white/5 rounded-lg px-3 py-1.5">
                <button onClick={() => setTotalPomodoros(Math.max(1, totalPomodoros - 1))}
                  className="w-6 h-6 flex items-center justify-center rounded bg-white/5 text-cd-text hover:bg-white/10 text-sm">-</button>
                <span className="text-xl font-bold text-cd-text tabular-nums w-6 text-center">{totalPomodoros}</span>
                <button onClick={() => setTotalPomodoros(Math.min(12, totalPomodoros + 1))}
                  className="w-6 h-6 flex items-center justify-center rounded bg-white/5 text-cd-text hover:bg-white/10 text-sm">+</button>
              </div>
              <span className="text-xs text-cd-text-secondary">
                = {totalPomodoros * sizeConfig.work}分钟专注
              </span>
            </div>
          </div>
        )}

        {/* 控制按钮 */}
        <div className="flex gap-3 mt-6">
          {phase === 'idle' && (
            <button onClick={handleStart}
              className="px-8 py-3 bg-cd-accent/20 text-cd-accent rounded-xl border border-cd-accent/30 hover:bg-cd-accent/30 transition flex items-center gap-2 font-medium">
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
          <div className="text-2xl font-bold text-cd-accent">{todayCount}</div>
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
                  <div className="w-full bg-cd-accent/20 rounded-t" style={{ height: `${h}%`, minHeight: '4px' }} />
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
