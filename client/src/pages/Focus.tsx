import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Play, Square, SkipForward, Brain, X, Sparkles, BarChart3, ChevronLeft, ChevronRight } from 'lucide-react'
import { startPomodoro, stopPomodoro, getPomodoroStats, getPomodoroQuality, getTodayTodos, checkPomodoroDistraction, formatLocalTimestamp, getSmartDuration, getPomodoroReport, type TodoV2, POMODORO_SIZES, LONG_BREAK_INTERVAL, type SmartDurationResult, type PomodoroReport } from '../api/client'
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
  const [quality, setQuality] = useState<{ score: number; grade: string; purity: number; completion: number; distraction_count: number }>({ score: 0, grade: '—', purity: 0, completion: 0, distraction_count: 0 })
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
  const [strictMode, setStrictMode] = useState(false)
  const [lockLevel, setLockLevel] = useState(0)  // 0=关 1=L1软提醒 2=L2硬拦截 3=L3锁屏
  const [distractionCount, setDistractionCount] = useState(0)
  const [distractionAlert, setDistractionAlert] = useState<{ app: string; count: number } | null>(null)
  const [resumePrompt, setResumePrompt] = useState<{ remaining: number; phase: Phase } | null>(null)
  const [smartDuration, setSmartDuration] = useState<SmartDurationResult | null>(null)
  const [reportOpen, setReportOpen] = useState(false)
  const [reportData, setReportData] = useState<PomodoroReport | null>(null)
  const [reportDays, setReportDays] = useState(7)
  const [reportLoading, setReportLoading] = useState(false)
  const [searchParams] = useSearchParams()
  const timerRef = useRef<NodeJS.Timeout | null>(null)
  const autoSelectedRef = useRef(false)
  const handleWorkCompleteRef = useRef<() => void>(() => {})
  const handleBreakCompleteRef = useRef<() => void>(() => {})
  const completingRef = useRef(false)
  const remainingRef = useRef(remaining)
  remainingRef.current = remaining

  const sizeConfig = POMODORO_SIZES[pomodoroSize]

  const loadStats = useCallback(async () => {
    try {
      const data = await getPomodoroStats('week')
      setTodayCount(data.today.count)
      setTodayMin(data.today.total_min)
      setStreak(data.streak)
      setWeekStats(data.stats)
      const q = await getPomodoroQuality()
      setQuality(q)
    } catch {}
  }, [])

  useEffect(() => { loadStats() }, [loadStats])

  // P9-3：加载智能时长建议（仅 idle 时加载一次）
  useEffect(() => {
    if (phase !== 'idle') return
    getSmartDuration().then(setSmartDuration).catch(() => {})
  }, [phase])

  // P9-3：加载番茄报告
  const loadReport = useCallback(async (days: number) => {
    setReportLoading(true)
    try {
      const data = await getPomodoroReport(days)
      setReportData(data)
    } catch { setReportData(null) }
    finally { setReportLoading(false) }
  }, [])

  useEffect(() => {
    if (reportOpen) loadReport(reportDays)
  }, [reportOpen, reportDays, loadReport])

  // 根据智能建议自动切换番茄大小
  const applySmartDuration = () => {
    if (!smartDuration) return
    const rec = smartDuration.recommended_min
    // 25 -> big, 20 -> small, 其他保持当前
    if (rec <= 20) setPomodoroSize('small')
    else setPomodoroSize('big')
  }

  // 恢复持久化状态
  useEffect(() => {
    const ps = loadPomodoroState()
    if (!ps || ps.phase === 'idle') return
    const elapsed = Math.floor((Date.now() - ps.startTimestamp) / 1000)
    if (elapsed >= ps.totalSec) {
      setRemaining(0)
    }
  }, [])

  // T5: 检测到未完成番茄时弹窗提示（state 已自动恢复，此处仅做提示）
  useEffect(() => {
    const ps = _initState.current
    if (!ps || ps.phase === 'idle') return
    const elapsed = Math.floor((Date.now() - ps.startTimestamp) / 1000)
    const left = ps.totalSec - elapsed
    if (left > 0) {
      setResumePrompt({ remaining: left, phase: ps.phase })
    }
  }, [])

  // T2: 番茄运行中每 15 秒调用后端分心检测
  const handleStopRef = useRef<() => void>(() => {})
  useEffect(() => {
    if (phase !== 'working' || !sessionId) return
    const interval = setInterval(async () => {
      try {
        const data = await checkPomodoroDistraction(sessionId)
        if (data.is_distraction) {
          setDistractionCount(data.distraction_count)
          // 同步到 interruptedCount，确保停止时回写正确的计数
          setInterruptedCount(data.distraction_count)
          setDistractionAlert({ app: data.app_name, count: data.distraction_count })
          // 通知宠物窗口变红
          window.electronAPI?.sendDistractionAlert?.({ app: data.app_name, count: data.distraction_count })
          if (strictMode) {
            handleStopRef.current()
          }
        }
      } catch { /* 静默失败，不打断专注 */ }
    }, 15000)
    return () => clearInterval(interval)
  }, [phase, sessionId, strictMode])

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
    const curRemaining = override?.remaining ?? remainingRef.current
    const data = {
      phase: override?.phase ?? phase,
      remaining: curRemaining,
      totalSec: override?.totalSec ?? (phase === 'idle' ? sizeConfig.work * 60 : curRemaining + (curRemaining > 0 ? 0 : 0)),
      task: override?.task ?? task,
      duration: override?.duration ?? sizeConfig.work,
    }
    window.electronAPI?.pomodoroWidgetUpdate?.(data)
  }, [phase, task, sizeConfig])

  // 倒计时
  useEffect(() => {
    if (phase === 'idle') return
    syncWidget()
    timerRef.current = setInterval(() => {
      setRemaining(prev => {
        const next = prev > 0 ? prev - 1 : 0
        // 持久化应基于 phase 切换时机，而非每 tick；移除原 savePomodoroState no-op 调用
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
    setDistractionCount(0)
    setDistractionAlert(null)
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
        lock_level: strictMode ? lockLevel : 0,
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
      lock_level: strictMode ? lockLevel : 0,
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
    setDistractionCount(0)
    setDistractionAlert(null)
    clearPomodoroState()
    loadStats()
    window.electronAPI?.pomodoroWidgetHide?.()
  }

  useEffect(() => { handleStopRef.current = handleStop }, [handleStop])

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
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-cd-text">专注模式</h1>
        <button onClick={() => setReportOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-cd-bg-card border border-white/5 rounded-lg text-cd-text-secondary hover:text-cd-text hover:bg-white/5 transition">
          <BarChart3 size={16} /> 番茄报告
        </button>
      </div>

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
            {distractionCount > 0 && phase === 'working' && (
              <span className="text-xs text-red-400 mt-1">已分心 {distractionCount} 次</span>
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
            {/* P9-3：智能时长建议 */}
            {smartDuration && smartDuration.analysis.length > 0 && (
              <div className="flex items-start gap-2 bg-purple-500/10 border border-purple-400/20 rounded-lg px-3 py-2 text-xs">
                <Sparkles size={14} className="text-purple-400 mt-0.5 flex-shrink-0" />
                <div className="flex-1 text-cd-text-secondary">
                  <div className="text-cd-text font-medium">智能建议：{smartDuration.recommended_min} 分钟</div>
                  <div className="mt-0.5">{smartDuration.reason}</div>
                </div>
                {(() => {
                  const rec = smartDuration.recommended_min
                  const matches = (rec <= 20 && pomodoroSize === 'small') || (rec > 20 && pomodoroSize === 'big')
                  return !matches ? (
                    <button onClick={applySmartDuration}
                      className="text-purple-400 hover:text-purple-300 text-[10px] underline whitespace-nowrap">
                      采用
                    </button>
                  ) : null
                })()}
              </div>
            )}
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
            {/* T2: 严格模式开关 + 学霸硬锁机三档 */}
            <div className="flex flex-col gap-1.5">
              <label className="flex items-center gap-2 text-xs text-cd-text-secondary cursor-pointer select-none">
                <input type="checkbox" checked={strictMode} onChange={(e) => setStrictMode(e.target.checked)}
                  className="rounded" />
                学霸模式（分心拦截）
              </label>
              {strictMode && (
                <div className="flex gap-1 ml-5">
                  {[
                    { lv: 1, label: 'L1 软提醒', color: 'text-yellow-400 border-yellow-400/30 bg-yellow-400/10' },
                    { lv: 2, label: 'L2 关进程', color: 'text-orange-400 border-orange-400/30 bg-orange-400/10' },
                    { lv: 3, label: 'L3 锁屏', color: 'text-red-400 border-red-400/30 bg-red-400/10' },
                  ].map(opt => (
                    <button key={opt.lv} onClick={() => setLockLevel(opt.lv)}
                      className={`px-2 py-0.5 rounded text-[10px] border transition ${
                        lockLevel === opt.lv ? opt.color : 'text-cd-text-tertiary border-white/5 bg-cd-bg-input'
                      }`}>
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
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
      <div className="grid grid-cols-3 gap-4 mb-4">
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

      {/* 专注质量评分 — 破解番茄TODO时长陷阱 */}
      {quality.score > 0 && (
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-8">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm text-cd-text-secondary">专注质量评分 · 重质量轻时长</h3>
            <span className={`text-2xl font-bold ${
              quality.grade === 'S' ? 'text-purple-400' :
              quality.grade === 'A' ? 'text-cd-accent' :
              quality.grade === 'B' ? 'text-blue-400' : 'text-cd-text-tertiary'
            }`}>{quality.grade}</span>
          </div>
          <div className="grid grid-cols-4 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-cd-text">{quality.score}</div>
              <div className="text-[10px] text-cd-text-tertiary">质量分</div>
            </div>
            <div>
              <div className="text-lg font-bold text-green-400">{quality.purity}%</div>
              <div className="text-[10px] text-cd-text-tertiary">纯度</div>
            </div>
            <div>
              <div className="text-lg font-bold text-cd-accent">{quality.completion}%</div>
              <div className="text-[10px] text-cd-text-tertiary">完成率</div>
            </div>
            <div>
              <div className="text-lg font-bold text-orange-400">{quality.distraction_count}</div>
              <div className="text-[10px] text-cd-text-tertiary">分心次数</div>
            </div>
          </div>
        </div>
      )}

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

      {/* T2: 分心检测弹窗 */}
      {distractionAlert && (
        <div className="fixed top-4 right-4 p-4 bg-red-500/20 border border-red-500/40 rounded-lg shadow-lg z-50 max-w-sm">
          <div className="flex items-start gap-2">
            <span className="text-red-400 text-lg">⚠️</span>
            <div className="flex-1">
              <p className="text-sm text-cd-text font-medium">检测到分心！</p>
              <p className="text-xs text-cd-text-secondary mt-1">
                当前应用：{distractionAlert.app}<br />
                已分心 {distractionCount} 次
              </p>
              <button onClick={() => setDistractionAlert(null)}
                className="mt-2 text-xs text-cd-blue hover:underline">知道了</button>
            </div>
          </div>
        </div>
      )}

      {/* T5: 番茄中断恢复提示 */}
      {resumePrompt && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-cd-card p-6 rounded-lg border border-cd-border max-w-md">
            <h3 className="text-lg font-medium text-cd-text mb-2">⚠️ 检测到未完成的番茄</h3>
            <p className="text-sm text-cd-text-secondary mb-4">
              剩余时间：{Math.floor(resumePrompt.remaining / 60)} 分 {resumePrompt.remaining % 60} 秒<br />
              阶段：{resumePrompt.phase === 'working' ? '专注中' : '休息中'}
            </p>
            <div className="flex gap-3 justify-end">
              <button onClick={() => { handleStop(); setResumePrompt(null) }}
                className="px-4 py-2 text-sm text-cd-text-tertiary hover:text-cd-text">放弃记录</button>
              <button onClick={() => setResumePrompt(null)}
                className="px-4 py-2 text-sm bg-cd-green text-white rounded hover:opacity-90">继续专注</button>
            </div>
          </div>
        </div>
      )}

      {/* P9-3：番茄报告弹窗 */}
      {reportOpen && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={() => setReportOpen(false)}>
          <div className="bg-cd-bg-card border border-white/10 rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-white/5 sticky top-0 bg-cd-bg-card z-10">
              <h2 className="text-lg font-bold text-cd-text flex items-center gap-2">
                <BarChart3 size={20} className="text-cd-accent" /> 番茄钟报告
              </h2>
              <button onClick={() => setReportOpen(false)} className="text-cd-text-tertiary hover:text-cd-text p-1">
                <X size={20} />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* 时间范围切换 */}
              <div className="flex gap-2">
                {[7, 14, 30].map(d => (
                  <button key={d} onClick={() => setReportDays(d)}
                    className={`px-3 py-1 text-xs rounded-lg border transition ${
                      reportDays === d
                        ? 'bg-cd-accent/20 text-cd-accent border-cd-accent/30'
                        : 'bg-cd-bg-input text-cd-text-secondary border-white/5'
                    }`}>
                    近 {d} 天
                  </button>
                ))}
              </div>

              {reportLoading ? (
                <div className="text-center py-10 text-cd-text-secondary text-sm">加载中…</div>
              ) : !reportData ? (
                <div className="text-center py-10 text-cd-text-secondary text-sm">加载失败</div>
              ) : reportData.total_sessions === 0 ? (
                <div className="text-center py-10 text-cd-text-secondary text-sm">
                  {reportData.message || '该时段内暂无番茄钟记录'}
                </div>
              ) : (
                <>
                  {/* 总览数据 */}
                  <div className="grid grid-cols-4 gap-3">
                    <div className="bg-cd-bg-input rounded-lg p-3 text-center">
                      <div className="text-xl font-bold text-cd-text">{reportData.total_sessions}</div>
                      <div className="text-[10px] text-cd-text-tertiary mt-0.5">总番茄</div>
                    </div>
                    <div className="bg-cd-bg-input rounded-lg p-3 text-center">
                      <div className="text-xl font-bold text-green-400">{reportData.completed_sessions}</div>
                      <div className="text-[10px] text-cd-text-tertiary mt-0.5">已完成</div>
                    </div>
                    <div className="bg-cd-bg-input rounded-lg p-3 text-center">
                      <div className="text-xl font-bold text-cd-accent">{Math.round((reportData.completion_rate || 0) * 100)}%</div>
                      <div className="text-[10px] text-cd-text-tertiary mt-0.5">完成率</div>
                    </div>
                    <div className="bg-cd-bg-input rounded-lg p-3 text-center">
                      <div className="text-xl font-bold text-gold">{reportData.total_focus_hour}</div>
                      <div className="text-[10px] text-cd-text-tertiary mt-0.5">专注小时</div>
                    </div>
                  </div>

                  {/* 最佳时段 */}
                  {reportData.best_period && (
                    <div className="bg-purple-500/10 border border-purple-400/20 rounded-lg p-3 text-sm">
                      <span className="text-purple-400 font-medium">★ 最佳时段：</span>
                      <span className="text-cd-text-secondary ml-1">
                        {reportData.best_period}（完成率 {Math.round((reportData.best_period_completion_rate || 0) * 100)}%）
                      </span>
                    </div>
                  )}

                  {/* 时段分析 */}
                  {reportData.period_stats && Object.keys(reportData.period_stats).length > 0 && (
                    <div>
                      <h3 className="text-sm text-cd-text-secondary mb-2">时段分布</h3>
                      <div className="grid grid-cols-4 gap-2">
                        {['上午', '下午', '晚间', '夜间'].map(p => {
                          const ps = reportData.period_stats?.[p]
                          if (!ps || ps.total === 0) return null
                          const rate = Math.round((ps.completed / ps.total) * 100)
                          return (
                            <div key={p} className="bg-cd-bg-input rounded-lg p-2 text-center">
                              <div className="text-xs text-cd-text font-medium">{p}</div>
                              <div className="text-lg font-bold text-cd-text mt-1">{ps.total}</div>
                              <div className="text-[10px] text-green-400">{rate}%</div>
                              <div className="text-[10px] text-cd-text-tertiary">{ps.min}min</div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* 每日趋势 */}
                  {reportData.daily_trend && reportData.daily_trend.length > 0 && (
                    <div>
                      <h3 className="text-sm text-cd-text-secondary mb-2">每日趋势</h3>
                      <div className="flex gap-1 items-end h-24 bg-cd-bg-input rounded-lg p-2">
                        {reportData.daily_trend.map((d, i) => {
                          const max = Math.max(...reportData.daily_trend!.map(x => x.min), 60)
                          const h = (d.min / max) * 100
                          return (
                            <div key={i} className="flex-1 flex flex-col items-center justify-end" title={`${d.date}: ${d.min}min`}>
                              <div className="w-full bg-cd-accent/30 rounded-t hover:bg-cd-accent/50 transition"
                                style={{ height: `${Math.max(h, 2)}%`, minHeight: '2px' }} />
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {/* 任务关联 */}
                  {reportData.total_sessions && reportData.total_sessions > 0 && (
                    <div className="bg-cd-bg-input rounded-lg p-3 text-sm flex items-center justify-between">
                      <span className="text-cd-text-secondary">任务关联率</span>
                      <span className="text-cd-text font-medium">
                        {Math.round((reportData.linked_task_ratio || 0) * 100)}%
                        <span className="text-cd-text-tertiary text-xs ml-2">
                          ({reportData.linked_task_count} 个不同任务)
                        </span>
                      </span>
                    </div>
                  )}

                  {/* 改进建议 */}
                  {reportData.suggestions && reportData.suggestions.length > 0 && (
                    <div>
                      <h3 className="text-sm text-cd-text-secondary mb-2">改进建议</h3>
                      <div className="space-y-1.5">
                        {reportData.suggestions.map((s, i) => (
                          <div key={i} className="flex items-start gap-2 bg-cd-bg-input rounded-lg p-2.5 text-xs text-cd-text-secondary">
                            <span className="text-cd-accent mt-0.5">→</span>
                            <span>{s}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
