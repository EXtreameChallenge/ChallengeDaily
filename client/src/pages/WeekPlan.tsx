import { useState, useEffect, useCallback, useMemo } from 'react'
import { Calendar, ChevronLeft, ChevronRight, Plus, X } from 'lucide-react'
import {
  BarChart, Bar, XAxis, Cell as RechartsCell, ResponsiveContainer, Tooltip,
} from 'recharts'
import {
  getWeekPlan, getUnassignedTodos, getWeekPlanStats, getMonthPlan, getMonthPlanStats,
  assignTodo, unassignTodo, createTodo, request, updatePlanMeta,
  getWeekStart, getWeekDates, getMonthKey, getGoals,
  type TodoV2, type WeekPlanData, type WeekPlanStats, type MonthPlanData, type MonthPlanStats,
} from '../api/client'
import { useToast } from '../components/Toast'
import TaskDetailModal from '../components/TaskDetailModal'
import TaskCreateModal from '../components/TaskCreateModal'
import {
  YearView, MonthView, WeekView, DayView,
  StatBlock,
  VIEW_TABS, type ViewMode,
  getTodayStr, formatLocalDate, formatLocalMonth, fmtDate, getISOWeek,
  getYearWeekStarts, DAILY_LIMIT,
} from './plan-views'

// AI 拆解草案任务类型
interface SplitDraftTask {
  title: string
  target_min: number
  category: string
  day?: number
  _checked?: boolean
}

