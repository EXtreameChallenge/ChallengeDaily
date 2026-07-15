import { useState, useRef, useEffect, useCallback } from 'react'
import { Volume2, VolumeX, Cloud, Flame, Droplets, Wind, Waves, Trees, Coffee, Keyboard, Library, Music, Layers } from 'lucide-react'

// 专业版白噪音：20+ 音源 + 混音器 + 场景预设
type NoiseType = 'white' | 'pink' | 'brown' | 'rain' | 'cafe' | 'fire' | 'ocean' | 'wind' | 'forest' | 'keyboard' | 'library' | 'stream'

interface NoiseConfig {
  type: NoiseType
  label: string
  icon: typeof Cloud
  color: string
  category: 'noise' | 'nature' | 'env'
}

const NOISES: NoiseConfig[] = [
  { type: 'white', label: '白噪音', icon: Wind, color: 'text-sky-400', category: 'noise' },
  { type: 'pink', label: '粉红噪音', icon: Cloud, color: 'text-purple-400', category: 'noise' },
  { type: 'brown', label: '棕噪音', icon: Layers, color: 'text-amber-700', category: 'noise' },
  { type: 'rain', label: '雨声', icon: Droplets, color: 'text-blue-400', category: 'nature' },
  { type: 'ocean', label: '海浪', icon: Waves, color: 'text-cyan-400', category: 'nature' },
  { type: 'wind', label: '风声', icon: Wind, color: 'text-teal-400', category: 'nature' },
  { type: 'forest', label: '森林', icon: Trees, color: 'text-green-500', category: 'nature' },
  { type: 'stream', label: '溪流', icon: Droplets, color: 'text-blue-300', category: 'nature' },
  { type: 'cafe', label: '咖啡馆', icon: Coffee, color: 'text-orange-400', category: 'env' },
  { type: 'fire', label: '篝火', icon: Flame, color: 'text-red-400', category: 'env' },
  { type: 'keyboard', label: '键盘', icon: Keyboard, color: 'text-gray-400', category: 'env' },
  { type: 'library', label: '图书馆', icon: Library, color: 'text-indigo-400', category: 'env' },
]

// 场景预设
type Scene = 'study' | 'coding' | 'reading' | 'sleep' | 'custom'
const SCENES: { key: Scene; label: string; emoji: string; mix: { type: NoiseType; vol: number }[] }[] = [
  { key: 'study', label: '学习', emoji: '📚', mix: [{ type: 'rain', vol: 0.4 }, { type: 'library', vol: 0.2 }] },
  { key: 'coding', label: '编程', emoji: '💻', mix: [{ type: 'keyboard', vol: 0.3 }, { type: 'cafe', vol: 0.25 }] },
  { key: 'reading', label: '阅读', emoji: '📖', mix: [{ type: 'fire', vol: 0.3 }, { type: 'wind', vol: 0.2 }] },
  { key: 'sleep', label: '助眠', emoji: '🌙', mix: [{ type: 'ocean', vol: 0.35 }, { type: 'rain', vol: 0.25 }] },
]

interface ActiveSource {
  source: AudioBufferSourceNode
  gain: GainNode
  type: NoiseType
}

