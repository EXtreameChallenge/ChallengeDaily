import dayjs from 'dayjs'
import { ToggleSwitch } from '../../../components/shared'
import { Server, Bot, Loader2, CheckCircle } from 'lucide-react'

interface IntegrationSectionProps {
  highlighted: boolean
  telemetryEnabled: boolean
  integrationBusy: 'telemetry' | 'mcp' | false
  handleIntegrationToggle: (key: 'telemetry_enabled' | 'mcp_enabled', value: boolean) => void
  telemetryEvents: Array<{ event: string; data: Record<string, unknown>; time: number }>
  handleClearTelemetry: () => void
  mcpEnabled: boolean
  wecomConfigured: boolean
  wecomWebhook: string
  setWecomWebhook: (v: string) => void
  handleSaveWecom: () => void
  wecomBusy: boolean
}

export function IntegrationSection({ highlighted, telemetryEnabled, integrationBusy, handleIntegrationToggle, telemetryEvents, handleClearTelemetry, mcpEnabled, wecomConfigured, wecomWebhook, setWecomWebhook, handleSaveWecom, wecomBusy }: IntegrationSectionProps) {
  return (
      <section
        id="settings-section-集成"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Server size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">集成</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          两个开关默认关闭。遥测只写本机 JSONL、绝不上传；MCP 开关控制外部客户端能否启动 stdio 服务。
        </div>

        <div className="rounded-xl border border-cd-border p-4 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm text-cd-text">本地诊断遥测</div>
              <div className="text-xs text-cd-text-tertiary mt-0.5">
                采集失败、AI 熔断、后端异常三类事件；仅保存在本机 SQLite（enterprise_telemetry）
              </div>
            </div>
            <ToggleSwitch
              checked={telemetryEnabled}
              disabled={integrationBusy === 'telemetry'}
              onChange={(v) => handleIntegrationToggle('telemetry_enabled', v)}
            />
          </div>
          {telemetryEnabled && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-xs text-cd-text-secondary">最近事件（{telemetryEvents.length}）</div>
                <button
                  onClick={handleClearTelemetry}
                  className="text-xs text-cd-red hover:underline"
                >
                  清空
                </button>
              </div>
              {telemetryEvents.length === 0 ? (
                <div className="text-xs text-cd-text-tertiary">暂无事件；触发一次失败或熔断后会出现在这里。</div>
              ) : (
                <div className="space-y-1.5 max-h-40 overflow-y-auto">
                  {telemetryEvents.slice(0, 5).map((ev, i) => (
                    <div key={`${ev.time}-${i}`} className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-mono text-cd-text-secondary">{ev.event}</span>
                      <span className="text-cd-text-tertiary">
                        {dayjs.unix(ev.time).format('MM-DD HH:mm:ss')}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-cd-border p-4 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm text-cd-text">MCP stdio 服务</div>
              <div className="text-xs text-cd-text-tertiary mt-0.5">
                开启后外部 MCP 客户端可启动 mcp_server.py；关闭时服务拒绝启动，避免默认暴露工具面。
              </div>
            </div>
            <ToggleSwitch
              checked={mcpEnabled}
              disabled={integrationBusy === 'mcp'}
              onChange={(v) => handleIntegrationToggle('mcp_enabled', v)}
            />
          </div>
          <div className="text-xs text-cd-text-tertiary">
            状态：{mcpEnabled ? '已开启（需重启外部客户端生效）' : '已关闭'} · 联调文档 docs/mcp-integration.md
          </div>
          {mcpEnabled && (
            <pre className="text-[11px] leading-5 bg-cd-bg-secondary rounded-lg p-3 overflow-x-auto text-cd-text-secondary">
{`{
  "mcpServers": {
    "challenge-daily": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "${'<repo>'}"
    }
  }
}`}
            </pre>
          )}
        </div>

        <div className="rounded-xl border border-cd-border p-4 space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-sm text-cd-text">
                <Bot size={14} className="text-cd-green" />
                企微群机器人日报
              </div>
              <div className="text-xs text-cd-text-tertiary mt-0.5">
                通过企业微信群机器人 webhook 外发日报；未配置时不会发送任何消息。
              </div>
            </div>
            <span className={`text-xs px-2.5 py-0.5 rounded-full whitespace-nowrap ${
              wecomConfigured
                ? 'bg-cd-green-light text-cd-green'
                : 'bg-cd-bg-secondary text-cd-text-tertiary'
            }`}>
              {wecomConfigured ? '已配置' : '未配置'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={wecomWebhook}
              onChange={(e) => setWecomWebhook(e.target.value)}
              placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
              className="flex-1 min-w-0 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-xs focus:outline-none focus:border-cd-green transition-colors"
            />
            <button
              onClick={handleSaveWecom}
              disabled={wecomBusy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-2xl text-xs font-medium bg-cd-accent text-white hover:opacity-90 transition-opacity disabled:opacity-40 whitespace-nowrap"
            >
              {wecomBusy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
              {wecomBusy ? '测试中...' : '保存并测试'}
            </button>
          </div>
          <div className="text-xs text-cd-text-tertiary">
            保存后会真实发送一条“连接测试”消息；只有企微返回 errcode 0 才会标记已配置。
          </div>
        </div>
      </section>
  )
}


