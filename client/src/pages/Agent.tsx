import { useState, useEffect } from 'react'
import {
  Bot,
  Zap,
  Globe,
  Send,
  Plus,
  Trash2,
  Power,
  PowerOff,
  Loader2,
  CheckCircle,
  XCircle,
  Link2 as LinkIcon,
  Clock,
  FileText,
  Timer,
} from 'lucide-react'
import {
  getWebhooks,
  addWebhook,
  deleteWebhook,
  testWebhook,
  toggleWebhook,
  triggerAutoReport,
  getAutoReportConfig,
  updateAutoReportConfig,
  type Webhook,
  type AutoReportConfig,
} from '../api/client'
import { ToggleSwitch, useAsyncData, ApiErrorDisplay } from '../components/shared'

type AgentData = { webhooks: Webhook[]; autoConfig: AutoReportConfig }

export default function AgentPage() {
  // 添加表单
  const [showAdd, setShowAdd] = useState(false)
  const [newUrl, setNewUrl] = useState('')
  const [newName, setNewName] = useState('')
  const [newType, setNewType] = useState<'feishu' | 'dingtalk' | 'wecom' | 'custom'>('feishu')
  // 测试/操作状态
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; message: string }>>({})
  const [adding, setAdding] = useState(false)
  // 自动推送
  const [pushing, setPushing] = useState(false)
  const [pushResult, setPushResult] = useState<{ ok: boolean; message: string } | null>(null)
  // 自动日报配置（本地缓存，用于受控表单）
  const [autoConfig, setAutoConfig] = useState<{ enabled: boolean; auto_time: string; auto_push: boolean }>({ enabled: false, auto_time: '18:00', auto_push: true })
  const [autoSaving, setAutoSaving] = useState(false)

  const { data, loading, error, refresh } = useAsyncData<AgentData>(
    async () => {
      const [whData, arConfig] = await Promise.all([getWebhooks(), getAutoReportConfig()])
      return { webhooks: whData, autoConfig: arConfig }
    },
    [],
  )

  const webhooks = data?.webhooks || []

  // 同步远程配置到本地表单
  useEffect(() => {
    if (data?.autoConfig) setAutoConfig(data.autoConfig)
  }, [data?.autoConfig])

  const handleAdd = async () => {
    if (!newUrl.trim()) return
    setAdding(true)
    try {
      await addWebhook({
        url: newUrl.trim(),
        name: newName.trim() || undefined,
        type: newType,
        events: ['daily_report'],
      })
      setShowAdd(false)
      setNewUrl('')
      setNewName('')
      refresh()
    } catch (err) {
      console.error('Failed to add webhook:', err)
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteWebhook(id)
      refresh()
    } catch (err) {
      console.error('Failed to delete webhook:', err)
    }
  }

  const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const result = await testWebhook(id)
      setTestResult(prev => ({ ...prev, [id]: result }))
    } catch (err: any) {
      setTestResult(prev => ({ ...prev, [id]: { ok: false, message: err.message || '测试失败' } }))
    } finally {
      setTestingId(null)
    }
  }

  const handleToggle = async (id: string) => {
    try {
      await toggleWebhook(id)
      refresh()
    } catch (err) {
      console.error('Failed to toggle webhook:', err)
    }
  }

  const handleAutoPush = async () => {
    setPushing(true)
    setPushResult(null)
    try {
      const result = await triggerAutoReport()
      setPushResult({ ok: true, message: `日报已生成，推送至 ${result.webhooks_pushed} 个 Webhook` })
    } catch (err: any) {
      setPushResult({ ok: false, message: err.message || '操作失败' })
    } finally {
      setPushing(false)
    }
  }

  const saveAutoConfig = async (updates: Partial<typeof autoConfig>) => {
    const newConfig = { ...autoConfig, ...updates }
    setAutoConfig(newConfig)
    setAutoSaving(true)
    try {
      const result = await updateAutoReportConfig(updates)
      if (result.config) setAutoConfig(result.config)
    } catch (err) {
      console.error('Failed to save auto report config:', err)
    } finally {
      setAutoSaving(false)
    }
  }

  const WH_TYPE_INFO: Record<string, { label: string; color: string; desc: string }> = {
    feishu: { label: '飞书', color: '#3370FF', desc: '飞书群机器人 Webhook' },
    dingtalk: { label: '钉钉', color: '#0089FF', desc: '钉钉群自定义机器人' },
    wecom: { label: '企业微信', color: '#07C160', desc: '企业微信群机器人' },
    custom: { label: '自定义', color: 'var(--cd-text-tertiary)', desc: '自定义 HTTP Webhook' },
  }

  return (
    <div className="animate-fade-in space-y-5 max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-cd-text">接入Agent</h1>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:bg-cd-green-dark transition-colors"
        >
          <Plus size={14} />
          添加推送
        </button>
      </div>

      {/* ─── 错误提示 ──────────────────────── */}
      {error && <ApiErrorDisplay error={error} onRetry={refresh} />}

      {/* ─── 自动推送 ──────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">一键推送日报</h2>
        </div>
        <p className="text-xs text-cd-text-tertiary">
          立即生成今日日报并推送到所有已启用的 Webhook
        </p>
        <button
          onClick={handleAutoPush}
          disabled={pushing}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-cd-green text-white hover:bg-cd-green-dark disabled:opacity-50 transition-colors"
        >
          {pushing ? (
            <><Loader2 size={14} className="animate-spin" /> 正在生成并推送...</>
          ) : (
            <><Send size={14} /> 生成日报并推送</>
          )}
        </button>
        {pushResult && (
          <div className={`flex items-center gap-1.5 text-xs ${pushResult.ok ? 'text-cd-green' : 'text-cd-red'}`}>
            {pushResult.ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
            {pushResult.message}
          </div>
        )}
      </section>

      {/* ─── 定时自动日报 ──────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Timer size={16} className="text-cd-green" />
            <h2 className="text-sm font-semibold text-cd-text">定时自动日报</h2>
          </div>
          <ToggleSwitch
            checked={autoConfig.enabled}
            onChange={(checked) => saveAutoConfig({ enabled: checked })}
            disabled={autoSaving}
          />
        </div>
        <p className="text-xs text-cd-text-tertiary">
          到达设定时间后，自动生成当日日报并推送到启用的 Webhook
        </p>
        {autoConfig.enabled && (
          <div className="space-y-3 animate-fade-in">
            <div className="flex items-center gap-3">
              <label className="text-xs text-cd-text-secondary w-20 shrink-0">触发时间</label>
              <input
                type="time"
                value={autoConfig.auto_time}
                onChange={(e) => saveAutoConfig({ auto_time: e.target.value })}
                className="bg-cd-card border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
              />
            </div>
            <div className="flex items-center gap-3">
              <label className="text-xs text-cd-text-secondary w-20 shrink-0">自动推送</label>
              <ToggleSwitch
                checked={autoConfig.auto_push}
                onChange={(checked) => saveAutoConfig({ auto_push: checked })}
              />
              <span className="text-xs text-cd-text-tertiary">
                {autoConfig.auto_push ? '生成后自动推送' : '仅生成不推送'}
              </span>
            </div>
          </div>
        )}
      </section>

      {/* ─── 添加 Webhook ──────────────────── */}
      {showAdd && (
        <section className="card space-y-3 animate-fade-in border-cd-green/20">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-cd-text">添加 Webhook 推送</h2>
            <button onClick={() => setShowAdd(false)} className="text-cd-text-tertiary hover:text-cd-text">
              ✕
            </button>
          </div>

          <div className="flex gap-2">
            {Object.entries(WH_TYPE_INFO).map(([key, info]) => (
              <button
                key={key}
                onClick={() => setNewType(key as any)}
                className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-all ${
                  newType === key
                    ? 'border-cd-green bg-cd-green-light text-cd-green'
                    : 'border-cd-border bg-cd-bg-secondary text-cd-text-secondary hover:border-cd-green/30'
                }`}
              >
                {info.label}
              </button>
            ))}
          </div>

          <div className="text-xs text-cd-text-tertiary">{WH_TYPE_INFO[newType].desc}</div>

          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">名称（可选）</label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder={`${WH_TYPE_INFO[newType].label}群机器人`}
              className="w-full bg-cd-bg-secondary border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
            />
          </div>

          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">Webhook URL</label>
            <input
              type="text"
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
              className="w-full bg-cd-bg-secondary border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green font-mono"
            />
          </div>

          <button
            onClick={handleAdd}
            disabled={adding || !newUrl.trim()}
            className="w-full py-2 rounded-lg text-sm font-medium bg-cd-green text-white hover:bg-cd-green-dark disabled:opacity-50 transition-colors"
          >
            {adding ? '添加中...' : '添加'}
          </button>
        </section>
      )}

      {/* ─── Webhook 列表 ─────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Globe size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">已配置的推送</h2>
          <span className="text-[10px] text-cd-text-tertiary bg-cd-bg-secondary px-2 py-0.5 rounded-full">
            {webhooks.filter(w => w.enabled).length}/{webhooks.length} 启用
          </span>
        </div>

        {loading ? (
          <div className="text-xs text-cd-text-tertiary animate-pulse">加载中...</div>
        ) : webhooks.length === 0 ? (
          <div className="text-center py-8">
            <LinkIcon size={24} className="text-cd-text-tertiary mx-auto mb-2" />
            <p className="text-xs text-cd-text-tertiary">还没有配置 Webhook</p>
            <p className="text-[10px] text-cd-text-tertiary mt-1">
              添加飞书/钉钉/企业微信群机器人，日报生成后自动推送
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {webhooks.map((wh) => {
              const info = WH_TYPE_INFO[wh.type] || WH_TYPE_INFO.custom
              return (
                <div
                  key={wh.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
                    wh.enabled ? 'bg-cd-bg-secondary border-cd-border' : 'bg-cd-bg-secondary/50 border-cd-border opacity-60'
                  }`}
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold shrink-0"
                    style={{ background: info.color }}
                  >
                    {info.label[0]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-cd-text truncate">{wh.name}</div>
                    <div className="text-[10px] text-cd-text-tertiary truncate font-mono">{wh.url}</div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button
                      onClick={() => handleTest(wh.id)}
                      disabled={testingId === wh.id}
                      className="p-1 rounded text-cd-text-tertiary hover:text-cd-text hover:bg-cd-hover transition-colors disabled:opacity-50"
                      title="测试连接"
                    >
                      {testingId === wh.id ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Send size={14} />
                      )}
                    </button>
                    <button
                      onClick={() => handleToggle(wh.id)}
                      className="p-1 rounded text-cd-text-tertiary hover:text-cd-text hover:bg-cd-hover transition-colors"
                      title={wh.enabled ? '禁用' : '启用'}
                    >
                      {wh.enabled ? <Power size={14} className="text-cd-green" /> : <PowerOff size={14} />}
                    </button>
                    <button
                      onClick={() => handleDelete(wh.id)}
                      className="p-1 rounded text-cd-text-tertiary hover:text-cd-red hover:bg-cd-red-light transition-colors"
                      title="删除"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {testResult && Object.entries(testResult).map(([id, result]) => (
          <div key={id} className={`flex items-center gap-1.5 text-xs ${result.ok ? 'text-cd-green' : 'text-cd-red'}`}>
            {result.ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
            {result.message}
          </div>
        ))}
      </section>

      {/* ─── Agent 功能说明 ─────────────────── */}
      <section className="card space-y-3">
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">Agent 能力</h2>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[
            { icon: Clock, title: '定时生成', desc: '每天工作结束自动生成日报', available: true },
            { icon: Send, title: '自动推送', desc: '生成后自动推送到 IM 群', available: true },
            { icon: FileText, title: '周报汇总', desc: '每周自动汇总周报并推送', available: false },
            { icon: Bot, title: 'AI Agent', desc: '根据上下文智能补充日报', available: false },
          ].map(({ icon: Icon, title, desc, available }) => (
            <div
              key={title}
              className={`flex items-start gap-2.5 p-3 rounded-lg ${
                available ? 'bg-cd-bg-secondary' : 'bg-cd-bg-secondary/50 opacity-50'
              }`}
            >
              <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                available ? 'bg-cd-green-light text-cd-green' : 'bg-cd-bg text-cd-text-tertiary'
              }`}>
                <Icon size={14} />
              </div>
              <div>
                <div className="text-xs font-medium text-cd-text">{title}</div>
                <div className="text-[10px] text-cd-text-tertiary">{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
