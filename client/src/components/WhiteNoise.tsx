import { useState, useRef, useEffect, useCallback } from 'react'
import { Volume2, VolumeX, Cloud, Flame, Droplets, Wind } from 'lucide-react'

type NoiseType = 'white' | 'pink' | 'rain' | 'cafe' | 'fire'

const NOISES: { type: NoiseType; label: string; icon: typeof Cloud; color: string }[] = [
  { type: 'white', label: '白噪音', icon: Wind, color: 'text-sky-400' },
  { type: 'pink', label: '粉红噪音', icon: Cloud, color: 'text-purple-400' },
  { type: 'rain', label: '雨声', icon: Droplets, color: 'text-blue-400' },
  { type: 'cafe', label: '咖啡馆', icon: Volume2, color: 'text-orange-400' },
  { type: 'fire', label: '篝火', icon: Flame, color: 'text-red-400' },
]

export default function WhiteNoise({ autoPlay = false }: { autoPlay?: boolean }) {
  const [active, setActive] = useState<NoiseType | null>(null)
  const [volume, setVolume] = useState(0.3)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const sourceRef = useRef<AudioBufferSourceNode | null>(null)
  const gainRef = useRef<GainNode | null>(null)

  const stopNoise = useCallback(() => {
    if (sourceRef.current) {
      try { sourceRef.current.stop() } catch {}
      sourceRef.current.disconnect()
      sourceRef.current = null
    }
    setActive(null)
  }, [])

  const playNoise = useCallback((type: NoiseType) => {
    if (sourceRef.current) {
      try { sourceRef.current.stop() } catch {}
      sourceRef.current.disconnect()
      sourceRef.current = null
    }
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioContext()
      }
      const ctx = audioCtxRef.current
      const bufferSize = 2 * ctx.sampleRate
      const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate)
      const data = buffer.getChannelData(0)

      switch (type) {
        case 'white':
          for (let i = 0; i < bufferSize; i++) data[i] = Math.random() * 2 - 1
          break
        case 'pink':
          let b0 = 0, b1 = 0, b2 = 0
          for (let i = 0; i < bufferSize; i++) {
            const white = Math.random() * 2 - 1
            b0 = 0.99765 * b0 + white * 0.0990460
            b1 = 0.96300 * b1 + white * 0.2965164
            b2 = 0.57000 * b2 + white * 1.0526913
            data[i] = (b0 + b1 + b2 + white * 0.1848) * 0.15
          }
          break
        case 'rain':
          for (let i = 0; i < bufferSize; i++) {
            data[i] = (Math.random() * 2 - 1) * 0.3
            if (i > 0) data[i] = (data[i] + data[i-1] * 0.8) * 0.6
          }
          break
        case 'cafe':
          for (let i = 0; i < bufferSize; i++) {
            data[i] = (Math.random() * 2 - 1) * 0.15
            if (i > 0) data[i] += data[i-1] * 0.3
          }
          break
        case 'fire':
          for (let i = 0; i < bufferSize; i++) {
            data[i] = (Math.random() * 2 - 1) * 0.1
            if (Math.random() < 0.001) data[i] += (Math.random() * 2 - 1) * 0.8
            if (i > 0) data[i] += data[i-1] * 0.5
          }
          break
      }

      const source = ctx.createBufferSource()
      source.buffer = buffer
      source.loop = true
      const gain = ctx.createGain()
      gain.gain.value = volume
      source.connect(gain)
      gain.connect(ctx.destination)
      source.start()
      sourceRef.current = source
      gainRef.current = gain
      setActive(type)
    } catch {}
  }, [volume])

  // 自动播放
  useEffect(() => {
    if (autoPlay && !active) playNoise('pink')
  }, [autoPlay])

  // 音量变化
  useEffect(() => {
    if (gainRef.current) gainRef.current.gain.value = active ? volume : 0
  }, [volume, active])

  // 清理
  useEffect(() => () => {
    if (sourceRef.current) {
      try { sourceRef.current.stop() } catch {}
      sourceRef.current.disconnect()
      sourceRef.current = null
    }
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
  }, [])

  return (
    <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-cd-text-secondary">白噪音 · 专注音效</span>
        {active && (
          <button onClick={stopNoise} className="text-cd-text-secondary hover:text-red-400 transition">
            <VolumeX size={16} />
          </button>
        )}
      </div>
      <div className="flex gap-2 flex-wrap">
        {NOISES.map(n => {
          const Icon = n.icon
          const isActive = active === n.type
          return (
            <button key={n.type} onClick={() => isActive ? stopNoise() : playNoise(n.type)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm transition border ${
                isActive ? `${n.color} bg-white/5 border-white/10` : 'text-cd-text-secondary bg-cd-bg-input border-white/5 hover:bg-white/5'
              }`}>
              <Icon size={14} /> {n.label}
            </button>
          )
        })}
      </div>
      {active && (
        <div className="flex items-center gap-2 mt-3">
          <Volume2 size={14} className="text-cd-text-secondary" />
          <input type="range" min="0" max="1" step="0.05" value={volume}
            onChange={e => setVolume(parseFloat(e.target.value))}
            className="flex-1 h-1 bg-cd-bg-input rounded-lg appearance-none cursor-pointer accent-purple-500" />
          <span className="text-xs text-cd-text-secondary w-8">{Math.round(volume * 100)}%</span>
        </div>
      )}
    </div>
  )
}
