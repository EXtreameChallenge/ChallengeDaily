import { useState, useEffect, useCallback } from 'react'
import { get, post } from '../api/client'

interface KeyStat {
  key: string
  count: number
}

// 键盘布局（标准QWERTY）
const KEYBOARD_ROWS = [
  ['Esc', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12'],
  ['`', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-', '=', 'Backspace'],
  ['Tab', 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '[', ']', '\\'],
  ['CapsLock', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ';', "'", 'Enter'],
  ['Shift', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/', 'Shift'],
  ['Ctrl', 'Win', 'Alt', 'Space', 'Alt', 'Fn', 'Ctrl'],
]

export default function KeyboardHeatmap() {
  const [stats, setStats] = useState<Record<string, number>>({})
  const [hotkeys, setHotkeys] = useState<KeyStat[]>([])
  const [listening, setListening] = useState(false)
  const [soundEnabled, setSoundEnabled] = useState(false)
  const [loading, setLoading] = useState(true)

  const fetchData = useCallback(async () => {
    try {
      const data = await get('/api/keyboard/stats')
      setStats(data.stats || {})
      setHotkeys(data.hotkeys || [])
    } catch { /* 后端未启动 */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const timer = setInterval(fetchData, 5000)
    return () => clearInterval(timer)
  }, [fetchData])

  const toggleListening = async () => {
    try {
      if (listening) {
        await post('/api/keyboard/stop')
        setListening(false)
      } else {
        await post('/api/keyboard/start')
        setListening(true)
      }
    } catch { /* ignore */ }
  }

  const toggleSound = async () => {
    try {
      const data = await post('/api/keyboard/sound/toggle', { enabled: !soundEnabled })
      setSoundEnabled(data.enabled)
    } catch { /* ignore */ }
  }

  const resetStats = async () => {
    try {
      await post('/api/keyboard/reset')
      fetchData()
    } catch { /* ignore */ }
  }

  // 计算热度颜色（基于最大count）
  const maxCount = Math.max(...Object.values(stats), 1)
  const getHeatColor = (count: number) => {
    if (count === 0) return 'transparent'
    const ratio = count / maxCount
    // 从浅蓝到深红的渐变
    if (ratio < 0.1) return 'rgba(102, 126, 234, 0.15)'
    if (ratio < 0.25) return 'rgba(102, 126, 234, 0.3)'
    if (ratio < 0.5) return 'rgba(239, 68, 68, 0.4)'
    if (ratio < 0.75) return 'rgba(239, 68, 68, 0.6)'
    return 'rgba(220, 38, 38, 0.85)'
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">⌨️ 键盘热力图</h1>
        <div className="flex gap-2">
          <button
            onClick={toggleListening}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              listening ? 'bg-red-500 text-white' : 'bg-green-500 text-white'
            }`}
          >
            {listening ? '停止监听' : '开始监听'}
          </button>
          <button
            onClick={toggleSound}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              soundEnabled ? 'bg-purple-500 text-white' : 'bg-gray-200 text-gray-700'
            }`}
          >
            🔊 机械音效: {soundEnabled ? '开' : '关'}
          </button>
          <button
            onClick={resetStats}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-gray-200 text-gray-700"
          >
            重置统计
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-20 text-gray-500">加载中...</div>
      ) : (
        <>
          {/* 键盘热力图 */}
          <div className="bg-white rounded-xl shadow p-6 mb-6">
            <div className="flex flex-col items-center gap-1">
              {KEYBOARD_ROWS.map((row, i) => (
                <div key={i} className="flex gap-1">
                  {row.map(key => (
                    <div
                      key={key}
                      className="w-12 h-12 rounded flex items-center justify-center text-xs font-medium border border-gray-200 transition-colors"
                      style={{
                        backgroundColor: getHeatColor(stats[key] || 0),
                        minWidth: key.length > 3 ? '60px' : undefined,
                      }}
                      title={`${key}: ${stats[key] || 0} 次`}
                    >
                      {key}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {/* 热门按键 Top 20 */}
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-lg font-semibold mb-4">🔥 热门按键 Top 20</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {hotkeys.map((item, i) => (
                <div key={item.key} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                  <span className="text-gray-400 text-sm w-6">#{i + 1}</span>
                  <span className="font-mono font-bold w-8">{item.key}</span>
                  <span className="ml-auto text-sm text-gray-600">{item.count}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
