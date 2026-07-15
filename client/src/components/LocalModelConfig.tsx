/**
 * P19-4: 本地小模型降级配置 UI
 * 配置 Ollama 地址、模型选择、自动降级开关
 */
import { useState, useEffect, useCallback } from 'react'
import {
  getLocalModelStatus, updateLocalModelConfig, listLocalModels, testLocalModel,
  type LocalModelConfig, type LocalModelStatus,
} from '../api/client'
import { useToast } from './Toast'
import { ToggleSwitch, useAsyncData, ApiErrorDisplay } from './shared'
import { Cpu, RefreshCw, Loader2, CheckCircle, XCircle, Zap } from 'lucide-react'

export default function LocalModelConfigPanel() {
  const toast = useToast()
  const [status, setStatus] = useState<LocalModelStatus | null>(null)
  const [config, setConfig] = useState<LocalModelConfig | null>(null)
  const [models, setModels] = useState<Array<{ name: string; size_mb: number }>>([])
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [statusRes, modelsRes] = await Promise.all([
        getLocalModelStatus(),
        listLocalModels().catch(() => ({ models: [] })),
      ])
      setStatus(statusRes)
      setConfig(statusRes.config)
      setModels(modelsRes.models || [])
    } catch (err: any) {
      console.warn('本地模型状态加载失败:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleUpdate = async (patch: Partial<LocalModelConfig>) => {
    if (!config) return
    const newConfig = { ...config, ...patch }
    setConfig(newConfig)
    setSaving(true)
    try {
      await updateLocalModelConfig(patch)
    } catch (err: any) {
      toast.error(err.message || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const r = await testLocalModel('text')
      setTestResult({
        ok: r.ok,
        message: r.ok ? (r.result?.text?.slice(0, 80) || '测试成功') : (r.result?.error || '测试失败'),
      })
      if (r.ok) toast.success('本地模型测试通过')
      else toast.error('本地模型测试失败')
    } catch (err: any) {
      setTestResult({ ok: false, message: err.message || '测试失败' })
      toast.error('测试失败')
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return <div className="text-xs text-cd-text-tertiary">加载中...</div>
  }

  const ollamaAvailable = status?.health?.available

  return (
    <div className="space-y-3">
      {/* Ollama 状态 */}
      <div className={`flex items-center gap-2 p-2 rounded text-xs ${
        ollamaAvailable
          ? 'bg-cd-green-light text-cd-green'
          : 'bg-cd-bg-secondary text-cd-text-tertiary'
      }`}>
        {ollamaAvailable ? <CheckCircle size={12} /> : <XCircle size={12} />}
        <span>Ollama {ollamaAvailable ? '已连接' : '未连接'}</span>
        {ollamaAvailable && status?.health?.model_count !== undefined && (
          <span className="text-cd-text-tertiary">· {status.health.model_count} 个模型</span>
        )}
        <button onClick={refresh} className="ml-auto text-cd-text-tertiary hover:text-cd-text">
          <RefreshCw size={11} />
        </button>
      </div>

      {!ollamaAvailable && (
        <div className="text-[10px] text-cd-text-tertiary p-2 bg-cd-bg-secondary rounded">
          安装 Ollama：访问 <span className="text-cd-green">ollama.com</span> 下载安装，
          然后运行 <code className="text-cd-text">ollama pull qwen2.5:7b</code> 拉取模型
        </div>
      )}

      {/* 启用开关 */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-cd-text">启用本地模型降级</div>
          <div className="text-[10px] text-cd-text-tertiary">云端 AI 不可用时自动切换到本地 Ollama</div>
        </div>
        <ToggleSwitch
          checked={config?.enabled || false}
          onChange={(v) => handleUpdate({ enabled: v })}
        />
      </div>

      {config?.enabled && (
        <>
          {/* Base URL */}
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">Ollama API 地址</label>
            <input
              type="text"
              value={config?.base_url || 'http://127.0.0.1:11434'}
              onChange={(e) => handleUpdate({ base_url: e.target.value })}
              placeholder="http://127.0.0.1:11434"
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded px-2 py-1 text-xs focus:outline-none focus:border-cd-green"
            />
          </div>

          {/* 模型选择 */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">视觉模型（截图分类）</label>
              {models.length > 0 ? (
                <select
                  value={config?.vision_model || 'llava'}
                  onChange={(e) => handleUpdate({ vision_model: e.target.value })}
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded px-2 py-1 text-xs focus:outline-none focus:border-cd-green"
                >
                  <option value="llava">llava（默认）</option>
                  {models.filter(m => /vl|llava|vision/i.test(m.name)).map(m => (
                    <option key={m.name} value={m.name}>
                      {m.name} ({Math.round(m.size_mb)}MB)
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={config?.vision_model || 'llava'}
                  onChange={(e) => handleUpdate({ vision_model: e.target.value })}
                  placeholder="llava"
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded px-2 py-1 text-xs focus:outline-none focus:border-cd-green"
                />
              )}
            </div>
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">文本模型（日报生成）</label>
              {models.length > 0 ? (
                <select
                  value={config?.text_model || 'qwen2.5:7b'}
                  onChange={(e) => handleUpdate({ text_model: e.target.value })}
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded px-2 py-1 text-xs focus:outline-none focus:border-cd-green"
                >
                  <option value="qwen2.5:7b">qwen2.5:7b（默认）</option>
                  {models.map(m => (
                    <option key={m.name} value={m.name}>
                      {m.name} ({Math.round(m.size_mb)}MB)
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={config?.text_model || 'qwen2.5:7b'}
                  onChange={(e) => handleUpdate({ text_model: e.target.value })}
                  placeholder="qwen2.5:7b"
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded px-2 py-1 text-xs focus:outline-none focus:border-cd-green"
                />
              )}
            </div>
          </div>

          {/* 自动降级 + 规则兜底 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-cd-text">云端失败自动降级</div>
                <div className="text-[10px] text-cd-text-tertiary">检测到云端不可用时自动切换本地</div>
              </div>
              <ToggleSwitch
                checked={config?.auto_fallback ?? true}
                onChange={(v) => handleUpdate({ auto_fallback: v })}
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-cd-text">规则引擎兜底</div>
                <div className="text-[10px] text-cd-text-tertiary">本地模型也失败时用关键词规则</div>
              </div>
              <ToggleSwitch
                checked={config?.fallback_to_rules ?? true}
                onChange={(v) => handleUpdate({ fallback_to_rules: v })}
              />
            </div>
          </div>

          {/* 超时配置 */}
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">
              推理超时（秒）：{config?.timeout_sec || 60}
            </label>
            <input
              type="range" min={15} max={300} step={5}
              value={config?.timeout_sec || 60}
              onChange={(e) => handleUpdate({ timeout_sec: parseInt(e.target.value) })}
              className="w-full"
            />
          </div>

          {/* 测试按钮 */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleTest}
              disabled={testing || !ollamaAvailable}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover border border-cd-border disabled:opacity-40"
            >
              {testing ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
              测试本地模型
            </button>
            {testResult && (
              <div className={`text-xs flex items-center gap-1 ${
                testResult.ok ? 'text-cd-green' : 'text-cd-red'
              }`}>
                {testResult.ok ? <CheckCircle size={11} /> : <XCircle size={11} />}
                <span className="truncate max-w-xs">{testResult.message}</span>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
