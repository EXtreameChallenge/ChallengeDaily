import { useState, useEffect, useCallback, useRef } from 'react'
import { getStatus, getSettings, updateSettings, testAiConnection, downloadExportActivities, downloadExportAppUsage, getBackupInfo, downloadBackup, restoreBackup, previewImport, executeImport, request, getMemoryStatus, uploadOpmlFile, type CollectorStatus, type BackendSettings, type MemoryStatus } from '../api/client'
import { ToggleSwitch, useTimeout, useAsyncData, ApiErrorDisplay } from '../components/shared'
import { useToast } from '../components/Toast'
import { useTheme, ACCENT_PRESETS, FONT_PRESETS, RADIUS_PRESETS, SHADOW_PRESETS, OPACITY_PRESETS, SKIN_PRESETS } from '../components/ThemeContext'
import { AppLockSettings } from '../components/AppLock'
import { Shield, Bot, Eye, EyeOff, Server, FileText, ListFilter, Download, Loader2, CheckCircle, XCircle, RotateCcw, Database, Upload, HardDrive, Info, RefreshCw, Palette, Type, GlassWater, Moon, Cat, Rocket, Search, Calendar, GitBranch, Cpu, Cloud, Brain, FileUp, Heart } from 'lucide-react'
import dayjs from 'dayjs'
import CalendarSubscriptionManager from '../components/CalendarSubscriptionManager'
import GitRepoManager from '../components/GitRepoManager'
import LocalModelConfigPanel from '../components/LocalModelConfig'

// ── 幕布文档接入 ──
type MubuStatus = 'idle' | 'syncing' | 'synced' | 'cookie_invalid' | 'error' | 'unknown'

interface MubuStatusInfo {
  doc_count: number
  last_sync: string | null
  status?: string
}

interface MubuDoc {
  id: string | number
  title: string
  url?: string
  updated_at?: string
}

// 将后端/IPC 返回的同步状态字符串归一化为前端枚举
function normalizeMubuStatus(s: string | undefined | null): MubuStatus {
  const v = (s || '').toLowerCase()
  if (!v) return 'unknown'
  if (v.includes('syncing') || v.includes('running') || v.includes('progress')) return 'syncing'
  if (v.includes('synced') || v.includes('done') || v.includes('complete') || v.includes('ok') || v.includes('success')) return 'synced'
  if (v.includes('cookie') || v.includes('unauthorized') || v.includes('auth') || v.includes('invalid') || v.includes('expire')) return 'cookie_invalid'
  if (v.includes('error') || v.includes('fail')) return 'error'
  return 'idle'
}

const MUBU_STATUS_META: Record<MubuStatus, { label: string; className: string }> = {
  idle: { label: '未同步', className: 'bg-cd-bg-secondary text-cd-text-tertiary' },
  syncing: { label: '同步中', className: 'bg-cd-green-light text-cd-green' },
  synced: { label: '已同步', className: 'bg-cd-green-light text-cd-green' },
  cookie_invalid: { label: 'Cookie 失效', className: 'bg-cd-red-light text-cd-red' },
  error: { label: '错误', className: 'bg-cd-red-light text-cd-red' },
  unknown: { label: '未知', className: 'bg-cd-bg-secondary text-cd-text-tertiary' },
}

