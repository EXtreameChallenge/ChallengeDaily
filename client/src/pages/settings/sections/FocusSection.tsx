
interface FocusSectionProps {
  focusStrictness: 'relaxed' | 'standard' | 'strict'
  setFocusStrictness: (v: 'relaxed' | 'standard' | 'strict') => void
}

export function FocusSection({ focusStrictness, setFocusStrictness }: FocusSectionProps) {
  return (
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-cd-text mb-3">专注监督</h2>

        <div className="space-y-4">
          {/* 三档严格度 */}
          <div>
            <label className="text-xs text-cd-text-secondary block mb-2">检测严格度</label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { value: 'relaxed', label: '宽松', desc: '仅检测游戏/短视频', color: 'text-green-400' },
                { value: 'standard', label: '标准', desc: '窗口标题+相关性', color: 'text-blue-400' },
                { value: 'strict', label: '严格', desc: '截图深度分析', color: 'text-orange-400' },
              ].map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setFocusStrictness(opt.value as any)}
                  className={`p-3 rounded-2xl border text-left transition ${
                    focusStrictness === opt.value
                      ? 'border-cd-accent bg-cd-accent/10'
                      : 'border-cd-border bg-cd-bg-secondary hover:border-cd-text-tertiary'
                  }`}
                >
                  <div className={`text-sm font-medium ${focusStrictness === opt.value ? opt.color : 'text-cd-text'}`}>
                    {opt.label}
                  </div>
                  <div className="text-[10px] text-cd-text-tertiary mt-0.5">{opt.desc}</div>
                </button>
              ))}
            </div>
            <p className="text-[11px] text-cd-text-tertiary mt-2">
              宽松模式仅拦截明显分心应用；标准模式结合窗口标题判断内容相关性（推荐）；严格模式会调用视觉模型分析截图内容。
            </p>
          </div>
        </div>
      </div>
  )
}


