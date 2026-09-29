/**
 * 协议兼容层面板（ActivityWatch + WakaTime）
 * ==========================================
 * - ActivityWatch aw-server REST API 兼容说明 + 状态指示 + 测试连接
 * - WakaTime heartbeat 兼容说明 + API Key 管理 + 测试心跳
 * - 数据统计：通过兼容层接收的数据量
 *
 * 后端端点：
 *  - GET  /api/aw/meta       — AW 兼容层元信息（bucket 列表、统计）
 *  - POST /api/aw/test       — 测试 AW 兼容层
 *  - GET  /api/wakatime/status — WakaTime 兼容层状态（API key 掩码、统计）
 *  - GET  /api/wakatime/key    — 获取完整 API key
 *  - POST /api/wakatime/key    — 重新生成 API key
 *  - POST /api/wakatime/test   — 发送测试心跳
 */
import { useState, useEffect, useCallback } from 'react'
import { request } from '../api/client'
import { useToast } from './Toast'
import {
  Activity, Key, Copy, RefreshCw, Send, Eye, EyeOff,
  CheckCircle, Loader2, Server, Database, Terminal,
  ExternalLink, ChevronDown, ChevronRight,
} from 'lucide-react'

// ── 类型定义 ────────────────────────────────────────────────────────
interface AwBucket {
  id: string
  type: string  // window | afk | web | editor
  client: string
  hostname: string
  created: string
  data?: Record<string, unknown>
  event_count?: number
}

interface AwMeta {
  server_url: string
  server_id: string
  server_version: string
  buckets: AwBucket[]
  stats: Record<string, number>
  auth_required: boolean
}

interface WakaTimeStatus {
  enabled: boolean
  api_key_masked: string
  api_key_length: number
  endpoints: {
    single: string
    bulk: string
  }
  auth_methods: string[]
  config_instructions: {
    vscode: { title: string; steps: string[] }
    cli: { title: string; steps: string[] }
  }
  stats: Record<string, number>
  version: string
}

