import { useState, useEffect, useCallback, useRef } from 'react'
import { getStatus, getSettings, updateSettings, testAiConnection, getExportActivitiesUrl, getExportAppUsageUrl, getBackupInfo, getBackupDownloadUrl, restoreBackup, type CollectorStatus, type BackendSettings } from '../api/client'
import { ToggleSwitch, useTimeout, useAsyncData, ApiErrorDisplay } from '../components/shared'
import { useToast } from '../components/Toast'
import { useTheme, ACCENT_PRESETS, FONT_PRESETS } from '../components/ThemeContext'
import { Shield, Bot, Eye, EyeOff, Server, FileText, ListFilter, Download, Loader2, CheckCircle, XCircle, RotateCcw, Database, Upload, HardDrive, Info, RefreshCw, Palette, Type, GlassWater, Moon, Cat } from 'lucide-react'
import dayjs from 'dayjs'

export default function Settings() {
  const toast = useToast()
  const { theme, toggleTheme, accentIndex, setAccentIndex, fontIndex, setFontIndex, sidebarTranslucent, setSidebarTranslucent } = useTheme()
  const [aiEnabled, setAiEnabled] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('https://open.bigmodel.cn/api/paas/v4')
  const [apiVisionModel, setApiVisionModel] = useState('glm-4v-flash')
  const [apiTextModel, setApiTextModel] = useState('glm-4-flash')
  const [showKey, setShowKey] = useState(false)
  const [excludeApps, setExcludeApps] = useState('')
  const [interval, setInterval_] = useState(60)
  const [workStart, setWorkStart] = useState(9)
  const [workEnd, setWorkEnd] = useState(18)
  const [customInstr, setCustomInstr] = useState('')
  const [saved, setSaved] = useState(false)
  // AI Key 配置状态（从后端 settings 读取，不暴露明文）
  const [apiKeySet, setApiKeySet] = useState(false)
  const [showKeyInput, setShowKeyInput] = useState(false)
  // AI 测试状态
  const [aiTesting, setAiTesting] = useState<'vision' | 'text' | false>(false)
  const [aiTestResult, setAiTestResult] = useState<{ ok: boolean; message: string; label?: string } | null>(null)
  // 导出日期范围
  const [exportStart, setExportStart] = useState(dayjs().subtract(7, 'day').format('YYYY-MM-DD'))
  const [exportEnd, setExportEnd] = useState(dayjs().format('YYYY-MM-DD'))
  // 备份/恢复
  const [restoring, setRestoring] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 关于与更新
  const [appVersion, setAppVersion] = useState('')
  const [updateChecking, setUpdateChecking] = useState(false)
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'available' | 'downloading' | 'downloaded' | 'up-to-date'>('idle')
  // 桌面宠物可见性
  const [petVisible, setPetVisible] = useState<boolean>(!!(window as any)._petVisible)

  const handleTogglePet = (show: boolean) => {
    setPetVisible(show)
    ;(window as any)._petVisible = show
    window.electronAPI?.togglePet?.(show)
  }

  // 安全 setTimeout — saved 状态自动消失
  useTimeout(() => setSaved(false), saved ? 2000 : null)

  const { data: initialData, loading, error, refresh: refreshData } = useAsyncData(async () => {
    const [s, settings, bInfo] = await Promise.all([
      getStatus(),
      getSettings(),
      getBackupInfo().catch(() => null),
    ])
    return { status: s, settings, backupInfo: bInfo }
  }, [])

  const status = initialData?.status ?? null
  const backupInfo = initialData?.backupInfo ?? null

  useEffect(() => {
    if (!initialData) return
    const { status: s, settings } = initialData
    // 优先使用 settings 中用户显式设置的 ai_enabled，避免 status 因 key 缺失而返回 false 导致开关被强制关闭
    setAiEnabled(settings.ai_enabled ?? s.ai_enabled)
    setApiKeySet(!!(settings as any).ai_api_key_set)
    setShowKeyInput(!(settings as any).ai_api_key_set)
    setExcludeApps(settings.exclude_apps.join(', '))
    setInterval_(settings.screenshot_interval_sec)
    setWorkStart(settings.work_start_hour)
    setWorkEnd(settings.work_end_hour)
    setCustomInstr(settings.custom_report_instructions || '')
    setApiBase(settings.ai_base_url || 'https://open.bigmodel.cn/api/paas/v4')
    // 兼容旧版单模型字段 ai_model
    const legacyModel = (settings as any).ai_model
    setApiVisionModel(settings.ai_vision_model || legacyModel || 'glm-4v-flash')
    setApiTextModel(settings.ai_text_model || legacyModel || 'glm-4-flash')
  }, [initialData])

  // 获取应用版本
  useEffect(() => {
    if (window.electronAPI?.getAppVersion) {
      window.electronAPI.getAppVersion().then(v => setAppVersion(v))
    }
  }, [])

  // 监听更新状态
  useEffect(() => {
    if (!window.electronAPI) return
    window.electronAPI.onUpdateAvailable(() => setUpdateStatus('available'))
    window.electronAPI.onUpdateProgress(() => setUpdateStatus('downloading'))
    window.electronAPI.onUpdateDownloaded(() => setUpdateStatus('downloaded'))
  }, [])

  const handleCheckUpdate = async () => {
    setUpdateChecking(true)
    try {
      await window.electronAPI?.checkForUpdates()
      setTimeout(() => {
        setUpdateChecking(false)
        if (updateStatus === 'idle') setUpdateStatus('up-to-date')
      }, 2000)
    } catch {
      setUpdateChecking(false)
    }
  }

  const _validateWorkHours = useCallback((): string | null => {
    if (workStart < 0 || workStart > 23 || workEnd < 0 || workEnd > 23) {
      return '工作时间必须在 0-23 之间'
    }
    if (workStart >= workEnd) {
      return '工作开始时间必须早于结束时间'
    }
    return null
  }, [workStart, workEnd])

  const handleSave = async () => {
    // 工时校验
    const validationError = _validateWorkHours()
    if (validationError) {
      toast.warning(validationError)
      return
    }

    try {
      const appsList = excludeApps
        .split(/[,\n]/)
        .map(s => s.trim())
        .filter(Boolean)

      const settings: Partial<BackendSettings> = {
        exclude_apps: appsList,
        screenshot_interval_sec: interval,
        work_start_hour: workStart,
        work_end_hour: workEnd,
        custom_report_instructions: customInstr,
        ai_base_url: apiBase,
        ai_vision_model: apiVisionModel,
        ai_text_model: apiTextModel,
        ai_enabled: aiEnabled,
      }
      // 仅当用户实际输入了 API Key 时才发送（避免清空已保存的 key）
      if (apiKey.trim()) {
        (settings as any).ai_api_key = apiKey.trim()
      }

      const res = await updateSettings(settings)
      setSaved(true)
      // 如果用户输入了新的 API Key，保存成功后标记为已配置并隐藏输入框
      if (apiKey.trim()) {
        setApiKeySet(true)
        setShowKeyInput(false)
        setApiKey('')
      }
      // 同步后端返回的最新状态（含 ai_api_key_set）
      if (res.settings) {
        setApiKeySet(!!(res.settings as any).ai_api_key_set)
      }
      toast.success('设置已保存')
    } catch (err) {
      console.error('Failed to save settings:', err)
      toast.error('保存失败，请重试')
    }
  }

  const handleResetDefaults = async () => {
    try {
      const defaultSettings: Partial<BackendSettings> = {
        exclude_apps: ['WeChat', '飞书', 'DingTalk', '1Password'],
        screenshot_interval_sec: 60,
        work_start_hour: 9,
        work_end_hour: 18,
        custom_report_instructions: '',
        ai_base_url: 'https://open.bigmodel.cn/api/paas/v4',
        ai_vision_model: 'glm-4v-flash',
        ai_text_model: 'glm-4-flash',
        ai_enabled: false,
      }
      await updateSettings(defaultSettings)
      // 重置本地状态
      setExcludeApps(defaultSettings.exclude_apps!.join(', '))
      setInterval_(defaultSettings.screenshot_interval_sec!)
      setWorkStart(defaultSettings.work_start_hour!)
      setWorkEnd(defaultSettings.work_end_hour!)
      setCustomInstr('')
      setApiBase(defaultSettings.ai_base_url!)
      setApiVisionModel(defaultSettings.ai_vision_model!)
      setApiTextModel(defaultSettings.ai_text_model!)
      setAiEnabled(false)
      setApiKey('')
      setApiKeySet(false)
      setShowKeyInput(true)
      toast.success('已恢复默认设置')
    } catch (err) {
      toast.error('恢复默认失败')
    }
  }

  const handleTestAi = async (model: 'vision' | 'text') => {
    setAiTesting(model)
    setAiTestResult(null)
    try {
      const modelName = model === 'vision' ? apiVisionModel : apiTextModel
      const result = await testAiConnection(apiKey, apiBase, modelName)
      setAiTestResult({ ...result, label: model === 'vision' ? '识图模型' : '文本模型' })
    } catch (err: any) {
      setAiTestResult({ ok: false, message: err.message || '测试失败', label: model === 'vision' ? '识图模型' : '文本模型' })
    } finally {
      setAiTesting(false as any)
    }
  }

  const handleRestore = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setRestoring(true)
    try {
      const result = await restoreBackup(file)
      toast.success(`数据恢复成功，已恢复 ${result.restored_files.length} 个文件`)
      refreshData()
    } catch (err: any) {
      toast.error(err.message || '数据恢复失败')
    } finally {
      setRestoring(false)
      // 清空 file input 以允许重复选择同一文件
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  if (error) {
    return <ApiErrorDisplay error={error} onRetry={refreshData} />
  }

  if (loading) {
    return <div className="animate-pulse text-cd-text-tertiary">加载中...</div>
  }

  return (
    <div className="animate-fade-in space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-cd-text">设置</h1>
        <button
          onClick={handleResetDefaults}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
        >
          <RotateCcw size={12} />
          恢复默认
        </button>
      </div>

      {/* ─── 外观设置 ──────────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Palette size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">外观设置</h2>
        </div>

        <div className="space-y-4">
          {/* 深色模式 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Moon size={14} className="text-cd-text-tertiary" />
              <span className="text-sm text-cd-text">深色模式</span>
            </div>
            <ToggleSwitch checked={theme === 'dark'} onChange={toggleTheme} />
          </div>

          {/* 桌面宠物 */}
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Cat size={14} className="text-cd-text-tertiary" />
                <span className="text-sm text-cd-text">桌面宠物</span>
              </div>
              <p className="text-[10px] text-cd-text-tertiary ml-[22px] mt-0.5">在桌面上显示陪伴小宠物</p>
            </div>
            <ToggleSwitch checked={petVisible} onChange={handleTogglePet} />
          </div>

          {/* 主题色 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Palette size={14} className="text-cd-text-tertiary" />
              <span className="text-sm text-cd-text">主题色</span>
            </div>
            <div className="flex flex-wrap gap-2.5">
              {ACCENT_PRESETS.map((preset, i) => (
                <button
                  key={i}
                  onClick={() => setAccentIndex(i)}
                  className={`group relative w-8 h-8 rounded-full transition-all duration-150 ${
                    i === accentIndex
                      ? 'ring-2 ring-offset-2 scale-110'
                      : 'hover:scale-105'
                  }`}
                  style={{
                    backgroundColor: theme === 'dark' ? preset.dark : preset.light,
                    ringColor: theme === 'dark' ? preset.dark : preset.light,
                    // @ts-ignore ring-offset-color not in CSSProperties
                    '--tw-ring-color': theme === 'dark' ? preset.dark : preset.light,
                  } as React.CSSProperties}
                  title={preset.name}
                >
                  {i === accentIndex && (
                    <CheckCircle size={14} className="absolute inset-0 m-auto text-white drop-shadow-sm" />
                  )}
                  <span className="sr-only">{preset.name}</span>
                </button>
              ))}
            </div>
            <p className="text-[10px] text-cd-text-tertiary mt-1.5">
              当前：{ACCENT_PRESETS[accentIndex].name}
            </p>
          </div>

          {/* 字体 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Type size={14} className="text-cd-text-tertiary" />
              <span className="text-sm text-cd-text">字体</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {FONT_PRESETS.map((f, i) => (
                <button
                  key={i}
                  onClick={() => setFontIndex(i)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 border ${
                    i === fontIndex
                      ? 'bg-cd-green-light text-cd-green border-cd-green/30'
                      : 'bg-cd-bg-secondary text-cd-text-secondary border-cd-border hover:bg-cd-hover'
                  }`}
                  style={i === fontIndex ? {} : { fontFamily: f.value }}
                >
                  {f.name}
                </button>
              ))}
            </div>
          </div>

          {/* 侧边栏毛玻璃 */}
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <GlassWater size={14} className="text-cd-text-tertiary" />
                <span className="text-sm text-cd-text">侧边栏毛玻璃</span>
              </div>
              <p className="text-[10px] text-cd-text-tertiary ml-[22px] mt-0.5">半透明模糊效果，需重启应用生效</p>
            </div>
            <ToggleSwitch checked={sidebarTranslucent} onChange={setSidebarTranslucent} />
          </div>
        </div>
      </section>

      {/* ─── 采集设置 ────────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Server size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">采集设置</h2>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">截图间隔（秒）</label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                value={interval}
                onChange={(e) => setInterval_(Number(e.target.value))}
                min={15}
                max={300}
                step={5}
                className="flex-1 accent-cd-green"
              />
              <span className="text-sm text-cd-text w-14 text-right">{interval}s</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">工作开始时间</label>
              <input
                type="number"
                value={workStart}
                onChange={(e) => setWorkStart(Number(e.target.value))}
                min={0}
                max={23}
                className={`w-full bg-cd-bg-secondary text-cd-text border rounded-lg px-3 py-1.5 text-sm focus:outline-none transition-colors ${
                  workStart >= workEnd ? 'border-cd-red focus:border-cd-red' : 'border-cd-border focus:border-cd-green'
                }`}
              />
            </div>
            <div>
              <label className="text-xs text-cd-text-secondary block mb-1">工作结束时间</label>
              <input
                type="number"
                value={workEnd}
                onChange={(e) => setWorkEnd(Number(e.target.value))}
                min={0}
                max={23}
                className={`w-full bg-cd-bg-secondary text-cd-text border rounded-lg px-3 py-1.5 text-sm focus:outline-none transition-colors ${
                  workEnd <= workStart ? 'border-cd-red focus:border-cd-red' : 'border-cd-border focus:border-cd-green'
                }`}
              />
            </div>
          </div>
          {workStart >= workEnd && (
            <p className="text-xs text-cd-red">开始时间必须早于结束时间</p>
          )}

          <div className="flex items-center justify-between">
            <span className="text-sm text-cd-text">采集器状态</span>
            <span className={`text-xs px-2.5 py-0.5 rounded-full ${
              status === null
                ? 'bg-cd-bg-secondary text-cd-text-tertiary'
                : status?.running
                  ? 'bg-cd-green-light text-cd-green'
                  : 'bg-cd-red-light text-cd-red'
            }`}>
              {status === null ? '连接中...' : status?.running ? '运行中' : '已暂停'}
            </span>
          </div>
        </div>
      </section>

      {/* ─── 排除应用 ──────────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <ListFilter size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">排除应用</h2>
        </div>

        <div>
          <label className="text-xs text-cd-text-secondary block mb-1">
            不记录的应用（每行一个，或逗号分隔）
          </label>
          <textarea
            value={excludeApps}
            onChange={(e) => setExcludeApps(e.target.value)}
            rows={5}
            placeholder="WeChat&#10;飞书&#10;DingTalk&#10;outlook"
            className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none font-mono"
          />
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 匹配逻辑：应用名或窗口标题包含上述关键词时不截图、不记录</p>
          <p>• 默认排除微信、飞书、钉钉、1Password 等隐私应用</p>
          <p>• 修改后即时生效，无需重启</p>
        </div>
      </section>

      {/* ─── AI 配置 ──────────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">AI 配置</h2>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-cd-text">启用 AI 分析</span>
            <ToggleSwitch checked={aiEnabled} onChange={setAiEnabled} />
          </div>

          {aiEnabled && (
            <>
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">API Base URL</label>
                <input
                  type="text"
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-cd-text-secondary block mb-1">识图模型（Vision）</label>
                  <input
                    type="text"
                    value={apiVisionModel}
                    onChange={(e) => setApiVisionModel(e.target.value)}
                    placeholder="glm-4v-flash"
                    className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                  />
                </div>
                <div>
                  <label className="text-xs text-cd-text-secondary block mb-1">文本模型（Text）</label>
                  <input
                    type="text"
                    value={apiTextModel}
                    onChange={(e) => setApiTextModel(e.target.value)}
                    placeholder="glm-4-flash"
                    className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">API Key</label>
                {apiKeySet && !showKeyInput ? (
                  <div className="flex items-center justify-between bg-cd-green-light border border-cd-green/20 rounded-lg px-3 py-2">
                    <div className="flex items-center gap-2 text-sm text-cd-green">
                      <CheckCircle size={14} />
                      <span>已配置（Windows 加密存储）</span>
                    </div>
                    <button
                      onClick={() => { setShowKeyInput(true); setApiKey('') }}
                      className="text-xs text-cd-green hover:opacity-80 font-medium"
                    >
                      更换
                    </button>
                  </div>
                ) : (
                  <div className="relative">
                    <input
                      type={showKey ? 'text' : 'password'}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="sk-..."
                      className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 pr-9 text-sm focus:outline-none focus:border-cd-green transition-colors"
                    />
                    <button
                      onClick={() => setShowKey(!showKey)}
                      className="absolute right-2 top-1.5 text-cd-text-tertiary hover:text-cd-text transition-colors"
                    >
                      {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                )}
              </div>

              {/* AI 测试按钮 */}
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => handleTestAi('vision')}
                  disabled={!!aiTesting || !(apiKey || apiKeySet)}
                  className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors disabled:opacity-40 border border-cd-border"
                >
                  {aiTesting === 'vision' ? (
                    <><Loader2 size={12} className="animate-spin" /> 测试识图模型...</>
                  ) : (
                    <>测试识图模型</>
                  )}
                </button>
                <button
                  onClick={() => handleTestAi('text')}
                  disabled={!!aiTesting || !(apiKey || apiKeySet)}
                  className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors disabled:opacity-40 border border-cd-border"
                >
                  {aiTesting === 'text' ? (
                    <><Loader2 size={12} className="animate-spin" /> 测试文本模型...</>
                  ) : (
                    <>测试文本模型</>
                  )}
                </button>
                {aiTestResult && (
                  <div className={`flex items-center gap-1.5 text-xs ${
                    aiTestResult.ok ? 'text-cd-green' : 'text-cd-red'
                  }`}>
                    {aiTestResult.ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
                    <span className="font-medium">{aiTestResult.label}：</span>
                    {aiTestResult.message}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </section>

      {/* ─── 日报自定义指令 ─────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">日报自定义指令</h2>
        </div>

        <div>
          <label className="text-xs text-cd-text-secondary block mb-1">
            追加到日报生成指令中的自定义要求（可选）
          </label>
          <textarea
            value={customInstr}
            onChange={(e) => setCustomInstr(e.target.value)}
            rows={3}
            placeholder="例如：重点关注开发相关活动，会议和沟通简要概括即可"
            className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-cd-green transition-colors resize-none"
          />
        </div>
        <div className="text-xs text-cd-text-tertiary">
          该指令会在生成日报时附加到 AI 提示词中，影响报告的重点和风格
        </div>
      </section>

      {/* ─── 数据导出 ──────────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Download size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">数据导出</h2>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">开始日期</label>
            <input
              type="date"
              value={exportStart}
              onChange={(e) => setExportStart(e.target.value)}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">结束日期</label>
            <input
              type="date"
              value={exportEnd}
              onChange={(e) => setExportEnd(e.target.value)}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
        </div>

        <div className="flex gap-3">
          <a
            onClick={async (e) => { e.preventDefault(); window.open(await getExportActivitiesUrl(exportStart, exportEnd), '_blank') }}
            href="#"
            download
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer"
          >
            <Download size={12} />
            导出活动记录
          </a>
          <a
            onClick={async (e) => { e.preventDefault(); window.open(await getExportAppUsageUrl(exportStart, exportEnd), '_blank') }}
            href="#"
            download
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer"
          >
            <Download size={12} />
            导出应用使用
          </a>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          导出为 CSV 格式，可用 Excel 打开。BOM 编码确保中文兼容。
        </div>
      </section>

      {/* ─── 数据备份与恢复 ────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">数据备份与恢复</h2>
        </div>

        {backupInfo && (
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-cd-bg-secondary rounded-lg p-3 text-center">
              <div className="text-sm font-bold text-cd-green">{backupInfo.db_size_mb} MB</div>
              <div className="text-[10px] text-cd-text-tertiary mt-0.5">数据库大小</div>
            </div>
            <div className="bg-cd-bg-secondary rounded-lg p-3 text-center">
              <div className="text-sm font-bold text-cd-green">{backupInfo.activities_count}</div>
              <div className="text-[10px] text-cd-text-tertiary mt-0.5">活动记录</div>
            </div>
            <div className="bg-cd-bg-secondary rounded-lg p-3 text-center">
              <div className="text-sm font-bold text-cd-green">{backupInfo.reports_count}</div>
              <div className="text-[10px] text-cd-text-tertiary mt-0.5">历史报告</div>
            </div>
          </div>
        )}

        <div className="flex gap-3">
          <a
            onClick={async (e) => { e.preventDefault(); window.open(await getBackupDownloadUrl(), '_blank') }}
            href="#"
            download
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer"
          >
            <Download size={12} />
            创建备份
          </a>
          <label className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer disabled:opacity-50">
            {restoring ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
            {restoring ? '恢复中...' : '从备份恢复'}
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              onChange={handleRestore}
              className="hidden"
              disabled={restoring}
            />
          </label>
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 备份包含数据库、设置和 Webhook 配置，导出为 ZIP 文件</p>
          <p>• 恢复前会自动备份当前数据，操作后需重启应用生效</p>
        </div>
      </section>

      {/* ─── 隐私说明 ──────────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">隐私保护</h2>
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 截图在 AI 分析完成后会自动删除，不会保存到磁盘</p>
          <p>• 所有数据仅保存于本地 SQLite 数据库，不上传任何服务器</p>
          <p>• AI 分析时自动脱敏：隐藏人名、手机号、金额等敏感信息</p>
          <p>• 排除列表中的应用不会被截图和记录</p>
          <p>• API Key 使用 Windows 系统加密存储 (DPAPI)，不以明文保存</p>
        </div>
      </section>

      {/* ─── 关于与更新 ────────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Info size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">关于与更新</h2>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-bold text-cd-text font-brand">ChallengeDaily</p>
            <p className="text-xs text-cd-text-tertiary">
              版本 {appVersion || '—'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {updateStatus === 'downloaded' ? (
              <button
                onClick={() => window.electronAPI?.installUpdate()}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:opacity-90 transition-opacity"
              >
                重启安装更新
              </button>
            ) : updateStatus === 'downloading' ? (
              <span className="text-xs text-cd-text-secondary">下载中...</span>
            ) : updateStatus === 'up-to-date' ? (
              <span className="flex items-center gap-1 text-xs text-cd-green">
                <CheckCircle size={12} />
                已是最新版本
              </span>
            ) : (
              <button
                onClick={handleCheckUpdate}
                disabled={updateChecking}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
              >
                {updateChecking ? (
                  <><Loader2 size={12} className="animate-spin" /> 检查中...</>
                ) : (
                  <><RefreshCw size={12} /> 检查更新</>
                )}
              </button>
            )}
          </div>
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 本软件为免费开源软件，数据完全本地存储</p>
          <p>• 如需帮助或反馈问题，请访问项目主页</p>
        </div>
      </section>

      {/* ─── 保存按钮 ─────────────────────────── */}
      <button
        onClick={handleSave}
        className={`w-full py-2.5 rounded-lg text-sm font-medium transition-colors ${
          saved
            ? 'bg-cd-green-light text-cd-green'
            : 'bg-cd-green hover:bg-cd-green-dark text-white'
        }`}
      >
        {saved ? '已保存' : '保存设置'}
      </button>
    </div>
  )
}
