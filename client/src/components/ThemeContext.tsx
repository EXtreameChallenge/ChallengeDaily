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

interface ThemeCtx {
  theme: Theme
  toggleTheme: () => void
  accentIndex: number
  setAccentIndex: (i: number) => void
  fontIndex: number
  setFontIndex: (i: number) => void
  sidebarTranslucent: boolean
  setSidebarTranslucent: (v: boolean) => void
}

const ThemeContext = createContext<ThemeCtx>({
  theme: 'light', toggleTheme: () => {},
  accentIndex: 0, setAccentIndex: () => {},
  fontIndex: 0, setFontIndex: () => {},
  sidebarTranslucent: false, setSidebarTranslucent: () => {},
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

  // 同步侧边栏毛玻璃
  useEffect(() => {
    const root = document.documentElement
    if (sidebarTranslucent) {
      root.style.setProperty('--cd-sidebar-bg', theme === 'dark' ? 'rgba(24,24,24,0.72)' : 'rgba(250,250,250,0.72)')
      root.style.setProperty('--cd-sidebar-blur', 'blur(20px) saturate(180%)')
    } else {
      root.style.removeProperty('--cd-sidebar-bg')
      root.style.removeProperty('--cd-sidebar-blur')
    }
    localStorage.setItem('cd_sidebar_translucent', sidebarTranslucent ? '1' : '0')
  }, [sidebarTranslucent, theme])

  const toggleTheme = useCallback(() => setTheme(prev => prev === 'light' ? 'dark' : 'light'), [])

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, accentIndex, setAccentIndex, fontIndex, setFontIndex, sidebarTranslucent, setSidebarTranslucent }}>
      {children}
    </ThemeContext.Provider>
  )
}
