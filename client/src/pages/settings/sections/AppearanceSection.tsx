import { useTheme, ACCENT_PRESETS, FONT_PRESETS, RADIUS_PRESETS, SHADOW_PRESETS, OPACITY_PRESETS, SKIN_PRESETS } from '../../../components/ThemeContext'
import { ToggleSwitch } from '../../../components/shared'
import { Palette, CheckCircle, Moon, Cat, Rocket, Type, GlassWater } from 'lucide-react'

interface AppearanceSectionProps {
  highlighted: boolean
  petVisible: boolean
  autoStart: boolean
  handleTogglePet: (show: boolean) => void
  handleToggleAutoStart: (enabled: boolean) => void
}

export function AppearanceSection({ highlighted, petVisible, autoStart, handleTogglePet, handleToggleAutoStart }: AppearanceSectionProps) {
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
  return (
      <section
        id="settings-section-外观"
        className={`card space-y-4 ${highlighted ? 'ring-2 ring-cd-green' : ''}`}
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
                    className={`relative rounded-2xl border-2 p-2.5 transition-all duration-150 ${
                      i === skinIndex
                        ? 'border-cd-green'
                        : 'border-cd-border hover:border-cd-text-tertiary'
                    }`}
                  >
                    {/* 迷你预览 */}
                    <div
                      className="rounded-2xl p-2 mb-2 h-14 flex gap-1.5 overflow-hidden"
                      style={{ background: pBg, border: `1px solid ${pBorder}` }}
                    >
                      {/* sidebar 缩略 */}
                      <div
                        className="w-3.5 rounded-lg flex flex-col gap-0.5 py-1 items-center"
                        style={{ background: pSidebar }}
                      >
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--cd-accent)' }} />
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: pBorder }} />
                        <div className="w-1.5 h-1.5 rounded-full" style={{ background: pBorder }} />
                      </div>
                      {/* content 缩略 */}
                      <div className="flex-1 flex flex-col gap-1">
                        <div className="h-1 rounded-full" style={{ background: 'var(--cd-accent)', width: '60%' }} />
                        <div
                          className="flex-1 rounded-lg flex flex-col gap-0.5 p-1"
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
            <div className="flex items-center gap-1 bg-cd-bg-input rounded-2xl p-0.5 border border-cd-border">
              {([
                { key: 'light', label: '亮色' },
                { key: 'dark', label: '深色' },
                { key: 'auto', label: '跟随系统' },
              ] as const).map(opt => (
                <button
                  key={opt.key}
                  onClick={() => setThemeExplicit(opt.key)}
                  className={`px-2.5 py-1 text-xs rounded-2xl transition ${
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
                className="w-7 h-7 rounded-lg cursor-pointer border border-cd-border bg-transparent"
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
                  className={`px-3 py-1.5 rounded-2xl text-xs font-medium transition-all duration-150 border ${
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
                  className={`px-3 py-1.5 rounded-2xl text-xs font-medium transition-all duration-150 border ${
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
                  className={`px-3 py-1.5 rounded-2xl text-xs font-medium transition-all duration-150 border ${
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
                  className={`px-3 py-1.5 rounded-2xl text-xs font-medium transition-all duration-150 border ${
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
  )
}