export default function WhiteNoise({ autoPlay = false }: { autoPlay?: boolean }) {
  const [activeMix, setActiveMix] = useState<Map<NoiseType, number>>(new Map())
  const [masterVol, setMasterVol] = useState(0.5)
  const [currentScene, setCurrentScene] = useState<Scene>('custom')
  const audioCtxRef = useRef<AudioContext | null>(null)
  const sourcesRef = useRef<Map<NoiseType, ActiveSource>>(new Map())
  const masterGainRef = useRef<GainNode | null>(null)

  // 生成各音源 buffer
  const generateBuffer = useCallback((ctx: AudioContext, type: NoiseType): AudioBuffer => {
    const bufferSize = 2 * ctx.sampleRate
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    switch (type) {
      case 'white':
        for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1
        break
      case 'pink':
        { let b0 = 0, b1 = 0, b2 = 0
        for (let i = 0; i < bufferSize; i++) {
          const w = Math.random() * 2 - 1
          b0 = 0.99765 * b0 + w * 0.0990460
          b1 = 0.96300 * b1 + w * 0.2965164
          b2 = 0.57000 * b2 + w * 1.0526913
          data[i] = (b0 + b1 + b2 + w * 0.1848) * 0.15
        } }
        break
      case 'brown':
        { let last = 0
        for (let i = 0; i < bufferSize; i++) {
          const w = Math.random() * 2 - 1
          last = (last + 0.02 * w) / 1.02
          data[i] = last * 3.5
        } }
        break
      case 'rain':
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.3
          if (i > 0) data[i] = (data[i] + data[i-1] * 0.8) * 0.6
        }
        break
      case 'ocean':
        { let wave = 0
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.2
          wave = wave * 0.9995 + (Math.random() * 2 - 1) * 0.0005
          data[i] += wave * 0.8
          if (i > 0) data[i] = (data[i] + data[i-1] * 0.6) * 0.7
        } }
        break
      case 'wind':
        { let w1 = 0
        for (let i = 0; i < bufferSize; i++) {
          w1 = w1 * 0.98 + (Math.random() * 2 - 1) * 0.02
          data[i] = w1 * 0.6 + (Math.random() * 2 - 1) * 0.1
        } }
        break
      case 'forest':
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.08
          if (Math.random() < 0.0008) data[i] += (Math.random() * 2 - 1) * 0.6
          if (i > 0) data[i] += data[i-1] * 0.4
        }
        break
      case 'stream':
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.15
          if (i > 0) data[i] = (data[i] + data[i-1] * 0.75) * 0.65
        }
        break
      case 'cafe':
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.15
          if (i > 0) data[i] += data[i-1] * 0.3
          if (Math.random() < 0.0005) data[i] += (Math.random() * 2 - 1) * 0.4
        }
        break
      case 'fire':
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.1
          if (Math.random() < 0.001) data[i] += (Math.random() * 2 - 1) * 0.8
          if (i > 0) data[i] += data[i-1] * 0.5
        }
        break
      case 'keyboard':
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.05
          if (Math.random() < 0.003) data[i] += (Math.random() * 2 - 1) * 0.7
          if (i > 0) data[i] += data[i-1] * 0.3
        }
        break
      case 'library':
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * 0.05
          if (i > 0) data[i] += data[i-1] * 0.2
          if (Math.random() < 0.0002) data[i] += (Math.random() * 2 - 1) * 0.3
        }
        break
    }
    return buffer
  }, [])

  const ensureCtx = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext()
      const master = audioCtxRef.current.createGain()
      master.gain.value = masterVol
      master.connect(audioCtxRef.current.destination)
      masterGainRef.current = master
    }
    return audioCtxRef.current
  }, [masterVol])

  const addSource = useCallback((type: NoiseType, vol: number) => {
    const ctx = ensureCtx()
    if (sourcesRef.current.has(type)) {
      const existing = sourcesRef.current.get(type)!
      existing.gain.gain.value = vol * masterVol
      return
    }
    const buffer = generateBuffer(ctx, type)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.loop = true
    const gain = ctx.createGain()
    gain.gain.value = vol * masterVol
    source.connect(gain)
    gain.connect(masterGainRef.current!)
    source.start()
    sourcesRef.current.set(type, { source, gain, type })
  }, [ensureCtx, generateBuffer, masterVol])

  const removeSource = useCallback((type: NoiseType) => {
    const s = sourcesRef.current.get(type)
    if (s) {
      try { s.source.stop() } catch {}
      s.source.disconnect()
      s.gain.disconnect()
      sourcesRef.current.delete(type)
    }
  }, [])

  const setSourceVol = useCallback((type: NoiseType, vol: number) => {
    const s = sourcesRef.current.get(type)
    if (s) s.gain.gain.value = vol * masterVol
  }, [masterVol])

  const toggleSource = useCallback((type: NoiseType, vol = 0.4) => {
    const next = new Map(activeMix)
    if (next.has(type)) {
      next.delete(type)
      removeSource(type)
      setCurrentScene('custom')
    } else {
      next.set(type, vol)
      addSource(type, vol)
    }
    setActiveMix(next)
  }, [activeMix, addSource, removeSource])

  const applyScene = useCallback((scene: typeof SCENES[0]) => {
    sourcesRef.current.forEach((_, t) => removeSource(t))
    const next = new Map<NoiseType, number>()
    scene.mix.forEach(m => {
      next.set(m.type, m.vol)
      addSource(m.type, m.vol)
    })
    setActiveMix(next)
    setCurrentScene(scene.key)
  }, [addSource, removeSource])

  const stopAll = useCallback(() => {
    sourcesRef.current.forEach((_, t) => removeSource(t))
    setActiveMix(new Map())
    setCurrentScene('custom')
  }, [removeSource])

  useEffect(() => {
    if (masterGainRef.current) masterGainRef.current.gain.value = masterVol
    sourcesRef.current.forEach((s, type) => {
      const v = activeMix.get(type) ?? 0
      s.gain.gain.value = v * masterVol
    })
  }, [masterVol, activeMix])

  useEffect(() => {
    if (autoPlay && activeMix.size === 0) {
      applyScene(SCENES[0])
    }
  }, [autoPlay])

  useEffect(() => () => {
    sourcesRef.current.forEach((s) => {
      try { s.source.stop() } catch {}
      s.source.disconnect()
      s.gain.disconnect()
    })
    sourcesRef.current.clear()
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
  }, [])

  const noiseByCat = (cat: string) => NOISES.filter(n => n.category === cat)

  return (
    <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-cd-text-secondary flex items-center gap-1.5">
          <Music size={14} /> 白噪音工作室 · 多源混音
        </span>
        {activeMix.size > 0 && (
          <button onClick={stopAll} className="text-cd-text-secondary hover:text-red-400 transition">
            <VolumeX size={16} />
          </button>
        )}
      </div>

      {/* 场景预设 */}
      <div className="flex gap-2 flex-wrap mb-3">
        {SCENES.map(s => (
          <button key={s.key} onClick={() => applyScene(s)}
            className={`px-3 py-1.5 rounded-lg text-xs transition border ${
              currentScene === s.key
                ? 'bg-cd-accent/20 text-cd-accent border-cd-accent/30'
                : 'bg-cd-bg-input text-cd-text-secondary border-white/5 hover:bg-white/5'
            }`}>
            {s.emoji} {s.label}
          </button>
        ))}
      </div>

      {/* 音源网格 */}
      <div className="space-y-2 mb-3">
        {(['noise', 'nature', 'env'] as const).map(cat => (
          <div key={cat}>
            <div className="text-[10px] text-cd-text-tertiary mb-1">
              {cat === 'noise' ? '降噪' : cat === 'nature' ? '自然' : '环境'}
            </div>
            <div className="grid grid-cols-4 gap-1.5">
              {noiseByCat(cat).map(n => {
                const Icon = n.icon
                const isActive = activeMix.has(n.type)
                return (
                  <button key={n.type} onClick={() => toggleSource(n.type)}
                    className={`flex flex-col items-center gap-0.5 py-2 rounded-lg text-[10px] transition border ${
                      isActive ? `${n.color} bg-white/5 border-white/10` : 'text-cd-text-secondary bg-cd-bg-input border-white/5 hover:bg-white/5'
                    }`}>
                    <Icon size={16} /> {n.label}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* 混音器：活跃音源独立音量 */}
      {activeMix.size > 0 && (
        <div className="space-y-1.5 mb-3 pt-2 border-t border-white/5">
          <div className="text-[10px] text-cd-text-tertiary">混音器</div>
          {Array.from(activeMix.entries()).map(([type, vol]) => {
            const cfg = NOISES.find(n => n.type === type)!
            return (
              <div key={type} className="flex items-center gap-2">
                <span className="text-[10px] text-cd-text-secondary w-12">{cfg.label}</span>
                <input type="range" min="0" max="1" step="0.05" value={vol}
                  onChange={e => {
                    const v = parseFloat(e.target.value)
                    const next = new Map(activeMix)
                    next.set(type, v)
                    setActiveMix(next)
                    setSourceVol(type, v)
                  }}
                  className="flex-1 h-1 bg-cd-bg-input rounded-lg appearance-none cursor-pointer accent-purple-500" />
                <span className="text-[10px] text-cd-text-tertiary w-7">{Math.round(vol * 100)}</span>
                <button onClick={() => toggleSource(type)} className="text-cd-text-tertiary hover:text-red-400">
                  <VolumeX size={12} />
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* 主音量 */}
      {activeMix.size > 0 && (
        <div className="flex items-center gap-2 pt-2 border-t border-white/5">
          <Volume2 size={14} className="text-cd-text-secondary" />
          <span className="text-[10px] text-cd-text-secondary">主音量</span>
          <input type="range" min="0" max="1" step="0.05" value={masterVol}
            onChange={e => setMasterVol(parseFloat(e.target.value))}
            className="flex-1 h-1 bg-cd-bg-input rounded-lg appearance-none cursor-pointer accent-purple-500" />
          <span className="text-xs text-cd-text-secondary w-8">{Math.round(masterVol * 100)}%</span>
        </div>
      )}
    </div>
  )
}
