import { Moon, Sun } from 'lucide-react'
import { useTheme } from './ThemeContext'

/**
 * ThemeToggle — 独立圆形毛玻璃悬浮按钮
 * 与右上角窗口控件胶囊在同一水平线
 */
export default function ThemeToggle() {
  const { effectiveTheme, toggleTheme } = useTheme()
  const dark = effectiveTheme === 'dark'

  return (
    <button
      onClick={toggleTheme}
      className="theme-toggle-float fixed top-5 z-50 no-drag"
      style={{ right: '148px' }}
      title={dark ? '切换浅色模式' : '切换深色模式'}
    >
      {dark ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  )
}
