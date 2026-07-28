import { useState, useEffect, useRef, useCallback } from 'react'
import { Clock, Type, Palette, Timer, Copy, Check, ArrowRight } from 'lucide-react'

// ── ToolCard shell ──
function ToolCard({ icon: Icon, title, accentColor, children }: {
  icon: typeof Clock
  title: string
  accentColor: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-cd-bg-secondary border border-cd-border rounded-xl p-5 hover:border-cd-green/30 transition-colors">
      <div className="flex items-center gap-3 mb-4">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: `${accentColor}22`, color: accentColor }}
        >
          <Icon size={18} />
        </div>
        <h3 className="text-sm font-semibold text-cd-text">{title}</h3>
      </div>
      {children}
    </div>
  )
}

// ── Copy button ──
function CopyBtn({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }
  return (
    <button onClick={handleCopy} className="text-cd-text-tertiary hover:text-cd-text transition" title="复制">
      {copied ? <Check size={14} className="text-cd-green" /> : <Copy size={14} />}
    </button>
  )
}

// ── Input style ──
const inputCls =
  'w-full bg-cd-bg border border-cd-border rounded-lg px-3 py-2 text-sm text-cd-text focus:outline-none focus:border-cd-green transition'
const btnCls =
  'px-3 py-1.5 rounded-lg text-xs font-medium transition border border-cd-border bg-cd-bg-secondary text-cd-text-secondary hover:text-cd-text hover:border-cd-green/40'
const labelCls = 'block text-[11px] text-cd-text-tertiary mb-1'

// ═══════════════════════════════════════════════════
// 1. 时间计算器
// ═══════════════════════════════════════════════════
function TimeCalculator() {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [diff, setDiff] = useState<{ hours: number; minutes: number; totalMin: number } | null>(null)

  const calc = (s: string, e: string) => {
    if (!s || !e) { setDiff(null); return }
    const [sh, sm] = s.split(':').map(Number)
    const [eh, em] = e.split(':').map(Number)
    if (isNaN(sh) || isNaN(sm) || isNaN(eh) || isNaN(em)) { setDiff(null); return }
    let startMin = sh * 60 + sm
    let endMin = eh * 60 + em
    if (endMin < startMin) endMin += 24 * 60
    const total = endMin - startMin
    setDiff({ hours: Math.floor(total / 60), minutes: total % 60, totalMin: total })
  }

  const fillNowToEnd = () => {
    const now = new Date()
    const h = String(now.getHours()).padStart(2, '0')
    const m = String(now.getMinutes()).padStart(2, '0')
    const nowStr = `${h}:${m}`
    setStart(nowStr)
    setEnd('18:00')
    calc(nowStr, '18:00')
  }

  useEffect(() => { calc(start, end) }, [start, end])

  return (
    <ToolCard icon={Clock} title="时间计算器" accentColor="#10b981">
      <div className="space-y-3">
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className={labelCls}>开始时间</label>
            <input type="time" value={start} onChange={e => setStart(e.target.value)} className={inputCls} />
          </div>
          <ArrowRight size={16} className="text-cd-text-tertiary shrink-0 mb-2" />
          <div className="flex-1">
            <label className={labelCls}>结束时间</label>
            <input type="time" value={end} onChange={e => setEnd(e.target.value)} className={inputCls} />
          </div>
        </div>
        <button onClick={fillNowToEnd} className={btnCls + ' w-full'}>
          现在到 18:00 还有多久？
        </button>
        {diff && (
          <div className="bg-cd-bg rounded-lg p-3 border border-cd-border">
            <div className="text-2xl font-bold text-cd-text tabular-nums">
              {diff.hours}<span className="text-sm font-normal text-cd-text-tertiary ml-1">时</span>
              {' '}
              {String(diff.minutes).padStart(2, '0')}<span className="text-sm font-normal text-cd-text-tertiary ml-1">分</span>
            </div>
            <div className="text-xs text-cd-text-tertiary mt-1">共 {diff.totalMin} 分钟</div>
          </div>
        )}
      </div>
    </ToolCard>
  )
}

