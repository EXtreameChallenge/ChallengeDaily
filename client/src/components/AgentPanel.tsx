/**
 * AgentPanel — Agent 系统状态面板（独立组件，不修改现有聊天界面）
 *
 * 功能模块：
 *  1. 当前 Agent 状态（引擎类型 / 当前角色 / 推理强度）
 *  2. 工具调用进度（监听 SSE tool_call / tool_result 事件）
 *  3. 多 Agent 协作状态（Planner → Executor → Reviewer）
 *  4. 工作流进度条（GET /api/agent/tasks）
 *  5. 技能库浏览（GET /api/agent/skills，搜索 / 启用禁用）
 *  6. 审计日志（GET /api/agent/audit）
 *  7. 指标概览（GET /api/agent/metrics）
 *
 * 风格：极简，基础功能实现。
 */
import { useState, useEffect, useRef, useCallback, type ReactNode } from 'react'
import {
  Bot, Loader2, Check, X, Wrench, Network, GitBranch,
  BookOpen, ShieldCheck, BarChart3, RefreshCw, Search, ChevronDown,
} from 'lucide-react'
import { request, getBaseUrl, getApiToken, ensureBaseUrl } from '../api/client'

// ════════════════════════════════════════════════════════════
//  类型定义
// ════════════════════════════════════════════════════════════

/** 当前 Agent 状态 */
interface AgentStatus {
  engine: 'agno' | 'classic'
  role: 'single' | 'planner' | 'executor' | 'reviewer'
  reasoning_level: 'low' | 'medium' | 'high'
  team_active: boolean
}

/** 实时工具调用（SSE 驱动） */
interface LiveToolCall {
  id: string
  name: string
  status: 'running' | 'success' | 'error'
  params?: string
  result?: string
  startedAt: number
  finishedAt?: number
}

/** 多 Agent 节点状态 */
interface TeamNode {
  key: 'planner' | 'executor' | 'reviewer'
  label: string
  status: 'pending' | 'running' | 'done' | 'error'
  output?: string
}

/** 工作流任务状态 */
interface WorkflowTask {
  active: boolean
  name?: string
  current_node?: string
  node_index?: number
  total_nodes?: number
  started_at?: number
}

/** 技能卡片 */
interface Skill {
  id: string
  name: string
  description: string
  risk_level?: 'readonly' | 'operation' | 'dangerous'
  enabled: boolean
  use_count?: number
}

/** 审计记录 */
interface AuditRecord {
  id: number
  tool_name: string
  risk_level: 'readonly' | 'operation' | 'dangerous'
  confirmed: boolean
  duration_ms: number
  created_at: string
}

/** 指标概览 */
interface AgentMetrics {
  total_calls?: number
  avg_response_ms?: number
  token_usage?: number
  success_rate?: number
}

/** 审计风险级别归一化：后端存 READ_ONLY/DANGEROUS，前端用小写枚举 */
function normalizeRisk(value: unknown): AuditRecord['risk_level'] {
  const risk = String(value || '').toLowerCase().replace('read_only', 'readonly')
  if (risk === 'dangerous') return 'dangerous'
  if (risk === 'operation' || risk === 'write' || risk === 'confirm') return 'operation'
  return 'readonly'
}

// ════════════════════════════════════════════════════════════
//  常量
// ════════════════════════════════════════════════════════════

const ROLE_LABEL: Record<AgentStatus['role'], string> = {
  single: '单 Agent',
  planner: 'Planner',
  executor: 'Executor',
  reviewer: 'Reviewer',
}

const REASONING_LABEL: Record<AgentStatus['reasoning_level'], string> = {
  low: '低',
  medium: '中',
  high: '高',
}

const RISK_LABEL: Record<Skill['risk_level'], { label: string; cls: string }> = {
  readonly: { label: '只读', cls: 'text-cd-green' },
  operation: { label: '操作', cls: 'text-cd-orange' },
  dangerous: { label: '危险', cls: 'text-cd-red' },
}

const DEFAULT_TEAM: TeamNode[] = [
  { key: 'planner', label: 'Planner 规划', status: 'pending' },
  { key: 'executor', label: 'Executor 执行', status: 'pending' },
  { key: 'reviewer', label: 'Reviewer 审查', status: 'pending' },
]

// ════════════════════════════════════════════════════════════
//  工具函数
// ════════════════════════════════════════════════════════════

function fmtMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function fmtTime(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// ════════════════════════════════════════════════════════════
//  分区卡片（极简折叠块）
// ════════════════════════════════════════════════════════════
function Section({
  icon: Icon,
  title,
  children,
  defaultOpen = true,
}: {
  icon: typeof Bot
  title: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-cd-border rounded-2xl bg-cd-bg-secondary/40 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-cd-hover transition-colors"
      >
        <Icon size={13} className="text-cd-green shrink-0" />
        <span className="text-[12px] font-medium text-cd-text">{title}</span>
        <ChevronDown
          size={13}
          className={`ml-auto text-cd-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && <div className="px-3 pb-3 pt-1">{children}</div>}
    </div>
  )
}

// ════════════════════════════════════════════════════════════
//  主组件
// ════════════════════════════════════════════════════════════
export interface AgentPanelProps {
  /** 外层附加类名 */
  className?: string
  /** 组件是否可见（父级可控制） */
  visible?: boolean
}

export default function AgentPanel({ className = '', visible = true }: AgentPanelProps) {
  // ── 数据状态 ──
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [tools, setTools] = useState<LiveToolCall[]>([])
  const [team, setTeam] = useState<TeamNode[]>(DEFAULT_TEAM)
  const [workflow, setWorkflow] = useState<WorkflowTask | null>(null)
  const [skills, setSkills] = useState<Skill[]>([])
  const [audit, setAudit] = useState<AuditRecord[]>([])
  const [metrics, setMetrics] = useState<AgentMetrics | null>(null)
  const [skillSearch, setSkillSearch] = useState('')
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const esRef = useRef<EventSource | null>(null)

  // ── 拉取各 REST 接口 ──
  const refresh = useCallback(async () => {
    setRefreshing(true)
    try {
      const [st, wf, sk, au, mt] = await Promise.all([
        request('/api/agent/status').catch(() => null),
        request('/api/agent/tasks').catch(() => null),
        request('/api/agent/skills').catch(() => null),
        request('/api/agent/audit').catch(() => null),
        request('/api/agent/metrics').catch(() => null),
      ])
      if (st) setStatus(st as AgentStatus)
      if (wf) {
        const tasks = ((wf as { tasks?: Array<Record<string, unknown>> }).tasks || [])
        const active = tasks.find(t => t.status === 'running') || tasks[0]
        if (active) {
          let state: Record<string, unknown> = {}
          try {
            state = typeof active.state === 'string'
              ? JSON.parse(active.state) as Record<string, unknown>
              : (active.state as Record<string, unknown>) || {}
          } catch { /* 脏状态不阻塞面板 */ }
          setWorkflow({
            active: active.status === 'running',
            name: String(active.workflow_name || ''),
            current_node: String(active.current_node || ''),
            node_index: Number(state.node_index || 0),
            total_nodes: Number(state.total_nodes || 0),
            started_at: active.created_at ? Date.parse(String(active.created_at)) / 1000 : undefined,
          })
        } else {
          setWorkflow({ active: false })
        }
      }
      if (sk) {
        const raw = ((sk as { skills?: Array<Record<string, unknown>> }).skills || [])
        setSkills(raw.map(s => ({
          id: String(s.id ?? ''),
          name: String(s.name || ''),
          description: String(s.description || ''),
          risk_level: s.risk_level ? normalizeRisk(s.risk_level) : undefined,
          enabled: s.status === 'approved',
          use_count: typeof s.use_count === 'number' ? s.use_count : undefined,
        })))
      }
      if (au) {
        const raw = ((au as { logs?: Array<Record<string, unknown>> }).logs
          || (au as { records?: Array<Record<string, unknown>> }).records || [])
        setAudit(raw.map(r => ({
          id: Number(r.id || 0),
          tool_name: String(r.tool_name || ''),
          risk_level: normalizeRisk(r.risk_level),
          confirmed: Boolean(r.confirmed),
          duration_ms: Number(r.cost_ms ?? r.duration_ms ?? 0),
          created_at: String(r.created_at || ''),
        })))
      }
      if (mt) {
        const m = ((mt as { metrics?: Record<string, unknown> }).metrics || mt) as Record<string, unknown>
        setMetrics({
          total_calls: Number(m.total_tool_calls ?? m.total_calls ?? 0),
          avg_response_ms: Number(m.avg_cost_ms ?? m.avg_response_ms ?? 0),
          token_usage: typeof m.token_usage === 'number' ? m.token_usage : undefined,
          success_rate: typeof m.success_rate === 'number' ? m.success_rate : undefined,
        })
      }
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // ── 定时轮询（10s），非实时指标 ──
  useEffect(() => {
    if (!visible) return
    const timer = setInterval(refresh, 10000)
    return () => clearInterval(timer)
  }, [visible, refresh])

  // ── SSE 实时事件流（连接全局事件总线，过滤 agent 相关事件） ──
  useEffect(() => {
    if (!visible) return
    let cancelled = false
    let retry = 0

    const connect = async () => {
      await ensureBaseUrl()
      const token = await getApiToken()
      if (cancelled || !token) {
        if (!token && !cancelled) setTimeout(connect, 1500)
        return
      }
      const url = `${getBaseUrl()}/api/events/stream?token=${encodeURIComponent(token)}`
      const es = new EventSource(url)
      esRef.current = es

      es.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data)
          handleAgentEvent(evt)
        } catch { /* 心跳/非 JSON 忽略 */ }
      }
      es.onerror = () => {
        es.close()
        esRef.current = null
        if (cancelled) return
        retry += 1
        setTimeout(connect, Math.min(30000, 1000 * 2 ** retry))
      }
    }

    connect()
    return () => {
      cancelled = true
      esRef.current?.close()
      esRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible])

  // ── SSE 事件分发 ──
  const handleAgentEvent = (evt: { type?: string; data?: Record<string, unknown> }) => {
    const d = evt.data || {}
    switch (evt.type) {
      case 'tool_call': {
        const tc: LiveToolCall = {
          id: String(d.id ?? d.tool_id ?? Date.now()),
          name: String(d.name ?? d.tool_name ?? 'unknown'),
          status: 'running',
          params: d.params ? JSON.stringify(d.params) : undefined,
          startedAt: Date.now(),
        }
        setTools(prev => [tc, ...prev.filter(t => t.id !== tc.id)].slice(0, 30))
        break
      }
      case 'tool_result': {
        const id = String(d.id ?? d.tool_id ?? '')
        setTools(prev => prev.map(t =>
          t.id === id
            ? { ...t, status: (d.error ? 'error' : 'success') as LiveToolCall['status'], result: String(d.result ?? ''), finishedAt: Date.now() }
            : t
        ))
        break
      }
      case 'agent_role': {
        setStatus(prev => prev ? { ...prev, role: d.role as AgentStatus['role'] } : null)
        break
      }
      case 'team_update': {
        const nodes = (d.nodes as TeamNode[]) || []
        if (nodes.length) setTeam(nodes)
        break
      }
      case 'workflow_update': {
        setWorkflow((): WorkflowTask => ({
          active: true,
          name: String(d.name ?? ''),
          current_node: String(d.current_node ?? ''),
          node_index: Number(d.node_index ?? 0),
          total_nodes: Number(d.total_nodes ?? 1),
          started_at: Date.now(),
        }))
        break
      }
    }
  }

  // ── 技能启用/禁用 ──
  const toggleSkill = async (skill: Skill) => {
    try {
      await request(`/api/agent/skills/${skill.id}/toggle`, { method: 'POST' })
      setSkills(prev => prev.map(s => s.id === skill.id ? { ...s, enabled: !s.enabled } : s))
    } catch { /* 接口未就绪时静默 */ }
  }

  // ── 技能搜索过滤 ──
  const filteredSkills = skills.filter(s =>
    !skillSearch.trim() ||
    s.name.toLowerCase().includes(skillSearch.toLowerCase()) ||
    s.description.toLowerCase().includes(skillSearch.toLowerCase())
  )

  if (!visible) return null

  const teamRunning = team.some(n => n.status === 'running')
  const elapsedWorkflow = workflow?.started_at
    ? Date.now() - workflow.started_at
    : 0

  return (
    <div className={`space-y-2 ${className}`}>
      {/* ═══════ 1. 当前 Agent 状态 ═══════ */}
      <Section icon={Bot} title="Agent 状态">
        <div className="grid grid-cols-3 gap-1.5 text-[11px]">
          <div className="bg-cd-bg rounded-lg px-2 py-1.5">
            <div className="text-cd-text-tertiary">引擎</div>
            <div className="font-medium text-cd-text mt-0.5">
              {status?.engine === 'agno' ? 'Agno' : status?.engine === 'classic' ? 'Classic' : '—'}
            </div>
          </div>
          <div className="bg-cd-bg rounded-lg px-2 py-1.5">
            <div className="text-cd-text-tertiary">角色</div>
            <div className="font-medium text-cd-text mt-0.5">
              {status ? ROLE_LABEL[status.role] : '—'}
            </div>
          </div>
          <div className="bg-cd-bg rounded-lg px-2 py-1.5">
            <div className="text-cd-text-tertiary">推理强度</div>
            <div className="font-medium text-cd-text mt-0.5">
              {status ? REASONING_LABEL[status.reasoning_level] : '—'}
            </div>
          </div>
        </div>
        {status?.team_active && (
          <div className="mt-1.5 text-[10px] text-cd-purple">多 Agent Team 运行中</div>
        )}
      </Section>

      {/* ═══════ 2. 工具调用进度 ═══════ */}
      <Section icon={Wrench} title="工具调用">
        {tools.length === 0 ? (
          <div className="text-[11px] text-cd-text-tertiary py-1">暂无工具调用</div>
        ) : (
          <div className="space-y-1">
            {tools.map(t => {
              const elapsed = t.finishedAt ? t.finishedAt - t.startedAt : Date.now() - t.startedAt
              return (
                <div key={t.id} className="text-[11px]">
                  <div className="flex items-center gap-1.5">
                    {t.status === 'running' && <Loader2 size={11} className="animate-spin text-cd-accent shrink-0" />}
                    {t.status === 'success' && <Check size={11} className="text-cd-green shrink-0" />}
                    {t.status === 'error' && <X size={11} className="text-cd-red shrink-0" />}
                    <span className="text-cd-text font-mono truncate">{t.name}</span>
                    <span className="ml-auto text-cd-text-tertiary shrink-0">{fmtMs(elapsed)}</span>
                  </div>
                  {t.params && (
                    <div className="text-[10px] text-cd-text-tertiary truncate mt-0.5 font-mono">
                      参数: {t.params.slice(0, 80)}
                    </div>
                  )}
                  {t.result != null && (
                    <div className="text-[10px] text-cd-text-tertiary truncate mt-0.5">
                      结果: {t.result.slice(0, 80)}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Section>

      {/* ═══════ 3. 多 Agent 协作状态 ═══════ */}
      <Section icon={Network} title="协作流程" defaultOpen={teamRunning}>
        <div className="flex items-center gap-1">
          {team.map((node, i) => (
            <div key={node.key} className="flex items-center gap-1 flex-1">
              <div
                className={`flex-1 rounded-lg px-2 py-1.5 text-[10px] border transition-colors ${
                  node.status === 'running'
                    ? 'bg-cd-green-light border-cd-green/40 text-cd-green'
                    : node.status === 'done'
                      ? 'bg-cd-bg border-cd-border text-cd-text-secondary'
                      : node.status === 'error'
                        ? 'bg-cd-red-light border-cd-red/40 text-cd-red'
                        : 'bg-cd-bg-secondary border-cd-border text-cd-text-tertiary'
                }`}
              >
                <div className="font-medium truncate">{node.label}</div>
                <div className="truncate mt-0.5">
                  {node.status === 'running' ? '运行中…'
                    : node.status === 'done' ? '完成'
                      : node.status === 'error' ? '失败' : '等待'}
                </div>
              </div>
              {i < team.length - 1 && <span className="text-cd-text-tertiary text-[10px] shrink-0">→</span>}
            </div>
          ))}
        </div>
      </Section>

      {/* ═══════ 4. 工作流进度 ═══════ */}
      <Section icon={GitBranch} title="工作流">
        {!workflow?.active ? (
          <div className="text-[11px] text-cd-text-tertiary py-1">当前无运行中的工作流</div>
        ) : (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-cd-text font-medium truncate">{workflow.name || '未命名工作流'}</span>
              <span className="text-cd-text-tertiary shrink-0">{fmtMs(elapsedWorkflow)}</span>
            </div>
            <div className="h-1.5 bg-cd-bg rounded-full overflow-hidden">
              <div
                className="h-full bg-cd-green rounded-full transition-all"
                style={{
                  width: `${Math.min(100, ((workflow.node_index || 0) / Math.max(1, workflow.total_nodes || 1)) * 100)}%`,
                }}
              />
            </div>
            <div className="text-[10px] text-cd-text-tertiary flex justify-between">
              <span>当前节点: {workflow.current_node || '—'}</span>
              <span>{workflow.node_index || 0}/{workflow.total_nodes || 1}</span>
            </div>
          </div>
        )}
      </Section>

      {/* ═══════ 5. 技能库 ═══════ */}
      <Section icon={BookOpen} title={`技能库 (${skills.length})`}>
        <div className="flex items-center gap-1.5 mb-1.5">
          <div className="flex-1 flex items-center gap-1 bg-cd-bg rounded-lg px-2 py-1">
            <Search size={11} className="text-cd-text-tertiary shrink-0" />
            <input
              value={skillSearch}
              onChange={e => setSkillSearch(e.target.value)}
              placeholder="搜索技能"
              className="flex-1 bg-transparent text-[11px] text-cd-text focus:outline-none"
            />
          </div>
          <button
            onClick={refresh}
            className="p-1.5 text-cd-text-tertiary hover:text-cd-text transition-colors"
            title="刷新"
          >
            <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
          </button>
        </div>
        {filteredSkills.length === 0 ? (
          <div className="text-[11px] text-cd-text-tertiary py-1">
            {skills.length === 0 ? '暂无已审核技能' : '无匹配技能'}
          </div>
        ) : (
          <div className="space-y-1">
            {filteredSkills.map(s => {
              const risk = s.risk_level ? RISK_LABEL[s.risk_level] : null
              const expanded = expandedSkill === s.id
              return (
                <div key={s.id} className="bg-cd-bg rounded-lg px-2 py-1.5">
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => setExpandedSkill(expanded ? null : s.id)}
                      className="flex-1 text-left min-w-0"
                    >
                      <div className="flex items-center gap-1">
                        <span className="text-[11px] text-cd-text font-medium truncate">{s.name}</span>
                        {risk && <span className={`text-[9px] shrink-0 ${risk.cls}`}>{risk.label}</span>}
                      </div>
                      {expanded && (
                        <div className="text-[10px] text-cd-text-tertiary mt-0.5 leading-snug">
                          {s.description}
                        </div>
                      )}
                    </button>
                    {typeof s.use_count === 'number' && s.use_count > 0 && (
                      <span className="text-[9px] text-cd-text-tertiary shrink-0">×{s.use_count}</span>
                    )}
                    <button
                      onClick={() => toggleSkill(s)}
                      className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
                        s.enabled
                          ? 'bg-cd-green-light text-cd-green'
                          : 'bg-cd-bg-secondary text-cd-text-tertiary'
                      }`}
                    >
                      {s.enabled ? '已启用' : '已禁用'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Section>

      {/* ═══════ 6. 审计日志 ═══════ */}
      <Section icon={ShieldCheck} title="审计日志" defaultOpen={false}>
        {audit.length === 0 ? (
          <div className="text-[11px] text-cd-text-tertiary py-1">暂无审计记录</div>
        ) : (
          <div className="space-y-1">
            {audit.slice(0, 10).map(r => {
              const risk = RISK_LABEL[r.risk_level]
              return (
                <div key={r.id} className="flex items-center gap-1.5 text-[10px]">
                  <span className="font-mono text-cd-text truncate flex-1">{r.tool_name}</span>
                  <span className={risk.cls}>{risk.label}</span>
                  <span className="text-cd-text-tertiary">
                    {r.confirmed ? '已确认' : '未确认'}
                  </span>
                  <span className="text-cd-text-tertiary shrink-0">{fmtMs(r.duration_ms)}</span>
                  <span className="text-cd-text-tertiary shrink-0">{fmtTime(r.created_at)}</span>
                </div>
              )
            })}
          </div>
        )}
      </Section>

      {/* ═══════ 7. 指标概览 ═══════ */}
      <Section icon={BarChart3} title="指标概览">
        {!metrics ? (
          <div className="text-[11px] text-cd-text-tertiary py-1">暂无指标</div>
        ) : (
          <div className="grid grid-cols-4 gap-1.5 text-center">
            <div className="bg-cd-bg rounded-lg px-1 py-1.5">
              <div className="text-[13px] font-bold text-cd-text">{metrics.total_calls ?? '—'}</div>
              <div className="text-[9px] text-cd-text-tertiary mt-0.5">总调用</div>
            </div>
            <div className="bg-cd-bg rounded-lg px-1 py-1.5">
              <div className="text-[13px] font-bold text-cd-text">{fmtMs(metrics.avg_response_ms ?? 0)}</div>
              <div className="text-[9px] text-cd-text-tertiary mt-0.5">平均响应</div>
            </div>
            <div className="bg-cd-bg rounded-lg px-1 py-1.5">
              <div className="text-[13px] font-bold text-cd-text">{metrics.token_usage ?? '—'}</div>
              <div className="text-[9px] text-cd-text-tertiary mt-0.5">Token</div>
            </div>
            <div className="bg-cd-bg rounded-lg px-1 py-1.5">
              <div className="text-[13px] font-bold text-cd-green">
                {typeof metrics.success_rate === 'number' ? `${Math.round(metrics.success_rate * 100)}%` : '—'}
              </div>
              <div className="text-[9px] text-cd-text-tertiary mt-0.5">成功率</div>
            </div>
          </div>
        )}
      </Section>
    </div>
  )
}