// ── 组件 ────────────────────────────────────────────────────────────
export default function ProtocolCompatPanel() {
  const toast = useToast()
  const [awMeta, setAwMeta] = useState<AwMeta | null>(null)
  const [wtStatus, setWtStatus] = useState<WakaTimeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [testingAw, setTestingAw] = useState(false)
  const [testingWt, setTestingWt] = useState(false)
  const [showFullKey, setShowFullKey] = useState(false)
  const [fullApiKey, setFullApiKey] = useState('')
  const [regeneratingKey, setRegeneratingKey] = useState(false)
  const [showVscodeConfig, setShowVscodeConfig] = useState(false)
  const [showCliConfig, setShowCliConfig] = useState(false)
  const [copyState, setCopyState] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [meta, status] = await Promise.all([
        request('/api/aw/meta') as Promise<AwMeta>,
        request('/api/wakatime/status') as Promise<WakaTimeStatus>,
      ])
      setAwMeta(meta)
      setWtStatus(status)
    } catch (err: unknown) {
      // 静默处理，避免在设置页弹出错误
      const msg = err instanceof Error ? err.message : String(err)
      console.warn('协议兼容层数据加载失败:', msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // ── 测试 ActivityWatch 连接 ────────────────────────────────────────
  const handleTestAw = async () => {
    setTestingAw(true)
    try {
      const r = await request('/api/aw/test', { method: 'POST' }) as {
        status: string
        server: string
        version: string
        hostname: string
        message: string
      }
      if (r.status === 'ok') {
        toast.success(`AW 兼容层连接正常 (${r.server} v${r.version})`)
      } else {
        toast.error('AW 兼容层测试失败')
      }
      refresh()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '测试失败'
      toast.error(msg)
    } finally {
      setTestingAw(false)
    }
  }

  // ── 测试 WakaTime 心跳 ──────────────────────────────────────────────
  const handleTestWt = async () => {
    setTestingWt(true)
    try {
      const r = await request('/api/wakatime/test', { method: 'POST' }) as {
        status: string
        message: string
      }
      if (r.status === 'ok') {
        toast.success('测试心跳已发送，请检查活动记录')
      } else {
        toast.error(r.message || '测试心跳失败')
      }
      refresh()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '测试失败'
      toast.error(msg)
    } finally {
      setTestingWt(false)
    }
  }

  // ── 显示完整 API Key ──────────────────────────────────────────────
  const handleShowFullKey = async () => {
    if (showFullKey) {
      setShowFullKey(false)
      setFullApiKey('')
      return
    }
    try {
      const r = await request('/api/wakatime/key') as { api_key: string }
      setFullApiKey(r.api_key)
      setShowFullKey(true)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取失败'
      toast.error(msg)
    }
  }

  // ── 重置 API Key ───────────────────────────────────────────────────
  const handleRegenerateKey = async () => {
    if (!confirm('确定要重置 API Key 吗？已配置的 WakaTime 客户端将无法继续上报，需要更新配置。')) return
    setRegeneratingKey(true)
    try {
      const r = await request('/api/wakatime/key', { method: 'POST' }) as {
        api_key: string
        message: string
      }
      setFullApiKey(r.api_key)
      setShowFullKey(true)
      toast.success('API Key 已重置，请更新 WakaTime 客户端配置')
      refresh()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '重置失败'
      toast.error(msg)
    } finally {
      setRegeneratingKey(false)
    }
  }

  // ── 复制到剪贴板 ───────────────────────────────────────────────────
  const handleCopy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopyState(label)
      toast.success(`${label} 已复制到剪贴板`)
      setTimeout(() => setCopyState(null), 1500)
    } catch {
      // Electron 环境下 navigator.clipboard 可能不可用，回退到 execCommand
      try {
        const textarea = document.createElement('textarea')
        textarea.value = text
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
        setCopyState(label)
        toast.success(`${label} 已复制到剪贴板`)
        setTimeout(() => setCopyState(null), 1500)
      } catch {
        toast.error('复制失败，请手动复制')
      }
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-xs text-cd-text-tertiary">
        <Loader2 size={14} className="animate-spin mr-2" /> 加载协议兼容层状态...
      </div>
    )
  }

  const awStats = awMeta?.stats || {}
  const wtStats = wtStatus?.stats || {}
  const totalReceived =
    (awStats.aw_events_received || 0) +
    (awStats.aw_heartbeats_received || 0) +
    (awStats.wakatime_heartbeats_received || 0)
  const totalInserted =
    (awStats.aw_events_inserted || 0) +
    (awStats.wakatime_heartbeats_received || 0) - (awStats.wakatime_heartbeats_merged || 0)
  const totalMerged =
    (awStats.aw_heartbeats_merged || 0) +
    (awStats.wakatime_heartbeats_merged || 0)

  return (
    <div className="space-y-4">
      {/* ── 数据统计概览 ──────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-2">
        <div className="p-2 bg-cd-bg-secondary rounded-2xl border border-cd-border">
          <div className="flex items-center gap-1 text-[10px] text-cd-text-tertiary mb-0.5">
            <Database size={10} /> 接收总数
          </div>
          <div className="text-lg font-semibold text-cd-text">{totalReceived}</div>
        </div>
        <div className="p-2 bg-cd-green-light rounded-2xl border border-cd-green/20">
          <div className="flex items-center gap-1 text-[10px] text-cd-green mb-0.5">
            <CheckCircle size={10} /> 写入数
          </div>
          <div className="text-lg font-semibold text-cd-green">{Math.max(0, totalInserted)}</div>
        </div>
        <div className="p-2 bg-cd-bg-secondary rounded-2xl border border-cd-border">
          <div className="flex items-center gap-1 text-[10px] text-cd-text-tertiary mb-0.5">
            <RefreshCw size={10} /> 合并去重
          </div>
          <div className="text-lg font-semibold text-cd-text-secondary">{totalMerged}</div>
        </div>
      </div>

      {/* ── ActivityWatch 兼容层 ──────────────────────────────────── */}
      <div className="p-3 bg-cd-bg-secondary border border-cd-border rounded-2xl space-y-2">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-cd-green" />
          <span className="text-xs font-semibold text-cd-text">ActivityWatch 兼容层</span>
          <span className="ml-auto flex items-center gap-1 text-[10px]">
            <span className={`w-1.5 h-1.5 rounded-full ${awMeta ? 'bg-cd-green' : 'bg-cd-text-tertiary'} animate-pulse`} />
            <span className="text-cd-text-tertiary">{awMeta ? '已启用' : '未启用'}</span>
          </span>
        </div>

        {awMeta && (
          <>
            {/* 服务器信息 */}
            <div className="text-xs space-y-1">
              <div className="flex items-center gap-1.5 text-cd-text-secondary">
                <Server size={11} className="text-cd-text-tertiary" />
                <span>aw-server URL：</span>
                <code className="px-1.5 py-0.5 bg-cd-bg rounded-lg text-cd-green text-[10px] font-mono">
                  {awMeta.server_url}
                </code>
                <button
                  onClick={() => handleCopy(awMeta.server_url, 'aw-server URL')}
                  className="text-cd-text-tertiary hover:text-cd-text"
                  title="复制 URL"
                >
                  {copyState === 'aw-server URL' ? <CheckCircle size={11} className="text-cd-green" /> : <Copy size={11} />}
                </button>
              </div>
              <div className="flex items-center gap-1.5 text-cd-text-tertiary text-[10px]">
                <span>Server: {awMeta.server_id} v{awMeta.server_version}</span>
                {awMeta.auth_required && (
                  <span className="px-1.5 py-0.5 bg-cd-orange-light text-cd-orange rounded-lg text-[9px]">需鉴权</span>
                )}
              </div>
            </div>

            {/* Bucket 列表 */}
            <div className="space-y-1">
              <div className="text-[10px] text-cd-text-tertiary flex items-center gap-1">
                <Database size={10} /> Buckets ({awMeta.buckets.length})
              </div>
              {awMeta.buckets.length === 0 ? (
                <div className="text-[10px] text-cd-text-tertiary italic px-2 py-1">
                  暂无 bucket，当 AW 客户端首次推送事件时会自动创建
                </div>
              ) : (
                <div className="max-h-32 overflow-y-auto space-y-0.5">
                  {awMeta.buckets.map((b) => (
                    <div key={b.id} className="flex items-center gap-2 p-1.5 bg-cd-bg rounded-lg text-[10px]">
                      <span className={`px-1.5 py-0.5 rounded-lg text-[9px] font-mono ${_bucketTypeColor(b.type)}`}>
                        {b.type}
                      </span>
                      <code className="text-cd-text-secondary font-mono truncate flex-1">{b.id}</code>
                      <span className="text-cd-text-tertiary flex-shrink-0">
                        {b.event_count || 0} 事件
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 测试连接按钮 */}
            <button
              onClick={handleTestAw}
              disabled={testingAw}
              className="w-full px-3 py-1.5 bg-cd-green text-white rounded-lg text-xs hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-1.5"
            >
              {testingAw ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
              {testingAw ? '测试中...' : '测试连接'}
            </button>

            {/* AW 客户端配置说明 */}
            <details className="text-[10px] text-cd-text-tertiary">
              <summary className="cursor-pointer hover:text-cd-text-secondary flex items-center gap-1">
                <ChevronRight size={10} /> aw-watcher 配置说明
              </summary>
              <div className="mt-1 p-2 bg-cd-bg rounded-lg text-[10px] space-y-1 text-cd-text-secondary">
                <div>1. 安装 ActivityWatch 客户端：<a href="https://activitywatch.net/downloads/" target="_blank" rel="noopener noreferrer" className="text-cd-green inline-flex items-center gap-0.5">activitywatch.net <ExternalLink size={9} /></a></div>
                <div>2. 修改 aw-server 端口指向 ChallengeDaily（默认 5600 → 58888）</div>
                <div>3. 或在 aw-server 配置中设置 base_url = <code className="text-cd-green">{awMeta.server_url}</code></div>
                <div>4. 重启 ActivityWatch，事件将自动写入 ChallengeDaily</div>
              </div>
            </details>
          </>
        )}
      </div>

      {/* ── WakaTime 兼容层 ──────────────────────────────────────── */}
      <div className="p-3 bg-cd-bg-secondary border border-cd-border rounded-2xl space-y-2">
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-cd-green" />
          <span className="text-xs font-semibold text-cd-text">WakaTime 兼容层</span>
          <span className="ml-auto flex items-center gap-1 text-[10px]">
            <span className={`w-1.5 h-1.5 rounded-full ${wtStatus ? 'bg-cd-green' : 'bg-cd-text-tertiary'} animate-pulse`} />
            <span className="text-cd-text-tertiary">{wtStatus ? '已启用' : '未启用'}</span>
          </span>
        </div>

        {wtStatus && (
          <>
            {/* API Key 管理 */}
            <div className="space-y-1.5">
              <div className="text-[10px] text-cd-text-tertiary flex items-center gap-1">
                <Key size={10} /> API Key
              </div>
              <div className="flex items-center gap-1.5">
                <code className="flex-1 px-2 py-1 bg-cd-bg rounded-lg text-[11px] font-mono text-cd-green truncate">
                  {showFullKey ? fullApiKey : wtStatus.api_key_masked}
                </code>
                <button
                  onClick={handleShowFullKey}
                  className="p-1 text-cd-text-tertiary hover:text-cd-text"
                  title={showFullKey ? '隐藏' : '显示完整 Key'}
                >
                  {showFullKey ? <EyeOff size={12} /> : <Eye size={12} />}
                </button>
                <button
                  onClick={() => handleCopy(showFullKey ? fullApiKey : wtStatus.api_key_masked, 'API Key')}
                  className="p-1 text-cd-text-tertiary hover:text-cd-text"
                  title="复制 Key"
                >
                  {copyState === 'API Key' ? <CheckCircle size={12} className="text-cd-green" /> : <Copy size={12} />}
                </button>
                <button
                  onClick={handleRegenerateKey}
                  disabled={regeneratingKey}
                  className="p-1 text-cd-text-tertiary hover:text-cd-red"
                  title="重置 Key"
                >
                  {regeneratingKey ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                </button>
              </div>
            </div>

            {/* 端点信息 */}
            <div className="text-[10px] space-y-0.5">
              <div className="text-cd-text-tertiary">端点：</div>
              <div className="font-mono text-cd-text-secondary pl-2">
                <div>• {wtStatus.endpoints.single}</div>
                <div>• {wtStatus.endpoints.bulk}</div>
              </div>
            </div>

            {/* 测试心跳按钮 */}
            <button
              onClick={handleTestWt}
              disabled={testingWt}
              className="w-full px-3 py-1.5 bg-cd-green text-white rounded-lg text-xs hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-1.5"
            >
              {testingWt ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
              {testingWt ? '发送中...' : '测试心跳'}
            </button>

            {/* 配置说明 */}
            <div className="space-y-1">
              <div className="text-[10px] text-cd-text-tertiary">配置说明：</div>

              {/* VS Code 配置 */}
              <div className="bg-cd-bg rounded-lg">
                <button
                  onClick={() => setShowVscodeConfig(!showVscodeConfig)}
                  className="w-full flex items-center gap-1 px-2 py-1 text-[10px] text-cd-text-secondary hover:text-cd-text"
                >
                  {showVscodeConfig ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                  {wtStatus.config_instructions.vscode.title}
                </button>
                {showVscodeConfig && (
                  <ol className="p-2 pt-0 space-y-0.5 text-[10px] text-cd-text-tertiary list-decimal list-inside">
                    {wtStatus.config_instructions.vscode.steps.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ol>
                )}
              </div>

              {/* CLI 配置 */}
              <div className="bg-cd-bg rounded-lg">
                <button
                  onClick={() => setShowCliConfig(!showCliConfig)}
                  className="w-full flex items-center gap-1 px-2 py-1 text-[10px] text-cd-text-secondary hover:text-cd-text"
                >
                  {showCliConfig ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                  {wtStatus.config_instructions.cli.title}
                </button>
                {showCliConfig && (
                  <ol className="p-2 pt-0 space-y-0.5 text-[10px] text-cd-text-tertiary list-decimal list-inside">
                    {wtStatus.config_instructions.cli.steps.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ol>
                )}
              </div>
            </div>

            {/* 鉴权方式 */}
            <div className="text-[10px] text-cd-text-tertiary">
              <span>支持鉴权方式：</span>
              <span className="font-mono text-cd-text-secondary">
                {wtStatus.auth_methods.join(' / ')}
              </span>
            </div>
          </>
        )}
      </div>

      {/* ── 详细统计 ──────────────────────────────────────────────── */}
      <details className="text-[10px] text-cd-text-tertiary">
        <summary className="cursor-pointer hover:text-cd-text-secondary flex items-center gap-1">
          <ChevronRight size={10} /> 详细统计
        </summary>
        <div className="mt-1 p-2 bg-cd-bg-secondary rounded-lg grid grid-cols-2 gap-1.5">
          <StatRow label="AW 批量接收" value={awStats.aw_events_received} />
          <StatRow label="AW 写入" value={awStats.aw_events_inserted} />
          <StatRow label="AW heartbeat 接收" value={awStats.aw_heartbeats_received} />
          <StatRow label="AW heartbeat 合并" value={awStats.aw_heartbeats_merged} />
          <StatRow label="WakaTime 接收" value={awStats.wakatime_heartbeats_received} />
          <StatRow label="WakaTime 合并" value={awStats.wakatime_heartbeats_merged} />
        </div>
      </details>
    </div>
  )
}

// ── 子组件 ───────────────────────────────────────────────────────────
function StatRow({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="flex items-center justify-between text-[10px]">
      <span className="text-cd-text-tertiary">{label}</span>
      <span className="font-mono text-cd-text-secondary">{value || 0}</span>
    </div>
  )
}

// ── 工具函数 ─────────────────────────────────────────────────────────
function _bucketTypeColor(type: string): string {
  switch (type) {
    case 'window':
      return 'bg-cd-green-light text-cd-green'
    case 'afk':
      return 'bg-cd-orange-light text-cd-orange'
    case 'web':
      return 'bg-cd-blue-light text-cd-blue'
    case 'editor':
      return 'bg-cd-purple-light text-cd-purple'
    default:
      return 'bg-cd-bg text-cd-text-tertiary'
  }
}