// ═══════════════════════════════════════════════════
// 2. 文本处理
// ═══════════════════════════════════════════════════
function TextProcessor() {
  const [text, setText] = useState('')
  const [caseMode, setCaseMode] = useState<'upper' | 'lower' | 'capitalize'>('upper')

  const stats = {
    chars: text.length,
    charsNoSpace: text.replace(/\s/g, '').length,
    lines: text ? text.split('\n').length : 0,
    words: text.trim() ? text.trim().split(/\s+/).length : 0,
  }

  const dedupLines = () => {
    const lines = text.split('\n')
    const seen = new Set<string>()
    const result: string[] = []
    for (const l of lines) {
      if (!seen.has(l)) { seen.add(l); result.push(l) }
    }
    setText(result.join('\n'))
  }

  const convertCase = () => {
    if (caseMode === 'upper') setText(text.toUpperCase())
    else if (caseMode === 'lower') setText(text.toLowerCase())
    else setText(text.replace(/\b\w/g, c => c.toUpperCase()))
  }

  const formatJson = () => {
    try {
      setText(JSON.stringify(JSON.parse(text), null, 2))
    } catch {
      setText('⚠ JSON 格式无效')
    }
  }

  return (
    <ToolCard icon={Type} title="文本处理" accentColor="#3b82f6">
      <div className="space-y-3">
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          rows={4}
          placeholder="在此输入或粘贴文本..."
          className={inputCls + ' resize-none font-mono text-xs'}
        />
        <div className="grid grid-cols-4 gap-2 text-center">
          {[
            { label: '字符', value: stats.chars },
            { label: '无空格', value: stats.charsNoSpace },
            { label: '行数', value: stats.lines },
            { label: '词数', value: stats.words },
          ].map(s => (
            <div key={s.label} className="bg-cd-bg rounded-lg p-2 border border-cd-border">
              <div className="text-lg font-bold text-cd-text tabular-nums">{s.value}</div>
              <div className="text-[10px] text-cd-text-tertiary">{s.label}</div>
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={dedupLines} className={btnCls}>去重行</button>
          <select
            value={caseMode}
            onChange={e => setCaseMode(e.target.value as typeof caseMode)}
            className={`${inputCls} !w-auto !py-1.5 !px-2 text-xs`}
          >
            <option value="upper">转大写</option>
            <option value="lower">转小写</option>
            <option value="capitalize">首字母大写</option>
          </select>
          <button onClick={convertCase} className={btnCls}>转换</button>
          <button onClick={formatJson} className={btnCls}>JSON 格式化</button>
        </div>
      </div>
    </ToolCard>
  )
}

// ═══════════════════════════════════════════════════
// 3. 颜色选择器
// ═══════════════════════════════════════════════════
function ColorPicker() {
  const [hex, setHex] = useState('#10b981')
  const colorRef = useRef<HTMLInputElement>(null)

  const hexToRgb = (h: string) => {
    const c = h.replace('#', '')
    const r = parseInt(c.substring(0, 2), 16)
    const g = parseInt(c.substring(2, 4), 16)
    const b = parseInt(c.substring(4, 6), 16)
    if (isNaN(r) || isNaN(g) || isNaN(b)) return null
    return { r, g, b }
  }

  const rgbToHsl = (r: number, g: number, b: number) => {
    r /= 255; g /= 255; b /= 255
    const max = Math.max(r, g, b), min = Math.min(r, g, b)
    const l = (max + min) / 2
    if (max === min) return { h: 0, s: 0, l: Math.round(l * 100) }
    const d = max - min
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    let h = 0
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6
    else if (max === g) h = ((b - r) / d + 2) / 6
    else h = ((r - g) / d + 4) / 6
    return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) }
  }

  const rgb = hexToRgb(hex)
  const hsl = rgb ? rgbToHsl(rgb.r, rgb.g, rgb.b) : null
  const rgbStr = rgb ? `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})` : ''
  const hslStr = hsl ? `hsl(${hsl.h}, ${hsl.s}%, ${hsl.l}%)` : ''

  return (
    <ToolCard icon={Palette} title="颜色选择器" accentColor="#a855f7">
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div
            className="w-12 h-12 rounded-lg border border-cd-border cursor-pointer shrink-0"
            style={{ backgroundColor: hex }}
            onClick={() => colorRef.current?.click()}
          />
          <input
            ref={colorRef}
            type="color"
            value={hex.length === 7 ? hex : '#10b981'}
            onChange={e => setHex(e.target.value)}
            className="hidden"
          />
          <div className="flex-1">
            <label className={labelCls}>HEX</label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={hex}
                onChange={e => {
                  let v = e.target.value
                  if (v && !v.startsWith('#')) v = '#' + v
                  setHex(v)
                }}
                maxLength={7}
                className={inputCls + ' font-mono'}
                placeholder="#10b981"
              />
              <CopyBtn value={hex} />
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-cd-bg rounded-lg p-2 border border-cd-border">
            <div className="text-[10px] text-cd-text-tertiary mb-0.5">RGB</div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-cd-text">{rgbStr || '—'}</span>
              {rgbStr && <CopyBtn value={rgbStr} />}
            </div>
          </div>
          <div className="bg-cd-bg rounded-lg p-2 border border-cd-border">
            <div className="text-[10px] text-cd-text-tertiary mb-0.5">HSL</div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-cd-text">{hslStr || '—'}</span>
              {hslStr && <CopyBtn value={hslStr} />}
            </div>
          </div>
        </div>
      </div>
    </ToolCard>
  )
}

// ═══════════════════════════════════════════════════
// 4. 倒计时器
// ═══════════════════════════════════════════════════
function CountdownTimer() {
  const [minutes, setMinutes] = useState(25)
  const [totalSec, setTotalSec] = useState(0)
  const [remaining, setRemaining] = useState(0)
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const clear = useCallback(() => {
    if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null }
  }, [])

  useEffect(() => { return () => clear() }, [clear])

  useEffect(() => {
    if (!running || remaining <= 0) return
    intervalRef.current = setInterval(() => {
      setRemaining(prev => {
        if (prev <= 1) {
          clear()
          setRunning(false)
          setDone(true)
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => clear()
  }, [running, remaining, clear])

  const startTimer = () => {
    const sec = minutes * 60
    if (sec <= 0) return
    setTotalSec(sec)
    setRemaining(sec)
    setRunning(true)
    setDone(false)
  }

  const pauseResume = () => {
    if (running) { clear(); setRunning(false) }
    else { setRunning(true) }
  }

  const reset = () => {
    clear()
    setRunning(false)
    setRemaining(0)
    setTotalSec(0)
    setDone(false)
  }

  const displayMin = Math.floor(remaining / 60)
  const displaySec = remaining % 60
  const progress = totalSec > 0 ? ((totalSec - remaining) / totalSec) * 100 : 0

  return (
    <ToolCard icon={Timer} title="倒计时器" accentColor="#f59e0b">
      <div className="space-y-3">
        {totalSec === 0 ? (
          <>
            <div>
              <label className={labelCls}>分钟数</label>
              <input
                type="number"
                min={1}
                max={999}
                value={minutes}
                onChange={e => setMinutes(Math.max(1, parseInt(e.target.value) || 1))}
                className={inputCls}
              />
            </div>
            <div className="flex gap-2">
              {[5, 15, 25, 45, 60].map(m => (
                <button
                  key={m}
                  onClick={() => setMinutes(m)}
                  className={`flex-1 px-2 py-1.5 rounded-lg text-xs font-medium border transition ${
                    minutes === m
                      ? 'bg-cd-green/15 text-cd-green border-cd-green/30'
                      : 'border-cd-border text-cd-text-secondary hover:text-cd-text hover:border-cd-green/40'
                  }`}
                >
                  {m}m
                </button>
              ))}
            </div>
            <button onClick={startTimer} className="w-full px-4 py-2 bg-cd-green text-white rounded-lg text-sm font-medium hover:opacity-90 transition">
              开始倒计时
            </button>
          </>
        ) : (
          <>
            <div className="text-center">
              <div className={`text-4xl font-bold tabular-nums ${done ? 'text-cd-green' : 'text-cd-text'}`}>
                {String(displayMin).padStart(2, '0')}:{String(displaySec).padStart(2, '0')}
              </div>
              {done && <div className="text-sm text-cd-green mt-1">倒计时结束！</div>}
            </div>
            <div className="w-full h-2 bg-cd-bg rounded-full overflow-hidden">
              <div
                className="h-full bg-cd-green rounded-full transition-all duration-1000 ease-linear"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex gap-2">
              {!done && (
                <button onClick={pauseResume} className="flex-1 px-4 py-2 bg-cd-bg-secondary text-cd-text border border-cd-border rounded-lg text-sm hover:text-cd-text transition">
                  {running ? '暂停' : '继续'}
                </button>
              )}
              <button onClick={reset} className="flex-1 px-4 py-2 bg-cd-bg-secondary text-cd-text-secondary border border-cd-border rounded-lg text-sm hover:text-cd-text transition">
                重置
              </button>
            </div>
          </>
        )}
      </div>
    </ToolCard>
  )
}

// ═══════════════════════════════════════════════════
// Main Page
// ═══════════════════════════════════════════════════
export default function Toolbox() {
  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-cd-text flex items-center gap-2">
          <span className="text-cd-green">🧰</span> 效率工具箱
        </h1>
        <p className="text-sm text-cd-text-tertiary mt-1">
          几个常用小工具，时间计算、文本处理、颜色拾取、倒计时，即开即用
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <TimeCalculator />
        <TextProcessor />
        <ColorPicker />
        <CountdownTimer />
      </div>
    </div>
  )
}
