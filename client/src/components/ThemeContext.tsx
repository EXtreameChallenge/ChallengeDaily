import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'

type Theme = 'light' | 'dark' | 'auto'
type EffectiveTheme = 'light' | 'dark'

// 预设主题色
export const ACCENT_PRESETS = [
  { name: '经典紫', light: '#7B68EE', lightBg: '#F3F0FF', dark: '#937CFF', darkBg: 'rgba(123,104,238,0.15)' },
  { name: '翠绿', light: '#27AE60', lightBg: '#E8F5E9', dark: '#4CAF7C', darkBg: 'rgba(39,174,96,0.15)' },
  { name: '天蓝', light: '#2196F3', lightBg: '#E3F2FD', dark: '#64B5F6', darkBg: 'rgba(33,150,243,0.15)' },
  { name: '珊瑚橙', light: '#FF7043', lightBg: '#FBE9E7', dark: '#FF8A65', darkBg: 'rgba(255,112,67,0.15)' },
  { name: '玫瑰红', light: '#E91E63', lightBg: '#FCE4EC', dark: '#F06292', darkBg: 'rgba(233,30,99,0.15)' },
  { name: '琥珀金', light: '#F0A030', lightBg: '#FFF8E1', dark: '#FFB74D', darkBg: 'rgba(240,160,48,0.15)' },
  { name: '靛青', light: '#00BCD4', lightBg: '#E0F7FA', dark: '#4DD0E1', darkBg: 'rgba(0,188,212,0.15)' },
  { name: '石墨灰', light: '#607D8B', lightBg: '#ECEFF1', dark: '#90A4AE', darkBg: 'rgba(96,125,139,0.15)' },
]

export const FONT_PRESETS = [
  { name: 'Golden Time (默认)', value: "'Fraunces', 'FZQingKeBenYueSong', 'Microsoft YaHei', 'PingFang SC', ui-serif, serif" },
  { name: '苹方', value: "'PingFang SC', 'Microsoft YaHei', sans-serif" },
  { name: '微软雅黑', value: "'Microsoft YaHei', 'PingFang SC', sans-serif" },
  { name: '思源黑体', value: "'Noto Sans SC', 'Source Han Sans SC', 'Microsoft YaHei', sans-serif" },
  { name: '等宽极客', value: "'Anthropic Mono', 'JetBrains Mono', 'Fira Code', Consolas, monospace" },
]

export const RADIUS_PRESETS = [
  { name: '小', value: '0.375rem' },
  { name: '中', value: '0.5rem' },
  { name: '大', value: '0.75rem' },
  { name: '超大', value: '1rem' },
]

export const SHADOW_PRESETS = [
  { name: '无', value: 'none' },
  { name: '弱', value: '0 1px 2px 0 rgba(0, 0, 0, 0.05)' },
  { name: '中', value: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1)' },
  { name: '强', value: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1)' },
]

export const OPACITY_PRESETS = [
  { name: '100%', value: 1 },
  { name: '92%', value: 0.92 },
  { name: '84%', value: 0.84 },
  { name: '76%', value: 0.76 },
]

// ── 皮肤预设：经典（中性灰白）vs 翰墨（宣纸墨韵）──
// 皮肤改变表面/文字/边框的色温，强调色仍由 accent 独立控制
export const SKIN_PRESETS = [
  { name: '经典', value: 'classic', desc: '中性灰白 · 清爽现代', lightBg: '#FFFFFF', darkBg: '#121212' },
  { name: '翰墨', value: 'hanmo', desc: '宣纸墨韵 · 古典温润', lightBg: '#F7F3ED', darkBg: '#1A1714' },
]

interface ThemeCtx {
  theme: Theme
  effectiveTheme: EffectiveTheme
  toggleTheme: () => void
  setThemeExplicit: (t: Theme) => void
  accentIndex: number
  setAccentIndex: (i: number) => void
  fontIndex: number
  setFontIndex: (i: number) => void
  sidebarTranslucent: boolean
  setSidebarTranslucent: (v: boolean) => void
  radiusIndex: number
  setRadiusIndex: (i: number) => void
  shadowIndex: number
  setShadowIndex: (i: number) => void
  opacityIndex: number
  setOpacityIndex: (i: number) => void
  skinIndex: number
  setSkinIndex: (i: number) => void
}

const ThemeContext = createContext<ThemeCtx>({
  theme: 'light', effectiveTheme: 'light', toggleTheme: () => {}, setThemeExplicit: () => {},
  accentIndex: 0, setAccentIndex: () => {},
  fontIndex: 0, setFontIndex: () => {},
  sidebarTranslucent: false, setSidebarTranslucent: () => {},
  radiusIndex: 1, setRadiusIndex: () => {},
  shadowIndex: 1, setShadowIndex: () => {},
  opacityIndex: 0, setOpacityIndex: () => {},
  skinIndex: 0, setSkinIndex: () => {},
})

