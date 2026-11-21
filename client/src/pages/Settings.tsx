import { useState, useEffect, useCallback, useRef } from 'react'
import { getStatus, getSettings, updateSettings, testAiConnection, downloadExportActivities, downloadExportAppUsage, getBackupInfo, downloadBackup, restoreBackup, previewImport, executeImport, request, getMemoryStatus, uploadOpmlFile, type CollectorStatus, type BackendSettings, type MemoryStatus } from '../api/client'
import { ToggleSwitch, useTimeout, useAsyncData, ApiErrorDisplay } from '../components/shared'
import { useToast } from '../components/Toast'
import { useTheme, ACCENT_PRESETS, FONT_PRESETS, RADIUS_PRESETS, SHADOW_PRESETS, OPACITY_PRESETS, SKIN_PRESETS } from '../components/ThemeContext'
import { AppLockSettings } from '../components/AppLock'
import { Shield, Bot, Eye, EyeOff, Server, FileText, ListFilter, Download, Loader2, CheckCircle, XCircle, RotateCcw, Database, Upload, HardDrive, Info, RefreshCw, Palette, Type, GlassWater, Moon, Cat, Rocket, Search, Calendar, GitBranch, Cpu, Cloud, Brain, FileUp, Heart, ChevronDown, ChevronRight, UserRound } from 'lucide-react'
import { getUserProfile, saveUserProfile, type UserProfileData } from '../api/userProfile'
import dayjs from 'dayjs'
import CalendarSubscriptionManager from '../components/CalendarSubscriptionManager'
import GitRepoManager from '../components/GitRepoManager'
import LocalModelConfigPanel from '../components/LocalModelConfig'

import { AppearanceSection } from './settings/sections/AppearanceSection'
import { CollectSection } from './settings/sections/CollectSection'
import { FocusSection } from './settings/sections/FocusSection'
import { ExcludeAppsSection } from './settings/sections/ExcludeAppsSection'
import { DailyReportSection } from './settings/sections/DailyReportSection'
import { DataExportSection } from './settings/sections/DataExportSection'
import { CalendarSection } from './settings/sections/CalendarSection'
import { LifeSection } from './settings/sections/LifeSection'
import { ProfileSection } from './settings/sections/ProfileSection'
import { GitSection } from './settings/sections/GitSection'
import { IntegrationSection } from './settings/sections/IntegrationSection'
import { MubuSection } from './settings/sections/MubuSection'
import { BackupSection } from './settings/sections/BackupSection'
import { PrivacySection } from './settings/sections/PrivacySection'
import { AboutSection } from './settings/sections/AboutSection'
import { DataImportSection } from './settings/sections/DataImportSection'

// ── 幕布文档接入 ──
type MubuStatus = 'idle' | 'syncing' | 'synced' | 'cookie_invalid' | 'error' | 'unknown'

