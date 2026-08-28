import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'

/**
 * 接力链引擎（Relay Engine）
 *
 * 设计理念：上一个功能的结束，自然引导到下一个功能的开始
 * - 监听系统事件（活动变化、番茄钟完成、待办完成等）
 * - 匹配接力链规则，生成推荐卡片
 * - 用户点击行动按钮后自动执行，形成闭环
 *
 * 科学依据：
 * - 执行意图（Implementation Intentions）："如果X发生，就做Y"比"我要做Y"执行率高2-3倍
 * - 决策疲劳：系统推荐下一步，减少用户"该干什么"的决策消耗
 * - 习惯回路：提示（接力卡片）→ 行为（点击行动）→ 奖赏（完成反馈）
 */

// 接力链触发事件类型
export type RelayEventType =
  | 'pomodoro_completed'      // 番茄钟完成
  | 'pomodoro_distraction'    // 番茄钟期间分心
  | 'todo_completed'           // 待办完成
  | 'report_generated'         // 日报生成
  | 'anomaly_detected'         // 异常数据检测
  | 'morning_brief'            // 早晨晨报
  | 'evening_review'           // 晚间复盘
  | 'habit_at_risk'            // 习惯即将中断
  | 'meeting_ended'            // 会议结束
  | 'low_energy'               // 低能量时段

// 接力链行动类型
export type RelayActionType =
  | 'start_pomodoro'           // 开始番茄钟
  | 'complete_todo'             // 完成待办
  | 'create_todo'               // 创建待办
  | 'create_goal'               // 创建目标
  | 'create_habit'              // 创建习惯
  | 'block_app'                 // 屏蔽应用
  | 'navigate'                  // 跳转页面
  | 'show_insight'              // 显示洞察
  | 'take_break'                // 休息提醒
  | 'write_diary'               // 写日记

// 接力行动
export interface RelayAction {
  type: RelayActionType
  label: string
  data?: Record<string, unknown>
  primary?: boolean
}

// 接力卡片
export interface RelayCard {
  id: string
  event: RelayEventType
  title: string
  message: string
  icon?: string
  actions: RelayAction[]
  dismissible: boolean
  createdAt: number
  expiresAt?: number
}

// 接力链规则
export interface RelayRule {
  id: string
  event: RelayEventType
  condition?: (data: Record<string, unknown>) => boolean
  generateCard: (data: Record<string, unknown>) => Omit<RelayCard, 'id' | 'event' | 'createdAt'>
}

// 引擎上下文
interface RelayEngineContextType {
  cards: RelayCard[]
  triggerEvent: (event: RelayEventType, data?: Record<string, unknown>) => void
  dismissCard: (id: string) => void
  executeAction: (cardId: string, actionIndex: number) => void
  registerRule: (rule: RelayRule) => void
}

const RelayEngineContext = createContext<RelayEngineContextType | null>(null)

export function useRelayEngine() {
  const ctx = useContext(RelayEngineContext)
  if (!ctx) throw new Error('useRelayEngine must be used within RelayEngineProvider')
  return ctx
}

