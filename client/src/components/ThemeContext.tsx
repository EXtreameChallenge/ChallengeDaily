import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'

type Theme = 'light' | 'dark'

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
  { name: '默认', value: "'Anthropic Sans', 'FZQingKeBenYueSong', 'Microsoft YaHei', 'PingFang SC', sans-serif" },
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

interface ThemeCtx {
  theme: Theme
  toggleTheme: () => void
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
}

const ThemeContext = createContext<ThemeCtx>({
  theme: 'light', toggleTheme: () => {},
  accentIndex: 0, setAccentIndex: () => {},
  fontIndex: 0, setFontIndex: () => {},
  sidebarTranslucent: false, setSidebarTranslucent: () => {},
  radiusIndex: 1, setRadiusIndex: () => {},
  shadowIndex: 1, setShadowIndex: () => {},
  opacityIndex: 0, setOpacityIndex: () => {},
})

export function useTheme() {
  return useContext(ThemeContext)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('cd_theme')
    if (saved === 'dark' || saved === 'light') return saved
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })
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

  // 同步主题和 CSS 变量
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
    localStorage.setItem('cd_theme', theme)
  }, [theme])

  // 同步主题色
  useEffect(() => {
    const preset = ACCENT_PRESETS[accentIndex]
    const root = document.documentElement
    root.style.setProperty('--cd-green', theme === 'dark' ? preset.dark : preset.light)
    root.style.setProperty('--cd-green-light', theme === 'dark' ? preset.darkBg : preset.lightBg)
    // dark mode 变体
    if (theme === 'dark') {
      root.style.setProperty('--cd-green-dark', preset.dark)
    } else {
      root.style.setProperty('--cd-green-dark', preset.light)
    }
    // purple 同步用于某些装饰元素
    root.style.setProperty('--cd-purple', theme === 'dark' ? preset.dark : preset.light)
    root.style.setProperty('--cd-purple-light', theme === 'dark' ? preset.darkBg : preset.lightBg)
    localStorage.setItem('cd_accent', String(accentIndex))
  }, [accentIndex, theme])

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
      root.style.setProperty('--cd-sidebar-bg', theme === 'dark' ? `rgba(24,24,24,${opacity})` : `rgba(250,250,250,${opacity})`)
      root.style.setProperty('--cd-sidebar-blur', 'blur(20px) saturate(180%)')
    } else {
      root.style.removeProperty('--cd-sidebar-bg')
      root.style.removeProperty('--cd-sidebar-blur')
    }
    localStorage.setItem('cd_sidebar_translucent', sidebarTranslucent ? '1' : '0')
  }, [sidebarTranslucent, theme, opacityIndex])

  const toggleTheme = useCallback(() => setTheme(prev => prev === 'light' ? 'dark' : 'light'), [])

  return (
    <ThemeContext.Provider value={{
      theme, toggleTheme,
      accentIndex, setAccentIndex,
      fontIndex, setFontIndex,
      sidebarTranslucent, setSidebarTranslucent,
      radiusIndex, setRadiusIndex,
      shadowIndex, setShadowIndex,
      opacityIndex, setOpacityIndex,
    }}>
      {children}
    </ThemeContext.Provider>
  )
}
