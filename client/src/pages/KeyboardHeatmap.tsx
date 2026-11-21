/* eslint-disable @typescript-eslint/no-explicit-any -- 键盘接口返回体为动态 JSON，局部断言即可 */
import { useState, useEffect, useCallback } from 'react'
import { get, post } from '../api/client'

interface KeyStat {
  key: string
  count: number
}

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
  const [msg, setMsg] = useState('')

  const fetchData = useCallback(async () => {
    try {
      const data: any = await get('/api/keyboard/stats')
      setStats(data.stats || {})
      setHotkeys(data.hotkeys || [])
      setListening(!!data.listening)
      if (data.available && !data.available.ok) setMsg(data.available.reason || '')
    } catch { /* ignore */ } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    get('/api/keyboard/sound/status').then((s: any) => setSoundEnabled(!!s?.enabled)).catch(() => {})
    const timer = setInterval(fetchData, 5000)
    return () => clearInterval(timer)
  }, [fetchData])

  const toggleListening = async () => {
    try {
      const res: any = listening ? await post('/api/keyboard/stop') : await post('/api/keyboard/start')
      if (!res?.ok) { setMsg(res?.error || '操作失败'); setListening(false); return }
      setListening(!listening)
      setMsg('')
    } catch (e: any) { setMsg(e?.message || '操作失败') }
  }

  const toggleSound = async () => {
    try {
      const data: any = await post('/api/keyboard/sound/toggle', { enabled: !soundEnabled })
      if (!data?.ok) { setMsg(data?.error || '音效不可用'); return }
      setSoundEnabled(!!data.enabled)
      setMsg('')
    } catch (e: any) { setMsg(e?.message || '音效不可用') }
  }

  const resetStats = async () => {
    try {
      const res: any = await post('/api/keyboard/reset')
      if (!res?.ok) setMsg(res?.error || '重置失败')
      fetchData()
    } catch (e: any) { setMsg(e?.message || '重置失败') }
  }

  const maxCount = Math.max(...Object.values(stats), 1)
  const getHeatColor = (count: number) => {
    if (count === 0) return 'transparent'
    const ratio = count / maxCount
    if (ratio < 0.1) return 'rgba(102, 126, 234, 0.15)'
    if (ratio < 0.25) return 'rgba(102, 126, 234, 0.3)'
    if (ratio < 0.5) return 'rgba(239, 68, 68, 0.4)'
    if (ratio < 0.75) return 'rgba(239, 68, 68, 0.6)'
    return 'rgba(220, 38, 38, 0.85)'
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold">⌨️ 键盘热力图</h1>
          <p className="text-sm text-gray-500 mt-1">统计按键频率，优化打字习惯</p>
          <p className="text-xs text-gray-400 mt-1">
            仅统计按键次数，不记录任何按键内容、不上传按键数据；默认关闭，开启后才监听，关闭即卸载全局钩子。
          </p>
          {msg && <p className="text-xs text-amber-600 mt-1">{msg}</p>}
        </div>
        <div className="flex gap-2">
          <button onClick={toggleListening}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${listening ? 'bg-red-500 text-white' : 'bg-green-500 text-white'}`}>
            {listening ? '⏹ 停止监听' : '▶ 开始监听'}
          </button>
          <button onClick={toggleSound}
            className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${soundEnabled ? 'bg-purple-500 text-white' : 'bg-gray-200 text-gray-700'}`}>
            🔊 {soundEnabled ? '音效开' : '音效关'}
          </button>
          <button onClick={resetStats}
            className="px-4 py-2 rounded-xl text-sm font-medium bg-gray-200 text-gray-700">重置</button>
        </div>
      </div>

      {loading ? <div className="text-center py-20 text-gray-500">加载中...</div> : (
        <>
          <div className="glass rounded-2xl p-6 mb-6">
            <div className="flex flex-col items-center gap-1">
              {KEYBOARD_ROWS.map((row, i) => (
                <div key={i} className="flex gap-1">
                  {row.map(key => (
                    <div key={key}
                      className="w-11 h-11 rounded-lg flex items-center justify-center text-xs font-medium border transition-all"
                      style={{
                        backgroundColor: getHeatColor(stats[key] || 0),
                        borderColor: 'var(--cd-border, #e5e7eb)',
                        minWidth: key.length > 3 ? '56px' : undefined,
                      }}
                      title={`${key}: ${stats[key] || 0} 次`}>
                      {key}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>

          <div className="glass rounded-2xl p-6">
            <h2 className="text-base font-semibold mb-4">🔥 热门按键 Top 20</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {hotkeys.map((item, i) => (
                <div key={item.key} className="flex items-center gap-3 p-3 bg-white/50 rounded-xl">
                  <span className="text-gray-400 text-xs w-6">#{i + 1}</span>
                  <span className="font-mono font-bold text-sm w-8">{item.key}</span>
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