// 内置接力链规则
const BUILTIN_RULES: RelayRule[] = [
  // 规则1：番茄钟完成 → 休息或继续
  {
    id: 'pomodoro-complete-break',
    event: 'pomodoro_completed',
    generateCard: (data) => ({
      title: '🍅 专注完成！',
      message: `完成了 ${data.durationMin || 25} 分钟专注。休息一下，还是继续下一个？`,
      icon: '🍅',
      actions: [
        { type: 'take_break', label: '☕ 休息5分钟', primary: true },
        { type: 'start_pomodoro', label: '▶ 继续专注' },
      ],
      dismissible: true,
      expiresAt: Date.now() + 5 * 60 * 1000,
    }),
  },

  // 规则2：番茄钟分心 → 屏蔽干扰
  {
    id: 'pomodoro-distraction-shield',
    event: 'pomodoro_distraction',
    condition: (data) => (data.switchCount || 0) >= 2,
    generateCard: (data) => ({
      title: '🤖 分心提醒',
      message: `你刚切到 ${data.appName || '干扰应用'} ${data.switchCount || 2} 次了。要帮你屏蔽一会儿吗？`,
      icon: '🤖',
      actions: [
        { type: 'block_app', label: '🛡️ 屏蔽5分钟', primary: true, data: { app: data.appName, duration: 5 } },
        { type: 'navigate', label: '我在处理工作' },
      ],
      dismissible: true,
      expiresAt: Date.now() + 2 * 60 * 1000,
    }),
  },

  // 规则3：待办完成 → 下一个任务
  {
    id: 'todo-complete-next',
    event: 'todo_completed',
    generateCard: (data) => ({
      title: '✅ 任务完成！',
      message: `"${data.todoTitle || '任务'}" 完成了。接下来做什么？`,
      icon: '✅',
      actions: data.nextTodo
        ? [
            { type: 'start_pomodoro', label: `▶ 开始：${data.nextTodoTitle || '下一个任务'}`, primary: true, data: { todoId: data.nextTodoId } },
            { type: 'navigate', label: '查看所有待办' },
          ]
        : [
            { type: 'navigate', label: '📋 查看待办列表', primary: true },
            { type: 'write_diary', label: '📝 记录一下' },
          ],
      dismissible: true,
      expiresAt: Date.now() + 3 * 60 * 1000,
    }),
  },

  // 规则4：日报异常 → 改进建议
  {
    id: 'report-anomaly-action',
    event: 'anomaly_detected',
    generateCard: (data) => ({
      title: '📊 发现一个模式',
      message: data.message || '你的数据中有一个值得注意的模式。要看看怎么改进吗？',
      icon: '📊',
      actions: [
        { type: 'show_insight', label: '🔍 查看详情', primary: true },
        { type: 'create_goal', label: '🎯 设为改进目标' },
      ],
      dismissible: true,
    }),
  },

  // 规则5：低能量时段 → 轻量任务建议
  {
    id: 'low-energy-light-task',
    event: 'low_energy',
    generateCard: () => ({
      title: '☀️ 下午低谷期',
      message: '下午2-3点是注意力自然低谷期。建议切换到轻量任务，或者站起来走走。',
      icon: '☀️',
      actions: [
        { type: 'take_break', label: '🚶 走动5分钟', primary: true },
        { type: 'navigate', label: '📋 切换到轻量任务' },
      ],
      dismissible: true,
      expiresAt: Date.now() + 30 * 60 * 1000,
    }),
  },

  // 规则6：会议结束 → 记录决策
  {
    id: 'meeting-ended-notes',
    event: 'meeting_ended',
    generateCard: () => ({
      title: '📝 会议结束',
      message: '花2分钟记录一下关键决策和待办事项？',
      icon: '📝',
      actions: [
        { type: 'navigate', label: '✍️ 记录笔记', primary: true },
        { type: 'create_todo', label: '➕ 创建待办' },
      ],
      dismissible: true,
      expiresAt: Date.now() + 10 * 60 * 1000,
    }),
  },
]

export function RelayEngineProvider({ children }: { children: ReactNode }) {
  const [cards, setCards] = useState<RelayCard[]>([])
  const [rules, setRules] = useState<RelayRule[]>(BUILTIN_RULES)

  // 清理过期卡片
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now()
      setCards(prev => prev.filter(c => !c.expiresAt || c.expiresAt > now))
    }, 30000)
    return () => clearInterval(interval)
  }, [])

  const triggerEvent = useCallback((event: RelayEventType, data: Record<string, unknown> = {}) => {
    const matchingRules = rules.filter(r => {
      if (r.event !== event) return false
      if (r.condition && !r.condition(data)) return false
      return true
    })

    const newCards: RelayCard[] = matchingRules.map(rule => {
      const cardData = rule.generateCard(data)
      return {
        ...cardData,
        id: `${rule.id}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        event,
        createdAt: Date.now(),
      }
    })

    if (newCards.length > 0) {
      setCards(prev => [...prev, ...newCards])
    }
  }, [rules])

  const dismissCard = useCallback((id: string) => {
    setCards(prev => prev.filter(c => c.id !== id))
  }, [])

  const executeAction = useCallback((cardId: string, actionIndex: number) => {
    const card = cards.find(c => c.id === cardId)
    if (!card) return
    const action = card.actions[actionIndex]
    if (!action) return

    // 执行行动（这里可以接入实际的API调用）
    console.log('[RelayEngine] Executing action:', action.type, action.data)

    // 执行后关闭卡片
    dismissCard(cardId)
  }, [cards, dismissCard])

  const registerRule = useCallback((rule: RelayRule) => {
    setRules(prev => [...prev, rule])
  }, [])

  return (
    <RelayEngineContext.Provider value={{
      cards,
      triggerEvent,
      dismissCard,
      executeAction,
      registerRule,
    }}>
      {children}
    </RelayEngineContext.Provider>
  )
}