export default function WeekPlan() {
  const { success, error } = useToast()
  const [viewMode, setViewMode] = useState<ViewMode>('week')
  const [weekStart, setWeekStart] = useState(getWeekStart())
  const [monthKey, setMonthKey] = useState(getMonthKey())
  const [yearKey, setYearKey] = useState(new Date().getFullYear())
  const [selectedDate, setSelectedDate] = useState(getTodayStr())
  const [weekPlan, setWeekPlan] = useState<WeekPlanData | null>(null)
  const [unassigned, setUnassigned] = useState<TodoV2[]>([])
  const [weekStats, setWeekStats] = useState<WeekPlanStats | null>(null)
  const [monthPlan, setMonthPlan] = useState<MonthPlanData | null>(null)
  const [monthStats, setMonthStats] = useState<MonthPlanStats | null>(null)
  const [yearMonthStats, setYearMonthStats] = useState<(MonthPlanStats | null)[]>([])
  const [yearWeekStats, setYearWeekStats] = useState<Map<string, WeekPlanStats>>(new Map())
  const [yearLoading, setYearLoading] = useState(false)
  const [yearGoal, setYearGoal] = useState('') // 年度目标（本地状态：API 暂无 year 级 meta）
  const [monthGoalDraft, setMonthGoalDraft] = useState('')
  const [dragId, setDragId] = useState<number | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [modalTodo, setModalTodo] = useState<TodoV2 | null>(null)
  const [splitDraft, setSplitDraft] = useState<SplitDraftTask[] | null>(null)
  const [splitLoading, setSplitLoading] = useState(false)
  const [splitGoalTitle, setSplitGoalTitle] = useState('')
  const [splitGoalDesc, setSplitGoalDesc] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedTaskId, setExpandedTaskId] = useState<number | null>(null)
  const [yearGoals, setYearGoals] = useState<any[]>([])

  // ── getYearWeekStarts wrapper（适配旧接口）──
  const _getYearWeekStarts = useCallback((year: number) => getYearWeekStarts(year, getWeekStart), [getWeekStart])

  const loadWeek = useCallback(async (ws: string) => {
    try {
      const [wp, un, st] = await Promise.all([getWeekPlan(ws), getUnassignedTodos(), getWeekPlanStats(ws)])
      setWeekPlan(wp)
      setUnassigned(un.todos)
      setWeekStats(st)
    } catch {
      error('加载周计划失败')
    }
  }, [error])

  const loadMonth = useCallback(async (mk: string) => {
    try {
      const [mp, st] = await Promise.all([getMonthPlan(mk), getMonthPlanStats(mk)])
      setMonthPlan(mp)
      setMonthStats(st)
      setMonthGoalDraft(mp.goal || '')
    } catch {
      error('加载月计划失败')
    }
  }, [error])

  const loadYear = useCallback(async (year: number) => {
    setYearLoading(true)
    try {
      const monthKeys = Array.from({ length: 12 }, (_, i) => `${year}-${String(i + 1).padStart(2, '0')}`)
      const weekStarts = _getYearWeekStarts(year)
      const [mStats, wStats, goalsRes] = await Promise.all([
        Promise.all(monthKeys.map(mk => getMonthPlanStats(mk).catch(() => null))),
        Promise.all(weekStarts.map(ws => getWeekPlanStats(ws).catch(() => null))),
        getGoals('active').catch(() => ({ goals: [] })),
      ])
      setYearMonthStats(mStats as (MonthPlanStats | null)[])
      const wMap = new Map<string, WeekPlanStats>()
      weekStarts.forEach((ws, i) => {
        const s = wStats[i]
        if (s) wMap.set(ws, s)
      })
      setYearWeekStats(wMap)
      // 过滤出跨越该年的目标
      setYearGoals((goalsRes.goals || []).filter((g: any) => {
        const sy = g.start_date ? new Date(g.start_date).getFullYear() : year
        const ey = g.target_date ? new Date(g.target_date).getFullYear() : year
        return sy <= year && ey >= year
      }))
    } catch {
      error('加载年计划失败')
    } finally {
      setYearLoading(false)
    }
  }, [error, _getYearWeekStarts])

  useEffect(() => {
    if (viewMode === 'month') loadMonth(monthKey)
    else if (viewMode === 'year') loadYear(yearKey)
    else loadWeek(weekStart)
  }, [viewMode, weekStart, monthKey, yearKey, loadWeek, loadMonth, loadYear])

  // ── 导航 ──
  const shiftWeek = (delta: number) => {
    const d = new Date(weekStart + 'T00:00:00')
    d.setDate(d.getDate() + delta * 7)
    setWeekStart(formatLocalDate(d))
  }
  const shiftMonth = (delta: number) => {
    const [y, m] = monthKey.split('-').map(Number)
    setMonthKey(formatLocalMonth(new Date(y, m - 1 + delta, 1)))
  }
  const shiftYear = (delta: number) => setYearKey(y => y + delta)
  const goToday = () => {
    const today = getTodayStr()
    setWeekStart(getWeekStart())
    setMonthKey(getMonthKey())
    setYearKey(new Date().getFullYear())
    setSelectedDate(today)
  }

  // ── 拖拽处理 ──
  const handleDragStart = (todo: TodoV2) => (e: React.DragEvent) => {
    setDragId(todo.id)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(todo.id))
  }
  const handleDragEnd = () => { setDragId(null); setDragOverCol(null) }
  const handleDragOver = (col: string) => (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragOverCol !== col) setDragOverCol(col)
  }
  const handleDragLeave = (col: string) => () => { if (dragOverCol === col) setDragOverCol(null) }
  const handleDropDay = (date: string) => async (e: React.DragEvent) => {
    e.preventDefault()
    setDragOverCol(null)
    const todoId = Number(e.dataTransfer.getData('text/plain'))
    if (!todoId || dragId !== todoId) { setDragId(null); return }
    const existingTasks = weekPlan?.day_tasks?.[date] || []
    const draggedTodo = [...(weekPlan?.day_tasks?.[date] || []), ...unassigned].find(t => t.id === todoId)
    const currentLoad = (existingTasks as TodoV2[]).reduce((s, t) => s + (t.target_min || 0), 0)
    const newTaskMin = draggedTodo?.target_min || 25
    if (currentLoad + newTaskMin > DAILY_LIMIT) {
      error(`${fmtDate(date)} 已达 ${currentLoad}分钟负载（上限 ${DAILY_LIMIT}分钟），无法继续分配`)
      setDragId(null)
      return
    }
    try {
      await assignTodo({ todo_id: todoId, assigned_date: date })
      success(`已分配至 ${fmtDate(date)}`)
      loadWeek(weekStart)
    } catch { error('分配失败') }
    setDragId(null)
  }
  const handleDropUnassigned = async (e: React.DragEvent) => {
    e.preventDefault()
    setDragOverCol(null)
    const todoId = Number(e.dataTransfer.getData('text/plain'))
    if (!todoId || dragId !== todoId) { setDragId(null); return }
    try {
      await unassignTodo(todoId)
      success('已移回待分配')
      loadWeek(weekStart)
    } catch { error('取消分配失败') }
    setDragId(null)
  }

  // ── 新建任务 ──
  const handleTaskCreated = (_id: number) => {
    success('任务已创建')
    if (viewMode === 'month') loadMonth(monthKey)
    else if (viewMode === 'year') loadYear(yearKey)
    else loadWeek(weekStart)
  }

  const openDetail = (todo: TodoV2) => setModalTodo(todo)
  const refreshAfterModal = () => {
    if (viewMode === 'month') loadMonth(monthKey)
    else if (viewMode === 'year') loadYear(yearKey)
    else loadWeek(weekStart)
  }
  const startFocus = (id: number) => { window.location.hash = '#/focus?todo_id=' + id }
  const dates = weekPlan?.dates || getWeekDates(weekStart)

  const toggleExpand = (id: number) => setExpandedTaskId(prev => prev === id ? null : id)

  // 月目标保存
  const saveMonthGoal = async () => {
    if (!monthPlan) return
    if ((monthPlan.goal || '') === monthGoalDraft) return
    try {
      await updatePlanMeta({ plan_type: 'month', plan_key: monthKey, goal: monthGoalDraft })
      success('月目标已更新')
      loadMonth(monthKey)
    } catch { error('保存月目标失败') }
  }

  // ── AI 拆解目标 ──
  const handleAutoSplit = async () => {
    if (!splitGoalTitle.trim()) { error('请先输入目标标题'); return }
    setSplitLoading(true)
    try {
      const res = await request('/api/week-plan/auto-split', {
        method: 'POST',
        body: JSON.stringify({ goal_title: splitGoalTitle, goal_description: splitGoalDesc, week_start: weekStart }),
      }, 30000) as { draft_tasks?: SplitDraftTask[]; error?: string }
      if (res.error) { error(res.error); return }
      setSplitDraft((res.draft_tasks || []).map(t => ({ ...t, _checked: true })))
    } catch (e) {
      error(e instanceof Error ? e.message : 'AI 拆解失败')
    } finally {
      setSplitLoading(false)
    }
  }
  const removeSplitTask = (idx: number) => setSplitDraft(prev => prev ? prev.filter((_, i) => i !== idx) : null)
  const toggleSplitTask = (idx: number) => setSplitDraft(prev => prev ? prev.map((t, i) => i === idx ? { ...t, _checked: !t._checked } : t) : null)
  const updateSplitTask = (idx: number, field: keyof SplitDraftTask, value: string | number) => setSplitDraft(prev => prev ? prev.map((t, i) => i === idx ? { ...t, [field]: value } : t) : null)
  const confirmSplit = async () => {
    if (!splitDraft) return
    const checked = splitDraft.filter(t => t._checked)
    if (checked.length === 0) { error('请至少选择一个任务'); return }
    const weekDates = getWeekDates(weekStart)
    let created = 0
    try {
      // 1. 先创建父任务（周级），形成真实父子关系（修复原本创建平级 day 任务的 bug）
      const totalMin = checked.reduce((s, t) => s + (Number(t.target_min) || 25), 0)
      const parent = await createTodo({
        title: splitGoalTitle.trim(), category: checked[0]?.category || '开发',
        target_min: totalMin, task_level: 'week', week_start: weekStart,
      })
      // 2. 创建子任务时设置 parent_id，task_level='day'
      for (const t of checked) {
        try {
          const dayIdx = (t.day || 1) - 1
          const assignedDate = dayIdx >= 0 && dayIdx < 5 ? weekDates[dayIdx] : ''
          await createTodo({
            title: t.title, category: t.category || '开发', target_min: Number(t.target_min) || 25,
            task_level: 'day', assigned_date: assignedDate || undefined, week_start: weekStart,
            parent_id: parent.id,
          })
          created++
        } catch { /* 单条失败继续 */ }
      }
      success(`已创建 1 个父任务 + ${created} 个子任务`)
    } catch (e) {
      // 父任务创建失败则回退为原逻辑（平级创建）
      for (const t of checked) {
        try {
          const dayIdx = (t.day || 1) - 1
          const assignedDate = dayIdx >= 0 && dayIdx < 5 ? weekDates[dayIdx] : ''
          await createTodo({
            title: t.title, category: t.category || '开发', target_min: Number(t.target_min) || 25,
            task_level: 'day', assigned_date: assignedDate || undefined, week_start: weekStart,
          })
          created++
        } catch { /* 单条失败继续 */ }
      }
      success(`已创建 ${created} 个任务（父子关系未建立）`)
    }
    setSplitDraft(null); setSplitGoalTitle(''); setSplitGoalDesc('')
    if (viewMode === 'month') loadMonth(monthKey); else loadWeek(weekStart)
  }

  // ── 当前视图时间范围标签 ──
  const rangeLabel = useMemo(() => {
    if (viewMode === 'year') return `${yearKey}年`
    if (viewMode === 'month') {
      const [y, m] = monthKey.split('-').map(Number)
      return `${y}年${m}月`
    }
    if (viewMode === 'week') {
      const [y, m] = weekStart.split('-').map(Number)
      const wk = getISOWeek(weekStart)
      const end = dates[6] || weekStart
      return `${y}年${m}月 第${wk}周 · ${fmtDate(weekStart)}-${fmtDate(end)}`
    }
    // day
    const d = new Date(selectedDate + 'T00:00:00')
    const wd = (d.getDay() + 6) % 7
    return `${fmtDate(selectedDate)} ${['周一', '周二', '周三', '周四', '周五', '周六', '周日'][wd]}`
  }, [viewMode, yearKey, monthKey, weekStart, selectedDate, dates])

  // ── 底部数据条（Recharts 柱状图 + 统计）──
  function renderBottomBar() {
    if (!weekStats) return null
    const chartData = weekStats.daily_focus.map(d => ({ date: d.date, focus: d.focus_min, label: fmtDate(d.date).split('/')[1] }))
    return (
      <div className="flex items-center gap-4 px-4 border-t border-cd-border" style={{ height: 56, background: 'var(--cd-card)' }}>
        <div style={{ width: 120, height: 40 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
              <XAxis dataKey="label" hide />
              <Tooltip
                cursor={{ fill: 'transparent' }}
                contentStyle={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', borderRadius: 6, fontSize: 11, color: 'var(--cd-text)' }}
                labelFormatter={(_, p) => p && p[0] ? fmtDate((p[0].payload as { date: string }).date) : ''}
                formatter={(v: number) => [`${v}min`, '专注']}
              />
              <Bar dataKey="focus" radius={[2, 2, 0, 0]}>
                {chartData.map(d => (
                  <RechartsCell key={d.date} fill={d.date === getTodayStr() ? '#7B68EE' : '#7B68EE66'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1" />
        <StatBlock label="完成率" value={`${weekStats.completion_rate}%`} color="#10b981" />
        <StatBlock label="深度工作" value={`${Math.round(weekStats.deep_focus_min)}m`} color="#7B68EE" />
        <StatBlock label="中断次数" value={weekStats.interrupt_count} color="#ef4444" />
        <StatBlock label="连续天数" value={`${weekStats.streak_days}d`} color="#F0C040" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* ── 顶部导航栏 ── */}
      <div className="px-4 pt-2.5 border-b border-cd-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Calendar size={18} className="text-cd-accent" />
            {/* 四级视图 Tab */}
            <div className="flex bg-cd-bg-input rounded-lg p-0.5">
              {VIEW_TABS.map(v => (
                <button key={v.key} onClick={() => setViewMode(v.key)}
                  className={`px-2.5 py-1 text-xs rounded-md transition ${viewMode === v.key ? 'bg-cd-accent/20 text-cd-accent' : 'text-cd-text-secondary hover:text-cd-text'}`}>
                  {v.emoji} {v.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => viewMode === 'year' ? shiftYear(-1) : viewMode === 'month' ? shiftMonth(-1) : shiftWeek(-1)}
              className="p-1.5 rounded-lg hover:bg-cd-hover text-cd-text-secondary transition">
              <ChevronLeft size={16} />
            </button>
            <span className="text-xs text-cd-text-secondary min-w-[160px] text-center tabular-nums">{rangeLabel}</span>
            <button onClick={() => viewMode === 'year' ? shiftYear(1) : viewMode === 'month' ? shiftMonth(1) : shiftWeek(1)}
              className="p-1.5 rounded-lg hover:bg-cd-hover text-cd-text-secondary transition">
              <ChevronRight size={16} />
            </button>
            <button onClick={goToday}
              className="px-2 py-1 text-xs rounded-lg bg-cd-bg-input text-cd-text-secondary hover:bg-cd-hover transition">
              今天
            </button>
            <button onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1 px-3 py-1 text-xs rounded-lg bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition">
              <Plus size={12} /> 新建
            </button>
            <button
              onClick={() => setSplitDraft([])}
              className="flex items-center gap-1 px-3 py-1 text-xs rounded-lg bg-cd-purple/20 text-cd-purple border border-cd-purple/30 hover:bg-cd-purple/30 transition"
              title="AI 拆解月目标为周待办草案"
            >
              🤖 AI 拆解
            </button>
          </div>
        </div>
        {/* 当前层级时间范围副标题 */}
        <div className="text-[10px] text-cd-text-tertiary py-1">
          {viewMode === 'year' && `📅 年计划 · ${yearKey} 年度总览`}
          {viewMode === 'month' && `📆 月计划 · ${monthKey} 月历与目标`}
          {viewMode === 'week' && `📋 周计划 · ${rangeLabel}`}
          {viewMode === 'day' && `✅ 日计划 · ${rangeLabel}`}
        </div>
      </div>

      {/* 主视图区 */}
      <div className="flex-1 overflow-hidden">
        {viewMode === 'year' && weekPlan !== undefined && (
          <YearView
            yearKey={yearKey}
            yearMonthStats={yearMonthStats}
            yearWeekStats={yearWeekStats}
            yearLoading={yearLoading}
            yearGoal={yearGoal}
            setYearGoal={setYearGoal}
            yearGoals={yearGoals}
            getYearWeekStarts={_getYearWeekStarts}
          />
        )}
        {viewMode === 'month' && monthPlan && (
          <MonthView
            monthKey={monthKey}
            monthPlan={monthPlan}
            monthStats={monthStats}
            monthGoalDraft={monthGoalDraft}
            setMonthGoalDraft={setMonthGoalDraft}
            saveMonthGoal={saveMonthGoal}
            openDetail={openDetail}
          />
        )}
        {viewMode === 'week' && weekPlan && (
          <WeekView
            weekPlan={weekPlan}
            dates={dates}
            unassigned={unassigned}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            dragId={dragId}
            dragOverCol={dragOverCol}
            expandedTaskId={expandedTaskId}
            handleDragStart={handleDragStart}
            handleDragEnd={handleDragEnd}
            handleDragOver={handleDragOver}
            handleDragLeave={handleDragLeave}
            handleDropDay={handleDropDay}
            handleDropUnassigned={handleDropUnassigned}
            openDetail={openDetail}
            startFocus={startFocus}
            setShowCreateModal={setShowCreateModal}
            toggleExpand={toggleExpand}
          />
        )}
        {viewMode === 'day' && weekPlan && (
          <DayView
            selectedDate={selectedDate}
            weekPlan={weekPlan}
            weekStart={weekStart}
            dragId={dragId}
            setSelectedDate={setSelectedDate}
            setWeekStart={setWeekStart}
            openDetail={openDetail}
            startFocus={startFocus}
            handleDragStart={handleDragStart}
            handleDragEnd={handleDragEnd}
            setShowCreateModal={setShowCreateModal}
            getWeekStart={getWeekStart}
          />
        )}
      </div>

      {/* 底部数据条（仅周/日视图显示）*/}
      {viewMode !== 'month' && viewMode !== 'year' && renderBottomBar()}

      {/* 任务详情浮层 */}
      <TaskDetailModal todo={modalTodo} onClose={() => setModalTodo(null)} onUpdate={refreshAfterModal} />

      {/* 统一任务创建弹窗 */}
      <TaskCreateModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleTaskCreated}
        defaults={{ week_start: weekStart, assigned_date: viewMode === 'day' ? selectedDate : '' }}
      />

      {/* AI 拆解草案弹窗 */}
      {splitDraft !== null && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="rounded-lg max-w-2xl w-full max-h-[85vh] overflow-auto flex flex-col" style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)' }}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-cd-border">
              <h3 className="text-sm font-semibold text-cd-text">🤖 AI 拆解目标为周待办</h3>
              <button onClick={() => { setSplitDraft(null); setSplitGoalTitle(''); setSplitGoalDesc('') }} className="text-cd-text-tertiary hover:text-cd-text">
                <X size={16} />
              </button>
            </div>

            {/* 目标输入区（草案为空时显示） */}
            {splitDraft.length === 0 && (
              <div className="p-5 space-y-3">
                <div>
                  <label className="text-xs text-cd-text-tertiary block mb-1">目标标题 *</label>
                  <input
                    value={splitGoalTitle}
                    onChange={e => setSplitGoalTitle(e.target.value)}
                    placeholder="例如：完成 v3.1.0 版本开发"
                    className="w-full px-3 py-2 rounded text-sm border border-cd-border"
                    style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                  />
                </div>
                <div>
                  <label className="text-xs text-cd-text-tertiary block mb-1">目标描述（可选）</label>
                  <textarea
                    value={splitGoalDesc}
                    onChange={e => setSplitGoalDesc(e.target.value)}
                    placeholder="补充目标细节、验收标准等"
                    rows={3}
                    className="w-full px-3 py-2 rounded text-sm border border-cd-border resize-none"
                    style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                  />
                </div>
                <div className="text-xs text-cd-text-tertiary">周开始：{weekStart}</div>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => { setSplitDraft(null); setSplitGoalTitle(''); setSplitGoalDesc('') }}
                    className="px-4 py-2 text-xs text-cd-text-tertiary hover:text-cd-text"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleAutoSplit}
                    disabled={splitLoading || !splitGoalTitle.trim()}
                    className="px-4 py-2 text-xs rounded text-white disabled:opacity-50"
                    style={{ background: 'var(--cd-purple)' }}
                  >
                    {splitLoading ? '🤖 拆解中...' : '🤖 开始拆解'}
                  </button>
                </div>
              </div>
            )}

            {/* 草案列表（有任务时显示） */}
            {splitDraft.length > 0 && (
              <>
                <div className="px-5 py-2 text-xs text-cd-text-tertiary border-b border-cd-border">
                  共 {splitDraft.length} 个草案任务，请勾选确认（可编辑标题/分钟数，或删除不需要的项）
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-2">
                  {splitDraft.map((task, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 rounded" style={{ background: 'var(--cd-bg-tertiary)' }}>
                      <input
                        type="checkbox"
                        checked={task._checked !== false}
                        onChange={() => toggleSplitTask(i)}
                        className="rounded"
                      />
                      <input
                        value={task.title}
                        onChange={e => updateSplitTask(i, 'title', e.target.value)}
                        className="flex-1 px-2 py-1 rounded text-sm border border-cd-border"
                        style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                      />
                      <input
                        type="number"
                        value={task.target_min}
                        onChange={e => updateSplitTask(i, 'target_min', Number(e.target.value))}
                        className="w-16 px-2 py-1 rounded text-xs text-center border border-cd-border"
                        style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                        title="预计分钟数"
                      />
                      <span className="text-[10px] text-cd-text-tertiary">min</span>
                      <select
                        value={task.day || 1}
                        onChange={e => updateSplitTask(i, 'day', Number(e.target.value))}
                        className="px-1 py-1 rounded text-[10px] border border-cd-border"
                        style={{ background: 'var(--cd-bg-input)', color: 'var(--cd-text)' }}
                      >
                        {[1, 2, 3, 4, 5].map(d => <option key={d} value={d}>周{['一', '二', '三', '四', '五'][d - 1]}</option>)}
                      </select>
                      <button
                        onClick={() => removeSplitTask(i)}
                        className="text-red-400 hover:text-red-300 px-1"
                        title="删除"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
                <div className="flex justify-end gap-3 px-5 py-3 border-t border-cd-border">
                  <button
                    onClick={() => { setSplitDraft([]); setSplitGoalTitle(''); setSplitGoalDesc('') }}
                    className="px-4 py-2 text-xs text-cd-text-tertiary hover:text-cd-text"
                  >
                    取消
                  </button>
                  <button
                    onClick={confirmSplit}
                    className="px-4 py-2 text-xs rounded text-white"
                    style={{ background: 'var(--cd-green)' }}
                  >
                    确认创建（{splitDraft.filter(t => t._checked !== false).length}）
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
