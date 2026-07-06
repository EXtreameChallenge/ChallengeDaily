import { useState, useEffect, useCallback } from 'react'
import {
  getProfile, saveProfile, addCorrection, deleteCorrection,
  getDailyProfile, generateDailyProfile,
  CATEGORIES,
  type ProfileData, type UserCorrection, type DailyProfile,
} from '../api/client'
import {
  User, Briefcase, Wrench, Trash2, Plus, RefreshCw, ChevronDown, ChevronUp,
  Loader2, Sparkles, Calendar, Brain, Save,
} from 'lucide-react'
import dayjs from 'dayjs'

/** 安全解析 JSON 字符串 */
function parseJsonSafe<T>(s: string | undefined | null, fallback: T): T {
  if (!s) return fallback
  try { return JSON.parse(s) } catch { return fallback }
}

export default function Profile() {
  const [data, setData] = useState<ProfileData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ text: string; type: 'ok' | 'err' } | null>(null)

  // ─── 画像编辑状态 ───
  const [roleDesc, setRoleDesc] = useState('')
  const [workStyle, setWorkStyle] = useState('')
  const [habits, setHabits] = useState<Record<string, string>>({})
  const [appOverrides, setAppOverrides] = useState<Record<string, string>>({})

  // ─── 纠正记录编辑 ───
  const [newCorrApp, setNewCorrApp] = useState('')
  const [newCorrCategory, setNewCorrCategory] = useState('')
  const [newCorrDesc, setNewCorrDesc] = useState('')

  // ─── 日画像 ───
  const [selectedDate, setSelectedDate] = useState(dayjs().format('YYYY-MM-DD'))
  const [dailyProfile, setDailyProfile] = useState<DailyProfile | null>(null)
  const [dailyLoading, setDailyLoading] = useState(false)
  const [dailyGenerating, setDailyGenerating] = useState(false)
  const [dailyExpanded, setDailyExpanded] = useState(true)

  // ─── 新增习惯/用途 ───
  const [newHabitApp, setNewHabitApp] = useState('')
  const [newHabitDesc, setNewHabitDesc] = useState('')
  const [newOverrideApp, setNewOverrideApp] = useState('')
  const [newOverrideDesc, setNewOverrideDesc] = useState('')

  const flash = (text: string, type: 'ok' | 'err' = 'ok') => {
    setMessage({ text, type })
    setTimeout(() => setMessage(null), 3000)
  }

  const loadData = useCallback(async () => {
    try {
      const d = await getProfile()
      setData(d)
      setRoleDesc(d.profile.role_desc || '')
      setWorkStyle(d.profile.work_style || '')
      setHabits(parseJsonSafe(d.profile.habits, {}))
      setAppOverrides(parseJsonSafe(d.profile.app_overrides, {}))
    } catch (err) {
      flash('加载画像失败', 'err')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // 加载日画像
  useEffect(() => {
    if (!selectedDate) return
    setDailyLoading(true)
    getDailyProfile(selectedDate)
      .then(r => setDailyProfile(r.profile))
      .catch(() => setDailyProfile(null))
      .finally(() => setDailyLoading(false))
  }, [selectedDate])

  const handleSave = async () => {
    setSaving(true)
    try {
      await saveProfile({
        role_desc: roleDesc,
        work_style: workStyle,
        habits,
        app_overrides: appOverrides,
      })
      flash('保存成功')
      loadData()
    } catch {
      flash('保存失败', 'err')
    } finally {
      setSaving(false)
    }
  }

  const handleAddCorrection = async () => {
    if (!newCorrApp.trim()) { flash('请填写应用名称', 'err'); return }
    try {
      await addCorrection({
        app_name: newCorrApp.trim(),
        correct_category: newCorrCategory,
        correct_desc: newCorrDesc,
      })
      setNewCorrApp(''); setNewCorrCategory(''); setNewCorrDesc('')
      flash('纠正已添加')
      loadData()
    } catch { flash('添加失败', 'err') }
  }

  const handleDeleteCorrection = async (id: number) => {
    try {
      await deleteCorrection(id)
      flash('已删除')
      loadData()
    } catch { flash('删除失败', 'err') }
  }

  const handleAddHabit = () => {
    if (!newHabitApp.trim() || !newHabitDesc.trim()) return
    setHabits(prev => ({ ...prev, [newHabitApp.trim()]: newHabitDesc.trim() }))
    setNewHabitApp(''); setNewHabitDesc('')
  }

  const handleRemoveHabit = (key: string) => {
    setHabits(prev => { const n = { ...prev }; delete n[key]; return n })
  }

  const handleAddOverride = () => {
    if (!newOverrideApp.trim() || !newOverrideDesc.trim()) return
    setAppOverrides(prev => ({ ...prev, [newOverrideApp.trim()]: newOverrideDesc.trim() }))
    setNewOverrideApp(''); setNewOverrideDesc('')
  }

  const handleRemoveOverride = (key: string) => {
    setAppOverrides(prev => { const n = { ...prev }; delete n[key]; return n })
  }

  const handleGenerateDaily = async () => {
    setDailyGenerating(true)
    try {
      const r = await generateDailyProfile(selectedDate, 60000)
      if (r.ok) {
        flash('日画像已生成')
        const d = await getDailyProfile(selectedDate)
        setDailyProfile(d.profile)
      } else {
        flash('该日期无足够数据', 'err')
      }
    } catch { flash('生成失败', 'err') }
    finally { setDailyGenerating(false) }
  }

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="animate-spin text-cd-green" size={24} /></div>

  const corrections = data?.corrections || []

  return (
    <div className="animate-fade-in max-w-4xl mx-auto space-y-6">
      {/* 顶部标题 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-cd-text font-display flex items-center gap-2">
            <Brain size={22} className="text-cd-green" /> 个人画像
          </h1>
          <p className="text-sm text-cd-text-tertiary mt-1">让 AI 更懂你 — 描述你的角色、习惯，系统会在分析时参考这些信息</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 bg-cd-green text-white px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90 disabled:opacity-50 transition"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          保存画像
        </button>
      </div>

      {/* Flash message */}
      {message && (
        <div className={`px-3 py-2 rounded-lg text-sm ${
          message.type === 'ok' ? 'bg-cd-green/10 text-cd-green' : 'bg-cd-red/10 text-cd-red'
        }`}>
          {message.text}
        </div>
      )}

      {/* ─── Section 1: 角色与风格 ─── */}
      <Section icon={User} title="角色描述" subtitle="你的职业、主要工作内容">
        <textarea
          className="w-full bg-cd-bg-secondary border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:ring-1 focus:ring-cd-green/50 resize-none"
          rows={2}
          placeholder="例如：Java全栈开发工程师，负责后端服务架构和前端交互优化"
          value={roleDesc}
          onChange={e => setRoleDesc(e.target.value)}
        />
      </Section>

      <Section icon={Briefcase} title="工作风格" subtitle="你的工作习惯和偏好">
        <textarea
          className="w-full bg-cd-bg-secondary border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:ring-1 focus:ring-cd-green/50 resize-none"
          rows={2}
          placeholder="例如：专注型，习惯长时间沉浸编码，间歇查看消息"
          value={workStyle}
          onChange={e => setWorkStyle(e.target.value)}
        />
      </Section>

      {/* ─── Section 2: App 用途说明 ─── */}
      <Section icon={Wrench} title="App 用途说明" subtitle="告诉 AI 你用每个 App 做什么，更精准分类">
        <div className="space-y-2">
          {Object.entries(appOverrides).map(([app, desc]) => (
            <div key={app} className="flex items-center gap-2">
              <span className="text-sm font-medium text-cd-text bg-cd-bg-secondary px-2.5 py-1 rounded-md min-w-[120px] truncate" title={app}>{app}</span>
              <span className="text-sm text-cd-text-secondary flex-1 truncate">{desc}</span>
              <button onClick={() => handleRemoveOverride(app)} className="text-cd-text-tertiary hover:text-cd-red transition p-1">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          <div className="flex items-center gap-2 pt-1">
            <input
              className="flex-1 bg-cd-bg-secondary border border-cd-border rounded-md px-2.5 py-1.5 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:ring-1 focus:ring-cd-green/50 min-w-0"
              placeholder="应用名（如 WeChat）"
              value={newOverrideApp}
              onChange={e => setNewOverrideApp(e.target.value)}
            />
            <input
              className="flex-[2] bg-cd-bg-secondary border border-cd-border rounded-md px-2.5 py-1.5 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:ring-1 focus:ring-cd-green/50 min-w-0"
              placeholder="用途说明（如 团队沟通协调）"
              value={newOverrideDesc}
              onChange={e => setNewOverrideDesc(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAddOverride()}
            />
            <button onClick={handleAddOverride} className="flex items-center gap-1 bg-cd-green/10 text-cd-green px-2.5 py-1.5 rounded-md text-sm hover:bg-cd-green/20 transition shrink-0">
              <Plus size={14} /> 添加
            </button>
          </div>
        </div>
      </Section>

      {/* ─── Section 3: 使用习惯 ─── */}
      <Section icon={Sparkles} title="使用习惯" subtitle="常用软件的使用方式描述">
        <div className="space-y-2">
          {Object.entries(habits).map(([app, desc]) => (
            <div key={app} className="flex items-center gap-2">
              <span className="text-sm font-medium text-cd-text bg-cd-bg-secondary px-2.5 py-1 rounded-md min-w-[120px] truncate" title={app}>{app}</span>
              <span className="text-sm text-cd-text-secondary flex-1 truncate">{desc}</span>
              <button onClick={() => handleRemoveHabit(app)} className="text-cd-text-tertiary hover:text-cd-red transition p-1">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          <div className="flex items-center gap-2 pt-1">
            <input
              className="flex-1 bg-cd-bg-secondary border border-cd-border rounded-md px-2.5 py-1.5 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:ring-1 focus:ring-cd-green/50 min-w-0"
              placeholder="应用名（如 IntelliJ IDEA）"
              value={newHabitApp}
              onChange={e => setNewHabitApp(e.target.value)}
            />
            <input
              className="flex-[2] bg-cd-bg-secondary border border-cd-border rounded-md px-2.5 py-1.5 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:ring-1 focus:ring-cd-green/50 min-w-0"
              placeholder="使用方式（如 项目开发和调试）"
              value={newHabitDesc}
              onChange={e => setNewHabitDesc(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAddHabit()}
            />
            <button onClick={handleAddHabit} className="flex items-center gap-1 bg-cd-green/10 text-cd-green px-2.5 py-1.5 rounded-md text-sm hover:bg-cd-green/20 transition shrink-0">
              <Plus size={14} /> 添加
            </button>
          </div>
        </div>
      </Section>

      {/* ─── Section 4: 分类纠正 ─── */}
      <Section icon={Wrench} title="分类纠正" subtitle="修正 AI 对 App 的分类错误，系统会学习你的偏好">
        <div className="space-y-2">
          {corrections.length > 0 && (
            <div className="space-y-1.5">
              {corrections.map(c => (
                <div key={c.id} className="flex items-center gap-2 bg-cd-bg-secondary rounded-lg px-3 py-2">
                  <span className="text-sm font-medium text-cd-text">{c.app_name}</span>
                  <span className="text-cd-text-tertiary text-xs">→</span>
                  <span className="text-sm text-cd-green font-medium">{c.correct_category || '重新分类'}</span>
                  {c.correct_desc && <span className="text-xs text-cd-text-tertiary truncate flex-1">{c.correct_desc}</span>}
                  <button onClick={() => handleDeleteCorrection(c.id)} className="text-cd-text-tertiary hover:text-cd-red transition p-1 shrink-0">
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="grid grid-cols-[1fr_140px_1fr_auto] gap-2 items-end">
            <div>
              <label className="text-[10px] text-cd-text-tertiary mb-0.5 block">应用名称</label>
              <input
                className="w-full bg-cd-bg border border-cd-border rounded-md px-2.5 py-1.5 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:ring-1 focus:ring-cd-green/50"
                placeholder="如 WeChat"
                value={newCorrApp}
                onChange={e => setNewCorrApp(e.target.value)}
              />
            </div>
            <div>
              <label className="text-[10px] text-cd-text-tertiary mb-0.5 block">正确分类</label>
              <select
                className="w-full bg-cd-bg border border-cd-border rounded-md px-2 py-1.5 text-sm text-cd-text focus:outline-none focus:ring-1 focus:ring-cd-green/50"
                value={newCorrCategory}
                onChange={e => setNewCorrCategory(e.target.value)}
              >
                <option value="">选择分类</option>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-cd-text-tertiary mb-0.5 block">说明（可选）</label>
              <input
                className="w-full bg-cd-bg border border-cd-border rounded-md px-2.5 py-1.5 text-sm text-cd-text placeholder:text-cd-text-tertiary focus:outline-none focus:ring-1 focus:ring-cd-green/50"
                placeholder="为什么应该是这个分类"
                value={newCorrDesc}
                onChange={e => setNewCorrDesc(e.target.value)}
              />
            </div>
            <button onClick={handleAddCorrection} className="flex items-center gap-1 bg-cd-green/10 text-cd-green px-3 py-1.5 rounded-md text-sm hover:bg-cd-green/20 transition shrink-0 h-[34px]">
              <Plus size={14} /> 纠正
            </button>
          </div>
          {corrections.length === 0 && (
            <p className="text-xs text-cd-text-tertiary text-center py-2">
              暂无纠正记录。当 AI 分类不准确时，在此添加纠正，系统会在后续分析中参考。
            </p>
          )}
        </div>
      </Section>

      {/* ─── Section 5: 每日画像 ─── */}
      <div className="bg-cd-card border border-cd-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Calendar size={18} className="text-cd-green" />
            <h2 className="text-sm font-semibold text-cd-text">每日画像</h2>
            <span className="text-[10px] text-cd-text-tertiary">AI 基于全天数据生成的结构化总结</span>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date"
              className="bg-cd-bg-secondary border border-cd-border rounded-md px-2 py-1 text-sm text-cd-text focus:outline-none focus:ring-1 focus:ring-cd-green/50"
              value={selectedDate}
              onChange={e => setSelectedDate(e.target.value)}
            />
            <button
              onClick={() => setDailyExpanded(!dailyExpanded)}
              className="text-cd-text-tertiary hover:text-cd-text transition p-1"
            >
              {dailyExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          </div>
        </div>

        {dailyExpanded && (
          <>
            {dailyLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="animate-spin text-cd-green" size={20} />
              </div>
            ) : dailyProfile ? (
              <div className="space-y-4">
                <div className="bg-cd-bg-secondary rounded-lg p-3">
                  <p className="text-sm text-cd-text leading-relaxed">{dailyProfile.daily_summary}</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <InfoBlock label="生产力评级" value={dailyProfile.productivity || '-'} />
                  <InfoBlock label="主力应用" value={parseJsonSafe<string[]>(dailyProfile.top_apps, []).slice(0, 5).join('、') || '-'} />
                  <InfoBlock label="专注时段" value={parseJsonSafe<number[]>(dailyProfile.focus_hours, []).map(h => `${h}:00`).join('、') || '-'} />
                  <InfoBlock label="生成时间" value={dailyProfile.generated_at || '-'} />
                </div>

                {(() => {
                  const patterns = parseJsonSafe<string[]>(dailyProfile.work_patterns, [])
                  const insights = parseJsonSafe<string[]>(dailyProfile.key_insights, [])
                  if (patterns.length === 0 && insights.length === 0) return null
                  return (
                    <div className="grid grid-cols-2 gap-3">
                      {patterns.length > 0 && (
                        <div>
                          <h4 className="text-[10px] font-semibold text-cd-text-tertiary uppercase mb-1.5">工作模式</h4>
                          <ul className="space-y-1">
                            {patterns.map((p, i) => <li key={i} className="text-xs text-cd-text-secondary flex items-start gap-1.5"><span className="text-cd-green mt-0.5">•</span>{p}</li>)}
                          </ul>
                        </div>
                      )}
                      {insights.length > 0 && (
                        <div>
                          <h4 className="text-[10px] font-semibold text-cd-text-tertiary uppercase mb-1.5">关键洞察</h4>
                          <ul className="space-y-1">
                            {insights.map((ins, i) => <li key={i} className="text-xs text-cd-text-secondary flex items-start gap-1.5"><span className="text-cd-purple mt-0.5">•</span>{ins}</li>)}
                          </ul>
                        </div>
                      )}
                    </div>
                  )
                })()}

                <button
                  onClick={handleGenerateDaily}
                  disabled={dailyGenerating}
                  className="flex items-center gap-1.5 text-xs text-cd-green hover:underline disabled:opacity-50"
                >
                  {dailyGenerating ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                  重新生成
                </button>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-sm text-cd-text-tertiary mb-3">该日期暂无日画像</p>
                <button
                  onClick={handleGenerateDaily}
                  disabled={dailyGenerating}
                  className="inline-flex items-center gap-1.5 bg-cd-green/10 text-cd-green px-4 py-2 rounded-lg text-sm hover:bg-cd-green/20 disabled:opacity-50 transition"
                >
                  {dailyGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                  {dailyGenerating ? '正在生成...' : '生成日画像'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}


// ─── 辅助组件 ───

function Section({ icon: Icon, title, subtitle, children }: {
  icon: React.ComponentType<{ size?: number; className?: string }>
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-cd-card border border-cd-border rounded-xl p-5">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={16} className="text-cd-green" />
        <h2 className="text-sm font-semibold text-cd-text">{title}</h2>
        {subtitle && <span className="text-[10px] text-cd-text-tertiary ml-1">{subtitle}</span>}
      </div>
      {children}
    </div>
  )
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-cd-bg-secondary rounded-lg px-3 py-2">
      <p className="text-[10px] text-cd-text-tertiary mb-0.5">{label}</p>
      <p className="text-sm text-cd-text font-medium truncate" title={value}>{value}</p>
    </div>
  )
}