export default function Settings() {
  const toast = useToast()
  const {
    theme, effectiveTheme, setThemeExplicit,
    accentIndex, setAccentIndex,
    fontIndex, setFontIndex,
    sidebarTranslucent, setSidebarTranslucent,
    radiusIndex, setRadiusIndex,
    shadowIndex, setShadowIndex,
    opacityIndex, setOpacityIndex,
    skinIndex, setSkinIndex,
    customAccent, setCustomAccent,
    fontScale, setFontScale,
  } = useTheme()
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
  // 检查更新 setTimeout 计时器引用，用于组件卸载时清理
  const checkUpdateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // 关于与更新
  const [appVersion, setAppVersion] = useState('')
  const [updateChecking, setUpdateChecking] = useState(false)
  const [updateStatus, setUpdateStatus] = useState<'idle' | 'available' | 'downloading' | 'downloaded' | 'up-to-date'>('idle')
  // 桌面宠物可见性
  const [petVisible, setPetVisible] = useState<boolean>(() => localStorage.getItem('cd_pet_visible') !== '0')
  // 开机自启动
  const [autoStart, setAutoStart] = useState(false)
  // 设置搜索
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightedSection, setHighlightedSection] = useState<string>('')
  // 幕布文档接入
  const [mubuStatus, setMubuStatus] = useState<MubuStatus>('unknown')
  const [mubuInfo, setMubuInfo] = useState<MubuStatusInfo | null>(null)
  const [mubuLogging, setMubuLogging] = useState(false)
  const [mubuSyncing, setMubuSyncing] = useState(false)
  const [mubuSearchQuery, setMubuSearchQuery] = useState('')
  const [mubuSearching, setMubuSearching] = useState(false)
  const [mubuSearchResults, setMubuSearchResults] = useState<MubuDoc[]>([])
  // OPML 导入 & 记忆向量化状态
  const [opmlUploading, setOpmlUploading] = useState(false)
  const opmlFileInputRef = useRef<HTMLInputElement>(null)
  const [memoryStatus, setMemoryStatus] = useState<MemoryStatus | null>(null)
  // 人生配置
  const [birthday, setBirthday] = useState('')
  const [lifeExpectancy, setLifeExpectancy] = useState(80)

  const handleSearch = (query: string) => {
    setSearchQuery(query)
    if (!query.trim()) { setHighlightedSection(''); return }
    // 简单匹配：遍历设置分区标题
    const sections = ['外观', '采集', 'AI', '日报', '数据', '日历', '人生', 'Git', '幕布', '备份', '导入', '隐私', '关于']
    const match = sections.find(s => s.toLowerCase().includes(query.toLowerCase()))
    if (match) {
      setHighlightedSection(match)
      // 滚动到对应区域
      const el = document.getElementById(`settings-section-${match}`)
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    } else {
      setHighlightedSection('')
    }
  }
  useEffect(() => {
    const sync = () => setPetVisible(localStorage.getItem('cd_pet_visible') !== '0')
    window.addEventListener('cd-pet-visible-change', sync)
    return () => window.removeEventListener('cd-pet-visible-change', sync)
  }, [])
  // 个人习惯配置已迁移至「深度画像」页面

  const handleTogglePet = (show: boolean) => {
    setPetVisible(show)
    ;(window as any)._petVisible = show
    localStorage.setItem('cd_pet_visible', show ? '1' : '0')
    window.dispatchEvent(new CustomEvent('cd-pet-visible-change'))
    // 通过 IPC 控制独立宠物窗口的显示/隐藏
    window.electronAPI?.togglePet(show)
  }

  const handleToggleAutoStart = async (enabled: boolean) => {
    try {
      await window.electronAPI?.setAutoStart(enabled)
      setAutoStart(enabled)
      toast.success(enabled ? '已开启开机自启动' : '已关闭开机自启动')
    } catch {
      toast.error('设置开机自启动失败')
    }
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
    // 人生配置
    setBirthday(settings.birthday || '')
    setLifeExpectancy(settings.life_expectancy || 80)
  }, [initialData])

  // 获取应用版本 & 开机自启动状态
  useEffect(() => {
    if (window.electronAPI?.getAppVersion) {
      window.electronAPI.getAppVersion().then(v => setAppVersion(v))
    }
    if (window.electronAPI?.getAutoStart) {
      window.electronAPI.getAutoStart().then(v => setAutoStart(v))
    }
  }, [])

  // 监听更新状态
  useEffect(() => {
    if (!window.electronAPI) return
    window.electronAPI.onUpdateAvailable(() => setUpdateStatus('available'))
    window.electronAPI.onUpdateProgress(() => setUpdateStatus('downloading'))
    window.electronAPI.onUpdateDownloaded(() => setUpdateStatus('downloaded'))
  }, [])

  // 组件卸载时清理检查更新的定时器，防止 setState 作用于已卸载组件
  useEffect(() => {
    return () => {
      if (checkUpdateTimerRef.current) clearTimeout(checkUpdateTimerRef.current)
    }
  }, [])

  // 幕布文档接入：拉取状态 & 监听 IPC 状态变化（不可用时降级为轮询）
  useEffect(() => {
    let unsub: (() => void) | null = null
    let pollTimer: ReturnType<typeof setInterval> | null = null

    const fetchMubuStatus = async () => {
      try {
        const data = await request('/api/mubu/status') as MubuStatusInfo
        setMubuInfo({ doc_count: data.doc_count ?? 0, last_sync: data.last_sync ?? null })
        setMubuStatus(normalizeMubuStatus(data.status))
      } catch {
        // 后端尚未实现 /api/mubu/status 时静默失败
      }
    }
    fetchMubuStatus()

    // 优先通过 IPC 监听状态变化
    const api = (window.electronAPI as any)
    if (api?.on && typeof api.on === 'function') {
      try {
        const off = api.on('mubu:status-change', (status: string) => {
          setMubuStatus(normalizeMubuStatus(status))
          fetchMubuStatus()
        })
        if (typeof off === 'function') unsub = off
      } catch {
        // IPC 监听注册失败，降级轮询
      }
    }

    // IPC 不可用或注册失败时，降级为定时轮询
    if (!unsub) {
      pollTimer = setInterval(fetchMubuStatus, 15000)
    }

    return () => {
      if (unsub) { try { unsub() } catch {} }
      if (pollTimer) clearInterval(pollTimer)
    }
  }, [])

  const handleCheckUpdate = async () => {
    setUpdateChecking(true)
    try {
      await window.electronAPI?.checkForUpdates()
      if (checkUpdateTimerRef.current) clearTimeout(checkUpdateTimerRef.current)
      checkUpdateTimerRef.current = setTimeout(() => {
        setUpdateChecking(false)
        // 使用函数式更新避免闭包过期：只有当前状态确实是 idle 时才标记为最新
        setUpdateStatus(prev => prev === 'idle' ? 'up-to-date' : prev)
        checkUpdateTimerRef.current = null
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
        birthday: birthday,
        life_expectancy: lifeExpectancy,
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

  // 幕布文档接入：登录（使用 SSE 绕过 IPC 注册不稳定问题）
  const handleMubuLogin = async () => {
    setMubuLogging(true)
    try {
      await request('/api/mubu/login-request', { method: 'POST' })
      toast.success('已发起幕布登录')
    } catch (err: any) {
      toast.error(err?.message || '幕布登录失败')
    } finally {
      setMubuLogging(false)
    }
  }

  // 幕布文档接入：立即同步（使用 SSE 绕过 IPC 注册不稳定问题）
  const handleMubuSync = async () => {
    setMubuSyncing(true)
    setMubuStatus('syncing')
    try {
      await request('/api/mubu/sync/trigger', { method: 'POST' })
      toast.success('已触发幕布同步')
    } catch (err: any) {
      setMubuStatus('error')
      toast.error(err?.message || '幕布同步失败')
    } finally {
      setMubuSyncing(false)
    }
  }

  // 幕布文档接入：搜索已同步文档
  const handleMubuSearch = async (q: string) => {
    setMubuSearchQuery(q)
    if (!q.trim()) { setMubuSearchResults([]); return }
    setMubuSearching(true)
    try {
      const data = await request(`/api/mubu/search?q=${encodeURIComponent(q)}`)
      const results = Array.isArray(data)
        ? (data as MubuDoc[])
        : ((data as { results?: MubuDoc[] }).results || [])
      setMubuSearchResults(results)
    } catch {
      setMubuSearchResults([])
    } finally {
      setMubuSearching(false)
    }
  }

  // OPML 文件导入：上传至 /api/mubu/import-opml
  const handleOpmlImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setOpmlUploading(true)
    try {
      const res = await uploadOpmlFile(file)
      const imported = typeof res.imported === 'number' ? res.imported : 0
      const skipped = typeof res.skipped === 'number' ? res.skipped : 0
      toast.success(`OPML 导入完成：成功 ${imported} 条${skipped > 0 ? `，跳过 ${skipped} 条` : ''}`)
      // 导入后刷新记忆向量化状态
      fetchMemoryStatus()
    } catch (err: any) {
      toast.error(err?.message || 'OPML 导入失败')
    } finally {
      setOpmlUploading(false)
      // 清空 file input 以允许重复选择同一文件
      if (opmlFileInputRef.current) opmlFileInputRef.current.value = ''
    }
  }

  // 拉取记忆向量化状态（失败时静默处理）
  const fetchMemoryStatus = useCallback(async () => {
    try {
      const s = await getMemoryStatus()
      setMemoryStatus(s)
    } catch {
      // 后端未实现 /api/memory/status 时静默失败
      setMemoryStatus(null)
    }
  }, [])

  useEffect(() => {
    fetchMemoryStatus()
  }, [fetchMemoryStatus])

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

      {/* ─── 设置搜索 ──────────────────────────── */}
      <div className="relative">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="搜索设置项...（外观/采集/AI/日报/数据/日历/人生/Git/幕布/备份/导入/隐私/关于）"
          className="w-full px-3 py-2 pl-9 bg-cd-bg-secondary border border-cd-border rounded-lg text-sm text-cd-text focus:outline-none focus:ring-1 focus:ring-cd-green"
        />
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-cd-text-tertiary" />
      </div>

      {/* ─── 外观设置 ──────────────────────────── */}
      <section
        id="settings-section-外观"
        className={`card space-y-4 ${highlightedSection === '外观' ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Palette size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">外观设置</h2>
        </div>

        <div className="space-y-4">
          {/* 皮肤 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Palette size={14} className="text-cd-text-tertiary" />
              <span className="text-sm text-cd-text">皮肤</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {SKIN_PRESETS.map((skin, i) => {
                const isHanmo = skin.value === 'hanmo'
                const pBg = effectiveTheme === 'dark' ? (isHanmo ? '#1A1714' : '#121212') : (isHanmo ? '#F7F3ED' : '#FFFFFF')
                const pCard = effectiveTheme === 'dark' ? (isHanmo ? '#221E19' : '#1E1E1E') : (isHanmo ? '#FBF8F2' : '#FFFFFF')
                const pSidebar = effectiveTheme === 'dark' ? (isHanmo ? '#1E1A16' : '#181818') : (isHanmo ? '#F2EDE2' : '#FAFAFA')
                const pBorder = effectiveTheme === 'dark' ? (isHanmo ? '#3A332B' : '#333333') : (isHanmo ? '#D9CFB8' : '#E0E0E0')
                const pText = effectiveTheme === 'dark' ? (isHanmo ? '#F5F0E8' : '#FFFFFF') : (isHanmo ? '#2C2620' : '#1A1A1A')
                const pTextTert = effectiveTheme === 'dark' ? (isHanmo ? '#7A6F5F' : '#666666') : (isHanmo ? '#9A8B7A' : '#999999')
                return (
                  <button
                    key={i}
                    onClick={() => setSkinIndex(i)}
                    className={`relative rounded-xl border-2 p-2.5 transition-all duration-150 ${
                      i === skinIndex
                        ? 'border-cd-green'
                        : 'border-cd-border hover:border-cd-text-tertiary'
                    }`}
                  >
                    {/* 迷你预览 */}
                    <div
                      className="rounded-lg p-2 mb-2 h-14 flex gap-1.5 overflow-hidden"
                      style={{ background: pBg, border: `1px solid ${pBorder}` }}
                    >
                      {/* sidebar 缩略 */}
                      <div
                        className="w-3.5 rounded-sm flex flex-col gap-0.5 py-1 items-center"
                        style={{ background: pSidebar }}
                      >
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#7B68EE' }} />
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: pBorder }} />
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: pBorder }} />
                      </div>
                      {/* content 缩略 */}
                      <div className="flex-1 flex flex-col gap-1">
                        <div className="h-1 rounded-full" style={{ background: '#7B68EE', width: '60%' }} />
                        <div
                          className="flex-1 rounded-sm flex flex-col gap-0.5 p-1"
                          style={{ background: pCard, border: `1px solid ${pBorder}` }}
                        >
                          <div className="h-0.5 rounded-full" style={{ background: pText, width: '70%' }} />
                          <div className="h-0.5 rounded-full" style={{ background: pTextTert, width: '45%' }} />
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-sm font-medium text-cd-text">{skin.name}</span>
                        <p className="text-[10px] text-cd-text-tertiary">{skin.desc}</p>
                      </div>
                      {i === skinIndex && (
                        <CheckCircle size={14} className="text-cd-green shrink-0" />
                      )}
                    </div>
                  </button>
                )
              })}
            </div>
            <p className="text-[10px] text-cd-text-tertiary mt-1.5">
              切换整体色温与底纹风格，当前：{SKIN_PRESETS[skinIndex].name}
            </p>
          </div>

          {/* 深色模式 — P14-1：三态选择（亮色/深色/跟随系统） */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Moon size={14} className="text-cd-text-tertiary" />
              <span className="text-sm text-cd-text">主题模式</span>
            </div>
            <div className="flex items-center gap-1 bg-cd-bg-input rounded-lg p-0.5 border border-cd-border">
              {([
                { key: 'light', label: '亮色' },
                { key: 'dark', label: '深色' },
                { key: 'auto', label: '跟随系统' },
              ] as const).map(opt => (
                <button
                  key={opt.key}
                  onClick={() => setThemeExplicit(opt.key)}
                  className={`px-2.5 py-1 text-xs rounded-md transition ${
                    theme === opt.key
                      ? 'bg-cd-green text-white shadow-sm'
                      : 'text-cd-text-secondary hover:text-cd-text'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
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

          {/* 开机自启动 */}
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Rocket size={14} className="text-cd-text-tertiary" />
                <span className="text-sm text-cd-text">开机自启动</span>
              </div>
              <p className="text-[10px] text-cd-text-tertiary ml-[22px] mt-0.5">登录 Windows 后自动启动应用</p>
            </div>
            <ToggleSwitch checked={autoStart} onChange={handleToggleAutoStart} />
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
                    backgroundColor: effectiveTheme === 'dark' ? preset.dark : preset.light,
                    ringColor: effectiveTheme === 'dark' ? preset.dark : preset.light,
                    // @ts-ignore ring-offset-color not in CSSProperties
                    '--tw-ring-color': effectiveTheme === 'dark' ? preset.dark : preset.light,
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
              {customAccent && <span className="text-cd-green"> · 自定义色已启用</span>}
            </p>
            {/* P17-2: 自定义主色 */}
            <div className="flex items-center gap-2 mt-2">
              <input
                type="color"
                value={customAccent || (effectiveTheme === 'dark' ? ACCENT_PRESETS[accentIndex].dark : ACCENT_PRESETS[accentIndex].light)}
                onChange={(e) => setCustomAccent(e.target.value)}
                className="w-7 h-7 rounded cursor-pointer border border-cd-border bg-transparent"
                title="自定义主色"
              />
              <span className="text-[11px] text-cd-text-tertiary">自定义主色</span>
              {customAccent && (
                <button
                  onClick={() => setCustomAccent(null)}
                  className="text-[11px] text-cd-red hover:underline"
                >
                  重置
                </button>
              )}
            </div>
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
            {/* P17-2: 字号缩放 */}
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[11px] text-cd-text-tertiary w-10">字号</span>
              <input
                type="range"
                min={0.85}
                max={1.25}
                step={0.05}
                value={fontScale}
                onChange={(e) => setFontScale(parseFloat(e.target.value))}
                className="flex-1 max-w-[160px] accent-cd-green"
              />
              <span className="text-[11px] text-cd-text-secondary w-10 text-right">{Math.round(fontScale * 100)}%</span>
            </div>
          </div>

          {/* 圆角 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm text-cd-text">圆角</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {RADIUS_PRESETS.map((r, i) => (
                <button
                  key={i}
                  onClick={() => setRadiusIndex(i)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 border ${
                    i === radiusIndex
                      ? 'bg-cd-green-light text-cd-green border-cd-green/30'
                      : 'bg-cd-bg-secondary text-cd-text-secondary border-cd-border hover:bg-cd-hover'
                  }`}
                >
                  {r.name}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-cd-text-tertiary mt-1.5">调整卡片和按钮的圆角大小，实时生效</p>
          </div>

          {/* 阴影强度 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm text-cd-text">阴影强度</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {SHADOW_PRESETS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => setShadowIndex(i)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 border ${
                    i === shadowIndex
                      ? 'bg-cd-green-light text-cd-green border-cd-green/30'
                      : 'bg-cd-bg-secondary text-cd-text-secondary border-cd-border hover:bg-cd-hover'
                  }`}
                >
                  {s.name}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-cd-text-tertiary mt-1.5">调整界面阴影深度，实时生效</p>
          </div>

          {/* 界面整体透明度 */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm text-cd-text">界面整体透明度</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {OPACITY_PRESETS.map((o, i) => (
                <button
                  key={i}
                  onClick={() => setOpacityIndex(i)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150 border ${
                    i === opacityIndex
                      ? 'bg-cd-green-light text-cd-green border-cd-green/30'
                      : 'bg-cd-bg-secondary text-cd-text-secondary border-cd-border hover:bg-cd-hover'
                  }`}
                >
                  {o.name}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-cd-text-tertiary mt-1.5">调节毛玻璃背景透明度，实时生效</p>
          </div>

          {/* 侧边栏毛玻璃 */}
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <GlassWater size={14} className="text-cd-text-tertiary" />
                <span className="text-sm text-cd-text">侧边栏毛玻璃</span>
              </div>
              <p className="text-[10px] text-cd-text-tertiary ml-[22px] mt-0.5">半透明模糊效果，开启后可调节上方透明度</p>
            </div>
            <ToggleSwitch checked={sidebarTranslucent} onChange={setSidebarTranslucent} />
          </div>
        </div>
      </section>

      {/* ─── 采集设置 ────────────────────────── */}
      <section
        id="settings-section-采集"
        className={`card space-y-4 ${highlightedSection === '采集' ? 'ring-2 ring-cd-green' : ''}`}
      >
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
      <section
        id="settings-section-AI"
        className={`card space-y-4 ${highlightedSection === 'AI' ? 'ring-2 ring-cd-green' : ''}`}
      >
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

              {/* P19-4：本地小模型降级配置 */}
              <div className="pt-3 border-t border-cd-border">
                <div className="flex items-center gap-1.5 mb-2">
                  <Cpu size={12} className="text-cd-text-tertiary" />
                  <span className="text-xs font-semibold text-cd-text-secondary">本地小模型降级（Ollama）</span>
                </div>
                <LocalModelConfigPanel />
              </div>
            </>
          )}
        </div>
      </section>

      {/* ─── 日报自定义指令 ─────────────────────── */}
      <section
        id="settings-section-日报"
        className={`card space-y-4 ${highlightedSection === '日报' ? 'ring-2 ring-cd-green' : ''}`}
      >
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

        {/* 每日定时生成日报 */}
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-cd-border">
          <div>
            <div className="text-xs text-cd-text-secondary">每日定时生成日报</div>
            <div className="text-[10px] text-cd-text-tertiary mt-0.5">在指定时间自动基于当日工作记录生成日报</div>
          </div>
          <div className="flex items-center gap-3">
            {settings.auto_daily_report && (
              <select
                value={settings.auto_daily_report_hour ?? 18}
                onChange={(e) => updateSetting('auto_daily_report_hour', parseInt(e.target.value))}
                className="bg-cd-bg-secondary text-cd-text border border-cd-border rounded px-2 py-1 text-xs"
              >
                {Array.from({ length: 24 }, (_, i) => (
                  <option key={i} value={i}>{String(i).padStart(2, '0')}:00</option>
                ))}
              </select>
            )}
            <button
              onClick={() => updateSetting('auto_daily_report', !settings.auto_daily_report)}
              className={`relative w-10 h-5 rounded-full transition-colors ${
                settings.auto_daily_report ? 'bg-cd-green' : 'bg-cd-bg-tertiary'
              }`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                settings.auto_daily_report ? 'left-5.5' : 'left-0.5'
              }`} />
            </button>
          </div>
        </div>
      </section>

      {/* ─── 数据导出 ──────────────────────────── */}
      <section
        id="settings-section-数据"
        className={`card space-y-4 ${highlightedSection === '数据' ? 'ring-2 ring-cd-green' : ''}`}
      >
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
            onClick={async (e) => { e.preventDefault(); try { await downloadExportActivities(exportStart, exportEnd) } catch (err) { toast.error('导出失败') } }}
            href="#"
            download
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer"
          >
            <Download size={12} />
            导出活动记录
          </a>
          <a
            onClick={async (e) => { e.preventDefault(); try { await downloadExportAppUsage(exportStart, exportEnd) } catch (err) { toast.error('导出失败') } }}
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

      {/* ─── 外部日历集成（P19-1） ──────────────────────────── */}
      <section
        id="settings-section-日历"
        className={`card space-y-4 ${highlightedSection === '日历' ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Calendar size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">外部日历集成</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          订阅 ICS 日历源（Google Calendar / Outlook / 飞书等），自动识别会议时段，避免在会议期间触发专注提醒。
        </div>
        <CalendarSubscriptionManager />
      </section>

      {/* ─── 人生配置（QuantLife 灵感） ──────────────────────────── */}
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Heart size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">人生配置</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          设置生日和预期寿命，开启「人生进度」可视化 — 让每一天都有坐标感。
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">生日</label>
            <input
              type="date"
              value={birthday}
              onChange={(e) => setBirthday(e.target.value)}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">预期寿命（岁）</label>
            <input
              type="number"
              value={lifeExpectancy}
              onChange={(e) => setLifeExpectancy(Number(e.target.value))}
              min={1}
              max={150}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          人生进度条将显示在首页顶部信息栏，让你直观感受时间流逝。
        </div>
      </section>

      {/* ─── Git 仓库集成（P19-2） ──────────────────────────── */}
      <section
        id="settings-section-Git"
        className={`card space-y-4 ${highlightedSection === 'Git' ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <GitBranch size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">Git 仓库集成</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          添加本地 git 仓库路径，日报将自动聚合提交记录与代码增删行数，生成开发者专属代码产出统计。
        </div>
        <GitRepoManager />
      </section>

      {/* ─── 幕布文档接入 ──────────────────────────── */}
      <section
        id="settings-section-幕布"
        className={`card space-y-4 ${highlightedSection === '幕布' ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Cloud size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">幕布文档接入</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          登录幕布账号后，可将文档同步至本地，便于日报与活动关联引用。
        </div>

        {/* 同步状态 + 文档统计 */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs text-cd-text-secondary">同步状态</span>
            <span className={`text-xs px-2.5 py-0.5 rounded-full ${MUBU_STATUS_META[mubuStatus].className}`}>
              {MUBU_STATUS_META[mubuStatus].label}
            </span>
          </div>
          <div className="text-xs text-cd-text-tertiary">
            {mubuInfo ? (
              <>
                {mubuInfo.doc_count} 篇文档
                {mubuInfo.last_sync && (
                  <> · 最近同步 {dayjs(mubuInfo.last_sync).format('MM-DD HH:mm')}</>
                )}
              </>
            ) : '—'}
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleMubuLogin}
            disabled={mubuLogging}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
          >
            {mubuLogging ? <Loader2 size={12} className="animate-spin" /> : <Cloud size={12} />}
            {mubuLogging ? '登录中...' : '登录幕布'}
          </button>
          <button
            onClick={handleMubuSync}
            disabled={mubuSyncing}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-green text-white hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {mubuSyncing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            {mubuSyncing ? '同步中...' : '立即同步'}
          </button>
        </div>

        {/* 搜索已同步文档 */}
        <div>
          <label className="text-xs text-cd-text-secondary block mb-1">搜索已同步文档</label>
          <div className="relative">
            <input
              type="text"
              value={mubuSearchQuery}
              onChange={(e) => handleMubuSearch(e.target.value)}
              placeholder="输入关键词搜索..."
              className="w-full px-3 py-1.5 pl-9 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
            {mubuSearching ? (
              <Loader2 size={14} className="absolute left-2.5 top-2 animate-spin text-cd-text-tertiary" />
            ) : (
              <Search size={14} className="absolute left-2.5 top-2 text-cd-text-tertiary" />
            )}
          </div>
          {mubuSearchResults.length > 0 && (
            <ul className="mt-2 space-y-1 max-h-48 overflow-y-auto">
              {mubuSearchResults.map((doc) => {
                const inner = (
                  <>
                    <span className="truncate text-cd-text">{doc.title}</span>
                    {doc.updated_at && (
                      <span className="text-[10px] text-cd-text-tertiary ml-2 shrink-0">
                        {dayjs(doc.updated_at).format('MM-DD')}
                      </span>
                    )}
                  </>
                )
                return (
                  <li key={doc.id}>
                    {doc.url ? (
                      <a
                        href={doc.url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs bg-cd-bg-secondary hover:bg-cd-hover transition-colors"
                      >
                        {inner}
                      </a>
                    ) : (
                      <div className="flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs bg-cd-bg-secondary">
                        {inner}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          {mubuSearchQuery.trim() && !mubuSearching && mubuSearchResults.length === 0 && (
            <p className="text-[10px] text-cd-text-tertiary mt-1.5">无匹配文档</p>
          )}
        </div>

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 首次使用请点击「登录幕布」完成账号授权</p>
          <p>• Cookie 失效时请重新登录以恢复同步</p>
        </div>

        {/* ── OPML 导入 & 记忆向量化 ── */}
        <div className="pt-3 border-t border-cd-border space-y-3">
          <div className="flex items-center gap-1.5">
            <FileUp size={12} className="text-cd-text-tertiary" />
            <span className="text-xs font-semibold text-cd-text-secondary">OPML 导入 & 记忆向量化</span>
          </div>

          {/* OPML 文件导入 */}
          <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border cursor-pointer disabled:opacity-50">
              {opmlUploading ? <Loader2 size={12} className="animate-spin" /> : <FileUp size={12} />}
              {opmlUploading ? '导入中...' : '导入 OPML 文件'}
              <input
                ref={opmlFileInputRef}
                type="file"
                accept=".opml,.xml"
                onChange={handleOpmlImport}
                className="hidden"
                disabled={opmlUploading}
              />
            </label>
            <a
              href="#/memory"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-cd-green hover:bg-cd-green-light transition-colors"
            >
              <Brain size={12} />
              管理记忆
            </a>
          </div>

          {/* 向量化状态显示 */}
          {memoryStatus ? (
            <div className="bg-cd-bg-secondary rounded-lg p-3 border border-cd-border space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-cd-text-secondary">向量化进度</span>
                <span className="font-medium text-cd-text">
                  {memoryStatus.indexed ?? 0} / {memoryStatus.total ?? 0}
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-cd-bg overflow-hidden">
                <div
                  className="h-full rounded-full bg-cd-green transition-all duration-500"
                  style={{
                    width: `${Math.min(
                      100,
                      memoryStatus.total > 0
                        ? Math.round(((memoryStatus.indexed ?? 0) / memoryStatus.total) * 100)
                        : 0,
                    )}%`,
                  }}
                />
              </div>
              {(memoryStatus.pending ?? 0) > 0 && (
                <div className="text-[10px] text-cd-text-tertiary">
                  待索引 {memoryStatus.pending} 条
                  {memoryStatus.indexing && (
                    <span className="ml-2 text-cd-green flex items-center gap-1 inline-flex">
                      <Loader2 size={9} className="animate-spin" />
                      索引中
                    </span>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="text-[10px] text-cd-text-tertiary">
              记忆系统未启用或后端暂未就绪
            </div>
          )}

          <div className="text-[10px] text-cd-text-tertiary space-y-1">
            <p>• 支持从其他笔记软件导出的 OPML 文件批量导入文档大纲</p>
            <p>• 导入的文档会自动抽取事实并写入记忆库，供语义检索使用</p>
          </div>
        </div>
      </section>

      {/* ─── 数据备份与恢复 ────────────────────── */}
      <section
        id="settings-section-备份"
        className={`card space-y-4 ${highlightedSection === '备份' ? 'ring-2 ring-cd-green' : ''}`}
      >
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
            onClick={async (e) => { e.preventDefault(); try { await downloadBackup() } catch (err) { toast.error('备份下载失败') } }}
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

      {/* ─── 数据迁移导入 ────────────────────── */}
      <DataImportSection toast={toast} highlighted={highlightedSection === '导入'} />

      {/* ─── 隐私说明 ──────────────────────────── */}
      <section
        id="settings-section-隐私"
        className={`card space-y-4 ${highlightedSection === '隐私' ? 'ring-2 ring-cd-green' : ''}`}
      >
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">隐私保护</h2>
        </div>

        {/* 应用级隐私锁 */}
        <AppLockSettings />

        <div className="text-xs text-cd-text-tertiary space-y-1">
          <p>• 截图在 AI 分析完成后会自动删除，不会保存到磁盘</p>
          <p>• 所有数据仅保存于本地 SQLite 数据库，不上传任何服务器</p>
          <p>• AI 分析时自动脱敏：隐藏人名、手机号、金额等敏感信息</p>
          <p>• 排除列表中的应用不会被截图和记录</p>
          <p>• API Key 使用 Windows 系统加密存储 (DPAPI)，不以明文保存</p>
        </div>
      </section>

      {/* ─── 关于与更新 ────────────────────────── */}
      <section
        id="settings-section-关于"
        className={`card space-y-4 ${highlightedSection === '关于' ? 'ring-2 ring-cd-green' : ''}`}
      >
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

// ── 数据迁移导入组件 ──
function DataImportSection({ toast, highlighted }: { toast: ReturnType<typeof useToast>; highlighted?: boolean }) {
  const [source, setSource] = useState<'fanqie_todo' | 'xiaohei_report' | 'goalday' | 'generic_csv'>('fanqie_todo')
  const [format, setFormat] = useState<'json' | 'csv'>('csv')
  const [rawText, setRawText] = useState('')
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [preview, setPreview] = useState<{ total_rows: number; detected_type: string; sample: Array<Record<string, unknown>> } | null>(null)
  const [result, setResult] = useState<{ imported: number; skipped: number; errors: string[] } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => setRawText(String(reader.result || ''))
    reader.readAsText(file)
  }

  const handlePreview = async () => {
    if (!rawText.trim()) { toast.error('请先粘贴或上传数据'); return }
    setPreviewing(true)
    setResult(null)
    try {
      const res = await previewImport(source, format, rawText)
      setPreview({ total_rows: res.total_rows, detected_type: res.detected_type, sample: res.sample })
      toast.success(`解析成功：${res.total_rows} 行，检测为 ${res.detected_type}`)
    } catch (err: any) {
      toast.error(err.message || '预览失败')
      setPreview(null)
    }
    setPreviewing(false)
  }

  const handleImport = async () => {
    if (!rawText.trim()) return
    setImporting(true)
    try {
      const res = await executeImport(source, format, rawText)
      setResult({ imported: res.imported, skipped: res.skipped, errors: res.errors })
      if (res.imported > 0) {
        toast.success(`导入完成：成功 ${res.imported} 条，跳过 ${res.skipped} 条`)
      } else {
        toast.error('无数据被导入，请检查格式')
      }
    } catch (err: any) {
      toast.error(err.message || '导入失败')
    }
    setImporting(false)
  }

  const SOURCES = [
    { value: 'fanqie_todo', label: '番茄TODO', desc: '任务/番茄数据' },
    { value: 'xiaohei_report', label: '小黑日报', desc: '历史日报' },
    { value: 'goalday', label: 'GoalDay', desc: '目标/日记' },
    { value: 'generic_csv', label: '通用CSV', desc: '自定义格式' },
  ] as const

  return (
    <section id="settings-section-导入" className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}>
      <div className="flex items-center gap-2">
        <Upload size={16} className="text-cd-accent" />
        <h2 className="text-sm font-semibold text-cd-text">数据迁移导入</h2>
      </div>
      <p className="text-xs text-cd-text-tertiary">
        从番茄TODO/小黑日报/GoalDay 等竞品导入数据，无缝迁移至 ChallengeDaily
      </p>

      {/* 数据源选择 */}
      <div className="grid grid-cols-4 gap-2">
        {SOURCES.map(s => (
          <button key={s.value} onClick={() => setSource(s.value)}
            className={`px-3 py-2 rounded-lg text-xs transition border ${
              source === s.value
                ? 'bg-cd-accent/20 text-cd-accent border-cd-accent/30'
                : 'bg-cd-bg-secondary text-cd-text-secondary border-transparent hover:bg-cd-hover'
            }`}>
            <div className="font-medium">{s.label}</div>
            <div className="text-[10px] opacity-70">{s.desc}</div>
          </button>
        ))}
      </div>

      {/* 格式选择 */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-cd-text-secondary">格式：</span>
        {(['csv', 'json'] as const).map(f => (
          <button key={f} onClick={() => setFormat(f)}
            className={`px-3 py-1 rounded text-xs transition ${
              format === f ? 'bg-cd-accent/20 text-cd-accent' : 'bg-cd-bg-secondary text-cd-text-secondary'
            }`}>
            {f.toUpperCase()}
          </button>
        ))}
        <label className="ml-auto cursor-pointer text-xs text-cd-accent hover:underline">
          <input ref={fileRef} type="file" accept=".csv,.json,.txt" onChange={handleFile} className="hidden" />
          📁 上传文件
        </label>
      </div>

      {/* 数据输入区 */}
      <textarea
        value={rawText}
        onChange={e => { setRawText(e.target.value); setPreview(null); setResult(null) }}
        rows={5}
        placeholder={`粘贴 ${format.toUpperCase()} 数据，或点击"上传文件"导入...\n\n示例 CSV:\ntitle,target_min,estimated_pomodoros,category\n完成项目A,25,2,开发\n阅读技术文档,25,1,学习`}
        className="w-full px-3 py-2 rounded-lg bg-cd-bg-input border border-cd-border text-xs font-mono text-cd-text focus:border-cd-accent outline-none resize-y"
      />

      {/* 操作按钮 */}
      <div className="flex gap-2">
        <button onClick={handlePreview} disabled={!rawText || previewing}
          className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs bg-cd-bg-secondary text-cd-text hover:bg-cd-hover disabled:opacity-40 transition">
          {previewing ? '解析中...' : '🔍 预览解析'}
        </button>
        <button onClick={handleImport} disabled={!rawText || importing}
          className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs bg-cd-accent text-white hover:opacity-90 disabled:opacity-40 transition">
          {importing ? '导入中...' : '⬆ 执行导入'}
        </button>
      </div>

      {/* 预览结果 */}
      {preview && (
        <div className="bg-cd-bg-secondary rounded-lg p-3 border border-cd-border">
          <div className="text-xs text-cd-text mb-2">
            ✅ 解析 <span className="font-bold text-cd-accent">{preview.total_rows}</span> 行 ·
            检测类型：<span className="font-bold text-cd-green">{preview.detected_type}</span>
          </div>
          {preview.sample.length > 0 && (
            <details className="text-[10px] text-cd-text-tertiary">
              <summary className="cursor-pointer hover:text-cd-text">查看样本（前3行）</summary>
              <pre className="mt-1 p-2 bg-cd-bg rounded overflow-x-auto">{JSON.stringify(preview.sample, null, 2)}</pre>
            </details>
          )}
        </div>
      )}

      {/* 导入结果 */}
      {result && (
        <div className="bg-cd-bg-secondary rounded-lg p-3 border border-cd-border">
          <div className="text-xs text-cd-text">
            导入结果：✅ 成功 <span className="font-bold text-cd-green">{result.imported}</span> 条 ·
            ⏭ 跳过 <span className="font-bold text-cd-text-tertiary">{result.skipped}</span> 条
          </div>
          {result.errors.length > 0 && (
            <details className="mt-2 text-[10px] text-red-400">
              <summary className="cursor-pointer">错误详情（{result.errors.length}条）</summary>
              <ul className="mt-1 space-y-0.5 max-h-32 overflow-y-auto">
                {result.errors.map((e, i) => <li key={i}>{e}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  )
}
