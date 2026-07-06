import { useState } from 'react'
import { updateSettings, testAiConnection } from '../api/client'
import {
  Sparkles,
  Bot,
  Clock,
  Shield,
  ChevronRight,
  ChevronLeft,
  CheckCircle,
  Loader2,
  Eye,
  EyeOff,
  Zap,
} from 'lucide-react'

const STEPS = ['welcome', 'ai', 'work-hours', 'done'] as const
type Step = typeof STEPS[number]

interface OnboardingProps {
  onComplete: () => void
}

export default function Onboarding({ onComplete }: OnboardingProps) {
  const [step, setStep] = useState<Step>('welcome')
  const stepIdx = STEPS.indexOf(step)

  // AI 配置
  const [aiEnabled, setAiEnabled] = useState(true)
  const [useFreeModel, setUseFreeModel] = useState(true)
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('https://open.bigmodel.cn/api/paas/v4')
  const [apiVisionModel, setApiVisionModel] = useState('glm-4v-flash')
  const [apiTextModel, setApiTextModel] = useState('glm-4-flash')
  const [showKey, setShowKey] = useState(false)
  const [aiTesting, setAiTesting] = useState(false)
  const [aiTestResult, setAiTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  // 工作时间
  const [workStart, setWorkStart] = useState(9)
  const [workEnd, setWorkEnd] = useState(18)

  const handleTestAi = async () => {
    setAiTesting(true)
    setAiTestResult(null)
    try {
      // 新手引导默认测试识图模型
      const result = await testAiConnection(apiKey, apiBase, apiVisionModel)
      setAiTestResult(result)
    } catch (err: any) {
      setAiTestResult({ ok: false, message: err.message || '测试失败' })
    } finally {
      setAiTesting(false)
    }
  }

  const handleUseFreeModel = () => {
    setUseFreeModel(true)
    setApiBase('https://open.bigmodel.cn/api/paas/v4')
    setApiVisionModel('glm-4v-flash')
    setApiTextModel('glm-4-flash')
  }

  const handleComplete = async () => {
    // 保存设置到后端
    try {
      const settings: Record<string, any> = {
        ai_enabled: aiEnabled,
        ai_base_url: apiBase,
        ai_vision_model: apiVisionModel,
        ai_text_model: apiTextModel,
        work_start_hour: workStart,
        work_end_hour: workEnd,
      }
      // 仅当用户实际输入了 API Key 时才发送
      if (apiKey.trim()) {
        settings.ai_api_key = apiKey.trim()
      }
      await updateSettings(settings)
    } catch (err) {
      console.error('Failed to save onboarding settings:', err)
    }
    localStorage.setItem('cd_onboarding_done', '1')
    onComplete()
  }

  const goNext = () => {
    if (step === 'done') {
      handleComplete()
      return
    }
    const nextIdx = Math.min(stepIdx + 1, STEPS.length - 1)
    setStep(STEPS[nextIdx])
  }

  const goPrev = () => {
    const prevIdx = Math.max(stepIdx - 1, 0)
    setStep(STEPS[prevIdx])
  }

  return (
    <div className="flex-1 flex items-center justify-center bg-cd-bg">
      <div className="w-full max-w-lg px-8">
        {/* ─── 步骤指示器 ─── */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((s, i) => (
            <div
              key={s}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                i === stepIdx
                  ? 'w-8 bg-cd-green'
                  : i < stepIdx
                    ? 'w-6 bg-cd-green/40'
                    : 'w-6 bg-cd-border'
              }`}
            />
          ))}
        </div>

        {/* ─── 步骤内容 ─── */}
        <div className="animate-fade-in">
          {step === 'welcome' && <WelcomeStep />}
          {step === 'ai' && (
            <AIStep
              aiEnabled={aiEnabled}
              setAiEnabled={setAiEnabled}
              useFreeModel={useFreeModel}
              setUseFreeModel={setUseFreeModel}
              handleUseFreeModel={handleUseFreeModel}
              apiKey={apiKey}
              setApiKey={setApiKey}
              apiBase={apiBase}
              setApiBase={setApiBase}
              apiVisionModel={apiVisionModel}
              setApiVisionModel={setApiVisionModel}
              apiTextModel={apiTextModel}
              setApiTextModel={setApiTextModel}
              showKey={showKey}
              setShowKey={setShowKey}
              aiTesting={aiTesting}
              aiTestResult={aiTestResult}
              handleTestAi={handleTestAi}
            />
          )}
          {step === 'work-hours' && (
            <WorkHoursStep
              workStart={workStart}
              setWorkStart={setWorkStart}
              workEnd={workEnd}
              setWorkEnd={setWorkEnd}
            />
          )}
          {step === 'done' && <DoneStep />}
        </div>

        {/* ─── 导航按钮 ─── */}
        <div className="flex items-center justify-between mt-8">
          <button
            onClick={goPrev}
            disabled={stepIdx === 0}
            className="flex items-center gap-1 px-4 py-2 rounded-lg text-sm text-cd-text-secondary hover:bg-cd-hover transition-colors disabled:opacity-0"
          >
            <ChevronLeft size={16} />
            上一步
          </button>

          <button
            onClick={goNext}
            className="flex items-center gap-1 px-6 py-2.5 rounded-lg text-sm font-medium bg-cd-green hover:bg-cd-green-dark text-white transition-colors"
          >
            {step === 'done' ? '开始使用' : '下一步'}
            {step !== 'done' && <ChevronRight size={16} />}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════
   Step: Welcome
   ═══════════════════════════════════════════ */
function WelcomeStep() {
  return (
    <div className="text-center">
      <div className="w-16 h-16 rounded-2xl bg-cd-green flex items-center justify-center text-white text-2xl font-bold mx-auto mb-5">
        CD
      </div>
      <h1 className="text-2xl font-bold text-cd-text mb-2 font-display">欢迎使用 <span className="font-brand font-bold">ChallengeDaily</span></h1>
      <p className="text-cd-text-secondary text-sm mb-6">
        AI 智能工作日报助手，自动记录你的工作轨迹
      </p>

      <div className="grid grid-cols-3 gap-4 text-center">
        {[
          { icon: Sparkles, title: '智能截图', desc: '后台静默捕获屏幕，AI 视觉识别工作内容' },
          { icon: Bot, title: 'AI 分析', desc: '自动分类12大工作类别，生成自然语言摘要' },
          { icon: Shield, title: '隐私优先', desc: '数据全部本地存储，截图分析后即删' },
        ].map(({ icon: Icon, title, desc }) => (
          <div key={title} className="card py-4 px-3">
            <div className="w-8 h-8 rounded-lg bg-cd-green-light flex items-center justify-center mx-auto mb-2">
              <Icon size={16} className="text-cd-green" />
            </div>
            <div className="text-xs font-semibold text-cd-text mb-1">{title}</div>
            <div className="text-[10px] text-cd-text-tertiary leading-relaxed">{desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════
   Step: AI Configuration
   ═══════════════════════════════════════════ */
function AIStep({
  aiEnabled, setAiEnabled,
  useFreeModel, setUseFreeModel, handleUseFreeModel,
  apiKey, setApiKey,
  apiBase, setApiBase,
  apiVisionModel, setApiVisionModel,
  apiTextModel, setApiTextModel,
  showKey, setShowKey,
  aiTesting, aiTestResult, handleTestAi,
}: {
  aiEnabled: boolean; setAiEnabled: (v: boolean) => void
  useFreeModel: boolean; setUseFreeModel: (v: boolean) => void; handleUseFreeModel: () => void
  apiKey: string; setApiKey: (v: string) => void
  apiBase: string; setApiBase: (v: string) => void
  apiVisionModel: string; setApiVisionModel: (v: string) => void
  apiTextModel: string; setApiTextModel: (v: string) => void
  showKey: boolean; setShowKey: (v: boolean) => void
  aiTesting: boolean
  aiTestResult: { ok: boolean; message: string } | null
  handleTestAi: () => void
}) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <Bot size={20} className="text-cd-green" />
        <h2 className="text-lg font-bold text-cd-text font-display">配置 AI 分析</h2>
      </div>
      <p className="text-xs text-cd-text-tertiary mb-5">
        AI 会识别截图内容，自动分类并生成摘要。不用 AI 也可以用基础规则分类。
      </p>

      {/* AI 开关 */}
      <div className="flex items-center justify-between mb-4">
        <span className="text-sm text-cd-text">启用 AI 分析</span>
        <button
          onClick={() => setAiEnabled(!aiEnabled)}
          role="switch"
          aria-checked={aiEnabled}
          className={`relative w-10 h-5 rounded-full transition-colors ${
            aiEnabled ? 'bg-cd-green' : 'bg-cd-border'
          }`}
        >
          <span
            className="absolute top-0.5 w-4 h-4 rounded-full bg-cd-card shadow-sm transition-all"
            style={{ left: aiEnabled ? '22px' : '2px' }}
          />
        </button>
      </div>

      {aiEnabled && (
        <div className="space-y-3 animate-fade-in">
          {/* 一键免费配置 */}
          <button
            onClick={handleUseFreeModel}
            className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 transition-all ${
              useFreeModel
                ? 'border-cd-green bg-cd-green-light'
                : 'border-cd-border bg-cd-bg-secondary hover:border-cd-green/30'
            }`}
          >
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              useFreeModel ? 'bg-cd-green text-white' : 'bg-cd-bg text-cd-text-tertiary'
            }`}>
              <Zap size={20} />
            </div>
            <div className="text-left flex-1">
              <div className="text-sm font-semibold text-cd-text">使用免费模型（推荐）</div>
              <div className="text-[10px] text-cd-text-tertiary">
                智谱 GLM-4V-Flash / 完全免费 / 国内直连 / 支持图片理解
              </div>
            </div>
            {useFreeModel && <CheckCircle size={18} className="text-cd-green shrink-0" />}
          </button>

          {/* 自定义配置 */}
          <button
            onClick={() => setUseFreeModel(false)}
            className={`w-full flex items-center gap-3 p-3 rounded-xl border-2 transition-all ${
              !useFreeModel
                ? 'border-cd-green bg-cd-green-light'
                : 'border-cd-border bg-cd-bg-secondary hover:border-cd-green/30'
            }`}
          >
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
              !useFreeModel ? 'bg-cd-green text-white' : 'bg-cd-bg text-cd-text-tertiary'
            }`}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
            </div>
            <div className="text-left flex-1">
              <div className="text-sm font-semibold text-cd-text">自定义模型</div>
              <div className="text-[10px] text-cd-text-tertiary">
                支持 OpenAI 协议的任意模型（GPT-4o、通义千问等）
              </div>
            </div>
            {!useFreeModel && <CheckCircle size={18} className="text-cd-green shrink-0" />}
          </button>

          {/* 自定义配置表单 */}
          {!useFreeModel && (
            <div className="space-y-3 animate-fade-in border border-cd-border rounded-xl p-4 bg-cd-bg-secondary">
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">API Base URL</label>
                <input
                  type="text"
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                  className="w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-cd-text-secondary block mb-1">识图模型</label>
                  <input
                    type="text"
                    value={apiVisionModel}
                    onChange={(e) => setApiVisionModel(e.target.value)}
                    placeholder="glm-4v-flash"
                    className="w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
                  />
                </div>
                <div>
                  <label className="text-xs text-cd-text-secondary block mb-1">文本模型</label>
                  <input
                    type="text"
                    value={apiTextModel}
                    onChange={(e) => setApiTextModel(e.target.value)}
                    placeholder="glm-4-flash"
                    className="w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">API Key</label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="sk-..."
                    className="w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-1.5 pr-9 text-sm focus:outline-none focus:border-cd-green"
                  />
                  <button
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-1.5 text-cd-text-tertiary hover:text-cd-text"
                  >
                    {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 免费模型需要的 API Key */}
          {useFreeModel && (
            <div className="space-y-3 animate-fade-in border border-cd-border rounded-xl p-4 bg-cd-bg-secondary">
              <div>
                <label className="text-xs text-cd-text-secondary block mb-1">
                  智谱 API Key
                  <span className="text-cd-green ml-1">（免费注册获取）</span>
                </label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="在 open.bigmodel.cn 免费注册后获取"
                    className="w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-1.5 pr-9 text-sm focus:outline-none focus:border-cd-green"
                  />
                  <button
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-1.5 text-cd-text-tertiary hover:text-cd-text"
                  >
                    {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* AI 测试 */}
          {apiKey && (
            <div>
              <button
                onClick={handleTestAi}
                disabled={aiTesting}
                className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-medium bg-cd-bg-secondary text-cd-text-secondary hover:bg-cd-hover transition-colors border border-cd-border disabled:opacity-40"
              >
                {aiTesting ? (
                  <><Loader2 size={12} className="animate-spin" /> 正在测试...</>
                ) : (
                  <>测试连接</>
                )}
              </button>
              {aiTestResult && (
                <div className={`mt-2 flex items-center gap-1.5 text-xs ${
                  aiTestResult.ok ? 'text-cd-green' : 'text-cd-red'
                }`}>
                  {aiTestResult.ok ? <CheckCircle size={12} /> : <span>!</span>}
                  {aiTestResult.message}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!aiEnabled && (
        <div className="text-xs text-cd-text-tertiary bg-cd-bg-secondary rounded-lg p-3 mt-2">
          不启用 AI 时，将使用应用名称规则进行基础分类，无法生成智能摘要。
          你可以随时在设置中启用 AI。
        </div>
      )}
    </div>
  )
}

/* ═══════════════════════════════════════════
   Step: Work Hours
   ═══════════════════════════════════════════ */
function WorkHoursStep({
  workStart, setWorkStart,
  workEnd, setWorkEnd,
}: {
  workStart: number; setWorkStart: (v: number) => void
  workEnd: number; setWorkEnd: (v: number) => void
}) {
  const hours = Array.from({ length: 24 }, (_, i) => i)
  const totalWorkHours = workEnd > workStart ? workEnd - workStart : 24 - workStart + workEnd

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <Clock size={20} className="text-cd-green" />
        <h2 className="text-lg font-bold text-cd-text font-display">设置工作时间</h2>
      </div>
      <p className="text-xs text-cd-text-tertiary mb-5">
        只在工作时间段内自动截图记录，休息时间不打扰。你也可以在设置中随时调整。
      </p>

      <div className="card space-y-5">
        {/* 时间条可视化 */}
        <div className="flex gap-0.5">
          {hours.map((h) => {
            const isWork = h >= workStart && h < workEnd
            return (
              <div
                key={h}
                className={`flex-1 h-8 rounded-sm flex items-center justify-center text-[9px] transition-colors ${
                  isWork ? 'bg-cd-green-light text-cd-green font-medium' : 'bg-cd-bg-secondary text-cd-text-tertiary'
                }`}
              >
                {h}
              </div>
            )
          })}
        </div>

        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-2">工作开始</label>
            <div className="text-2xl font-bold text-cd-text font-display">
              {String(workStart).padStart(2, '0')}:00
            </div>
            <input
              type="range"
              value={workStart}
              onChange={(e) => setWorkStart(Number(e.target.value))}
              min={0}
              max={23}
              className="w-full mt-2 accent-cd-green"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-2">工作结束</label>
            <div className="text-2xl font-bold text-cd-text">
              {String(workEnd).padStart(2, '0')}:00
            </div>
            <input
              type="range"
              value={workEnd}
              onChange={(e) => setWorkEnd(Number(e.target.value))}
              min={1}
              max={24}
              className="w-full mt-2 accent-cd-green"
            />
          </div>
        </div>

        <div className="text-center text-xs text-cd-text-tertiary">
          每天将自动记录约 {totalWorkHours} 小时的工作轨迹
        </div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════
   Step: Done
   ═══════════════════════════════════════════ */
function DoneStep() {
  return (
    <div className="text-center">
      <div className="w-16 h-16 rounded-full bg-cd-green-light flex items-center justify-center mx-auto mb-5">
        <CheckCircle size={32} className="text-cd-green" />
      </div>
      <h2 className="text-xl font-bold text-cd-text mb-2 font-display">一切就绪！</h2>
      <p className="text-sm text-cd-text-secondary mb-6">
        ChallengeDaily 已开始在后台默默记录你的工作轨迹
      </p>

      <div className="space-y-3 text-left max-w-xs mx-auto">
        {[
          '截图每 60 秒自动采集一次，可在设置中调整',
          'AI 会识别截图内容并自动分类到 12 大类别',
          '在「生成报告」页面一键生成工作日报',
          '工作结束后会自动生成今日日报',
        ].map((text, i) => (
          <div key={i} className="flex items-start gap-2.5">
            <div className="w-5 h-5 rounded-full bg-cd-green-light flex items-center justify-center shrink-0 mt-0.5">
              <span className="text-[10px] text-cd-green font-bold">{i + 1}</span>
            </div>
            <span className="text-xs text-cd-text-secondary">{text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