interface MubuStatusInfo {
  doc_count: number
  last_sync: string | null
  status?: string
  cookie_valid?: boolean
  message?: string
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
  const [focusStrictness, setFocusStrictness] = useState<'relaxed' | 'standard' | 'strict'>('standard')
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
  // 每日自动生成日报
  const [autoDailyReport, setAutoDailyReport] = useState(false)
  const [autoDailyReportHour, setAutoDailyReportHour] = useState(18)
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
  // 集成开关（遥测 / MCP）
  const [telemetryEnabled, setTelemetryEnabled] = useState(false)
  const [mcpEnabled, setMcpEnabled] = useState(false)
  const [telemetryEvents, setTelemetryEvents] = useState<Array<{ event: string; data: Record<string, unknown>; time: number }>>([])
  const [integrationBusy, setIntegrationBusy] = useState<'telemetry' | 'mcp' | false>(false)
  // 企微日报群机器人（B29）
  const [wecomWebhook, setWecomWebhook] = useState('')
  const [wecomConfigured, setWecomConfigured] = useState(false)
  const [wecomBusy, setWecomBusy] = useState(false)
  // 人生配置
  const [birthday, setBirthday] = useState('')
  const [lifeExpectancy, setLifeExpectancy] = useState(80)
  // 我的资料（用户画像）
  const [profileOpen, setProfileOpen] = useState(false)
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileForm, setProfileForm] = useState<UserProfileData>({
    nickname: '', role: '', company: '', current_project: '',
    responsibilities: '', industry: '', work_years: null,
    goals: '', report_style: '',
  })

  const handleSearch = (query: string) => {
    setSearchQuery(query)
    if (!query.trim()) { setHighlightedSection(''); return }
    // 简单匹配：遍历设置分区标题
    const sections = ['外观', '采集', 'AI', '日报', '数据', '日历', '人生', 'Git', '集成', '幕布', '备份', '导入', '隐私', '关于']
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
    setFocusStrictness((settings as any).focus_strictness || 'standard')
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
    // 每日自动生成日报
    setAutoDailyReport(settings.auto_daily_report ?? false)
    setAutoDailyReportHour(settings.auto_daily_report_hour ?? 18)
    // 集成开关
    setTelemetryEnabled(!!(settings as any).telemetry_enabled)
    setMcpEnabled(!!(settings as any).mcp_enabled)
  }, [initialData])

  // 企微日报配置：读取真实通道配置，未配置时明确显示“未配置”
  const loadWecomConfig = useCallback(async () => {
    try {
      const res = await request('/api/report-channels/config') as { channels?: Array<{ type?: string; config?: { webhook_url?: string; webhook?: string } }> }
      const channel = (res.channels || []).find((item) => item.type === 'wecom_report')
      const url = String(channel?.config?.webhook_url || channel?.config?.webhook || '').trim()
      setWecomWebhook(url)
      setWecomConfigured(!!url)
    } catch {
      setWecomWebhook('')
      setWecomConfigured(false)
    }
  }, [])

  useEffect(() => {
    void loadWecomConfig()
  }, [loadWecomConfig])

  const handleSaveWecom = async () => {
    const url = wecomWebhook.trim()
    if (!url) {
      toast.error('请先填写企微群机器人 webhook')
      return
    }
    if (!url.startsWith('https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=')) {
      toast.error('webhook 必须是企业微信群机器人地址')
      return
    }
    setWecomBusy(true)
    try {
      const result = await request('/api/report-channels/test', {
        method: 'POST',
        body: JSON.stringify({ type: 'wecom_report', config: { webhook_url: url } }),
      }) as { success?: boolean; message?: string }
      if (!result.success) {
        toast.error(`企微连接测试失败：${result.message || '未知错误'}`)
        await loadWecomConfig()
        return
      }
      const current = await request('/api/report-channels/config') as { channels?: Array<{ type?: string; config?: Record<string, unknown> }> }
      const channels = (current.channels || []).filter((item) => item.type !== 'wecom_report')
      channels.push({ type: 'wecom_report', config: { webhook_url: url } })
      await request('/api/report-channels/config', {
        method: 'POST',
        body: JSON.stringify({ channels }),
      })
      setWecomConfigured(true)
      toast.success('企微日报已保存，连接测试已真实发送')
    } catch {
      toast.error('保存或测试企微日报配置失败')
      await loadWecomConfig()
    } finally {
      setWecomBusy(false)
    }
  }

  // 获取应用版本 & 开机自启动状态
  useEffect(() => {
    if (window.electronAPI?.getAppVersion) {
      window.electronAPI.getAppVersion().then(v => setAppVersion(v))
    }
    if (window.electronAPI?.getAutoStart) {
      window.electronAPI.getAutoStart().then(v => setAutoStart(v))
    }
  }, [])

  // 我的资料：加载用户画像
  useEffect(() => {
    getUserProfile()
      .then((p) => {
        setProfileForm({
          nickname: p.nickname || '',
          role: p.role || '',
          company: p.company || '',
          current_project: p.current_project || '',
          responsibilities: p.responsibilities || '',
          industry: p.industry || '',
          work_years: p.work_years ?? null,
          goals: p.goals || '',
          report_style: p.report_style || '',
        })
      })
      .catch(() => { /* 后端未就绪时静默 */ })
  }, [])

  const handleSaveProfile = async () => {
    setProfileSaving(true)
    try {
      await saveUserProfile(profileForm)
      toast.success('我的资料已保存')
    } catch {
      toast.error('保存我的资料失败')
    } finally {
      setProfileSaving(false)
    }
  }

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
        setMubuInfo({
          doc_count: data.doc_count ?? 0,
          last_sync: data.last_sync ?? null,
          status: data.status,
          cookie_valid: data.cookie_valid,
          message: data.message,
        })
        setMubuStatus(data.cookie_valid === false ? 'cookie_invalid' : normalizeMubuStatus(data.status))
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
        focus_strictness: focusStrictness,
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
        auto_daily_report: autoDailyReport,
        auto_daily_report_hour: autoDailyReportHour,
        telemetry_enabled: telemetryEnabled,
        mcp_enabled: mcpEnabled,
      } as Partial<BackendSettings>
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

  const refreshTelemetryEvents = useCallback(async () => {
    try {
      const res = await request('/api/enterprise/telemetry/events?limit=20') as { enabled?: boolean; events?: Array<{ event: string; data: Record<string, unknown>; time: number }> }
      setTelemetryEvents(Array.isArray(res.events) ? res.events.slice(-20).reverse() : [])
    } catch {
      setTelemetryEvents([])
    }
  }, [])

  const handleIntegrationToggle = async (key: 'telemetry_enabled' | 'mcp_enabled', value: boolean) => {
    const kind = key === 'telemetry_enabled' ? 'telemetry' : 'mcp'
    setIntegrationBusy(kind)
    try {
      await updateSettings({ [key]: value } as Partial<BackendSettings>)
      if (key === 'telemetry_enabled') {
        setTelemetryEnabled(value)
        if (value) await refreshTelemetryEvents()
      } else {
        setMcpEnabled(value)
      }
      toast.success(key === 'telemetry_enabled'
        ? (value ? '已开启本地遥测（仅写本机，不上传）' : '已关闭本地遥测')
        : (value ? '已开启 MCP 服务开关' : '已关闭 MCP 服务开关'))
    } catch {
      toast.error('保存集成开关失败')
    } finally {
      setIntegrationBusy(false)
    }
  }

  const handleClearTelemetry = async () => {
    try {
      await request('/api/enterprise/telemetry/clear', { method: 'POST' })
      setTelemetryEvents([])
      toast.success('已清空本地遥测事件')
    } catch {
      toast.error('清空遥测事件失败')
    }
  }

  useEffect(() => {
    if (telemetryEnabled) refreshTelemetryEvents()
  }, [telemetryEnabled, refreshTelemetryEvents])

  const handleResetDefaults = async () => {
    try {
      const defaultSettings: Partial<BackendSettings> = {
        exclude_apps: [],
    focus_strictness: 'standard',
        screenshot_interval_sec: 60,
        work_start_hour: 9,
        work_end_hour: 18,
        custom_report_instructions: '',
        ai_base_url: 'https://open.bigmodel.cn/api/paas/v4',
        ai_vision_model: 'glm-4v-flash',
        ai_text_model: 'glm-4-flash',
        ai_enabled: false,
        telemetry_enabled: false,
        mcp_enabled: false,
      }
      await updateSettings(defaultSettings)
      // 重置本地状态
      setExcludeApps(defaultSettings.exclude_apps!.join(', '))
    setFocusStrictness('standard')
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
      setTelemetryEnabled(false)
      setMcpEnabled(false)
      setTelemetryEvents([])
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
      e.target.value = ''
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
    if (mubuStatus === 'cookie_invalid') {
      toast.warning('幕布 Cookie 已失效，请先重新登录再同步')
      return
    }
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
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border"
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
          className="w-full px-3 py-2 pl-9 bg-cd-bg-secondary border border-cd-border rounded-2xl text-sm text-cd-text focus:outline-none focus:ring-1 focus:ring-cd-green"
        />
        <Search className="absolute left-3 top-2.5 w-4 h-4 text-cd-text-tertiary" />
      </div>

      {/* ─── 外观设置 ──────────────────────────── */}
      <AppearanceSection highlighted={highlightedSection === '外观'} petVisible={petVisible} autoStart={autoStart} handleTogglePet={handleTogglePet} handleToggleAutoStart={handleToggleAutoStart} />

      {/* ─── 采集设置 ────────────────────────── */}
      <CollectSection highlighted={highlightedSection === '采集'} interval={interval} setInterval_={setInterval_} workStart={workStart} setWorkStart={setWorkStart} workEnd={workEnd} setWorkEnd={setWorkEnd} status={status} />

      {/* ─── 专注监督 ──────────────────────────── */}
      <FocusSection focusStrictness={focusStrictness} setFocusStrictness={setFocusStrictness} />

      {/* ─── 排除应用 ──────────────────────────── */}
      <ExcludeAppsSection excludeApps={excludeApps} setExcludeApps={setExcludeApps} />

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
                  className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
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
                    className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                  />
                </div>
                <div>
                  <label className="text-xs text-cd-text-secondary block mb-1">文本模型（Text）</label>
                  <input
                    type="text"
                    value={apiTextModel}
                    onChange={(e) => setApiTextModel(e.target.value)}
                    placeholder="glm-4-flash"
                    className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">API Key</label>
                {apiKeySet && !showKeyInput ? (
                  <div className="flex items-center justify-between bg-cd-green-light border border-cd-green/20 rounded-2xl px-3 py-2">
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
                      className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 pr-9 text-sm focus:outline-none focus:border-cd-green transition-colors"
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
                  className="flex items-center gap-2 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors disabled:opacity-40 border border-cd-border"
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
                  className="flex items-center gap-2 px-4 py-1.5 rounded-2xl text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors disabled:opacity-40 border border-cd-border"
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
      <DailyReportSection highlighted={highlightedSection === '日报'} customInstr={customInstr} setCustomInstr={setCustomInstr} autoDailyReport={autoDailyReport} setAutoDailyReport={setAutoDailyReport} autoDailyReportHour={autoDailyReportHour} setAutoDailyReportHour={setAutoDailyReportHour} />

      {/* ─── 数据导出 ──────────────────────────── */}
      <DataExportSection highlighted={highlightedSection === '数据'} exportStart={exportStart} setExportStart={setExportStart} exportEnd={exportEnd} setExportEnd={setExportEnd} toast={toast} />

      {/* ─── 外部日历集成（P19-1） ──────────────────────────── */}
      <CalendarSection highlighted={highlightedSection === '日历'} />

      {/* ─── 人生配置（QuantLife 灵感） ──────────────────────────── */}
      <LifeSection birthday={birthday} setBirthday={setBirthday} lifeExpectancy={lifeExpectancy} setLifeExpectancy={setLifeExpectancy} />

      {/* ─── 我的资料（用户画像） ──────────────────────────── */}
      <ProfileSection profileOpen={profileOpen} setProfileOpen={setProfileOpen} profileForm={profileForm} setProfileForm={setProfileForm} profileSaving={profileSaving} handleSaveProfile={handleSaveProfile} />

      {/* ─── Git 仓库集成（P19-2） ──────────────────────────── */}
      <GitSection highlighted={highlightedSection === 'Git'} />

      {/* ─── 集成开关（B26/B27） ──────────────────────────── */}
      <IntegrationSection highlighted={highlightedSection === '集成'} telemetryEnabled={telemetryEnabled} integrationBusy={integrationBusy} handleIntegrationToggle={handleIntegrationToggle} telemetryEvents={telemetryEvents} handleClearTelemetry={handleClearTelemetry} mcpEnabled={mcpEnabled} wecomConfigured={wecomConfigured} wecomWebhook={wecomWebhook} setWecomWebhook={setWecomWebhook} handleSaveWecom={handleSaveWecom} wecomBusy={wecomBusy} />
      <MubuSection highlighted={highlightedSection === '幕布'} mubuStatus={mubuStatus} mubuInfo={mubuInfo} mubuLogging={mubuLogging} mubuSyncing={mubuSyncing} mubuSearchQuery={mubuSearchQuery} mubuSearching={mubuSearching} mubuSearchResults={mubuSearchResults} handleMubuLogin={handleMubuLogin} handleMubuSync={handleMubuSync} handleMubuSearch={handleMubuSearch} opmlUploading={opmlUploading} opmlFileInputRef={opmlFileInputRef} handleOpmlImport={handleOpmlImport} memoryStatus={memoryStatus} />

      {/* ─── 数据备份与恢复 ────────────────────── */}
      <BackupSection highlighted={highlightedSection === '备份'} backupInfo={backupInfo} restoring={restoring} handleRestore={handleRestore} toast={toast} />

      {/* ─── 数据迁移导入 ────────────────────── */}
      <DataImportSection toast={toast} highlighted={highlightedSection === '导入'} />

      {/* ─── 隐私说明 ──────────────────────────── */}
      <PrivacySection highlighted={highlightedSection === '隐私'} />

      {/* ─── 关于与更新 ────────────────────────── */}
      <AboutSection highlighted={highlightedSection === '关于'} appVersion={appVersion} updateStatus={updateStatus} updateChecking={updateChecking} handleCheckUpdate={handleCheckUpdate} />

      {/* ─── 保存按钮 ─────────────────────────── */}
      <button
        onClick={handleSave}
        className={`w-full py-2.5 rounded-2xl text-sm font-medium transition-colors ${
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