export function useTheme() {
  return useContext(ThemeContext)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('cd_theme')
    if (saved === 'dark' || saved === 'light' || saved === 'auto') return saved
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
  // P14-1：跟踪系统深色偏好，用于 'auto' 模式实时跟随
  const [systemDark, setSystemDark] = useState<boolean>(() =>
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
  // P14-1：监听系统主题变化，auto 模式下自动切换
  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])
  // 解析后的有效主题：auto → 根据系统偏好；light/dark → 原值
  const effectiveTheme: EffectiveTheme = theme === 'auto' ? (systemDark ? 'dark' : 'light') : theme
  const [accentIndex, setAccentIndex] = useState(() => {
    const saved = localStorage.getItem('cd_accent')
    const n = parseInt(saved || '0', 10)
    return n >= 0 && n < ACCENT_PRESETS.length ? n : 0
  })
  const [fontIndex, setFontIndex] = useState(() => {
    const saved = localStorage.getItem('cd_font')
    const n = parseInt(saved || '0', 10)
    return n >= 0 && n < FONT_PRESETS.length ? n : 0
  })
  const [sidebarTranslucent, setSidebarTranslucent] = useState(() => {
    return localStorage.getItem('cd_sidebar_translucent') === '1'
  })
  const [radiusIndex, setRadiusIndex] = useState(() => {
    const saved = localStorage.getItem('cd_radius')
    const n = parseInt(saved || '1', 10)
    return n >= 0 && n < RADIUS_PRESETS.length ? n : 1
  })
  const [shadowIndex, setShadowIndex] = useState(() => {
    const saved = localStorage.getItem('cd_shadow')
    const n = parseInt(saved || '1', 10)
    return n >= 0 && n < SHADOW_PRESETS.length ? n : 1
  })
  const [opacityIndex, setOpacityIndex] = useState(() => {
    const saved = localStorage.getItem('cd_opacity')
    const n = parseInt(saved || '0', 10)
    return n >= 0 && n < OPACITY_PRESETS.length ? n : 0
  })
  const [skinIndex, setSkinIndex] = useState(() => {
    const saved = localStorage.getItem('cd_skin')
    const n = parseInt(saved || '0', 10)
    return n >= 0 && n < SKIN_PRESETS.length ? n : 0
  })

  // 同步主题和 CSS 变量
  useEffect(() => {
    const root = document.documentElement
    if (effectiveTheme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
    localStorage.setItem('cd_theme', theme)
  }, [theme, effectiveTheme])

  // 同步主题色
  useEffect(() => {
    const preset = ACCENT_PRESETS[accentIndex]
    const root = document.documentElement
    root.style.setProperty('--cd-green', effectiveTheme === 'dark' ? preset.dark : preset.light)
    root.style.setProperty('--cd-green-light', effectiveTheme === 'dark' ? preset.darkBg : preset.lightBg)
    // dark mode 变体
    if (effectiveTheme === 'dark') {
      root.style.setProperty('--cd-green-dark', preset.dark)
    } else {
      root.style.setProperty('--cd-green-dark', preset.light)
    }
    // purple 同步用于某些装饰元素
    root.style.setProperty('--cd-purple', effectiveTheme === 'dark' ? preset.dark : preset.light)
    root.style.setProperty('--cd-purple-light', effectiveTheme === 'dark' ? preset.darkBg : preset.lightBg)
    localStorage.setItem('cd_accent', String(accentIndex))
  }, [accentIndex, effectiveTheme])

  // 同步字体
  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty('--cd-font', FONT_PRESETS[fontIndex].value)
    localStorage.setItem('cd_font', String(fontIndex))
  }, [fontIndex])

  // 同步圆角
  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty('--cd-radius', RADIUS_PRESETS[radiusIndex].value)
    localStorage.setItem('cd_radius', String(radiusIndex))
  }, [radiusIndex])

  // 同步阴影
  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty('--cd-shadow', SHADOW_PRESETS[shadowIndex].value)
    localStorage.setItem('cd_shadow', String(shadowIndex))
  }, [shadowIndex])

  // 同步界面透明度
  useEffect(() => {
    const root = document.documentElement
    root.style.setProperty('--cd-opacity', String(OPACITY_PRESETS[opacityIndex].value))
    localStorage.setItem('cd_opacity', String(opacityIndex))
  }, [opacityIndex])

  // 同步侧边栏毛玻璃
  useEffect(() => {
    const root = document.documentElement
    const opacity = OPACITY_PRESETS[opacityIndex].value
    if (sidebarTranslucent) {
      const isHanmo = SKIN_PRESETS[skinIndex].value === 'hanmo'
      if (effectiveTheme === 'dark') {
        root.style.setProperty('--cd-sidebar-bg', isHanmo ? `rgba(30,26,22,${opacity})` : `rgba(24,24,24,${opacity})`)
      } else {
        root.style.setProperty('--cd-sidebar-bg', isHanmo ? `rgba(247,243,237,${opacity})` : `rgba(250,250,250,${opacity})`)
      }
      root.style.setProperty('--cd-sidebar-blur', 'blur(20px) saturate(180%)')
    } else {
      root.style.removeProperty('--cd-sidebar-bg')
      root.style.removeProperty('--cd-sidebar-blur')
    }
    localStorage.setItem('cd_sidebar_translucent', sidebarTranslucent ? '1' : '0')
  }, [sidebarTranslucent, effectiveTheme, opacityIndex, skinIndex])

  // 同步皮肤（经典 / 翰墨）
  useEffect(() => {
    const root = document.documentElement
    if (SKIN_PRESETS[skinIndex].value === 'hanmo') {
      root.classList.add('skin-hanmo')
    } else {
      root.classList.remove('skin-hanmo')
    }
    localStorage.setItem('cd_skin', String(skinIndex))
  }, [skinIndex])

  // P14-1：三态循环 light → dark → auto → light
  const toggleTheme = useCallback(() => setTheme(prev => prev === 'light' ? 'dark' : prev === 'dark' ? 'auto' : 'light'), [])
  const setThemeExplicit = useCallback((t: Theme) => setTheme(t), [])

  return (
    <ThemeContext.Provider value={{
      theme, effectiveTheme, toggleTheme, setThemeExplicit,
      accentIndex, setAccentIndex,
      fontIndex, setFontIndex,
      sidebarTranslucent, setSidebarTranslucent,
      radiusIndex, setRadiusIndex,
      shadowIndex, setShadowIndex,
      opacityIndex, setOpacityIndex,
      skinIndex, setSkinIndex,
    }}>
      {children}
    </ThemeContext.Provider>
  )
}
