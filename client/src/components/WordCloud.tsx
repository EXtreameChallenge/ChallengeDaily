import { useState, useEffect, useRef, useCallback } from 'react'
import { request } from '../api/client'

interface WordItem { text: string; value: number }

export default function WordCloud() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [words, setWords] = useState<WordItem[]>([])
  const [loading, setLoading] = useState(true)

  const loadWords = useCallback(async () => {
    try {
      const data = await request('/api/stats/wordcloud') as { words: WordItem[] }
      setWords(data.words || [])
    } catch {
      setWords([])
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadWords() }, [loadWords])

  // Canvas 绘制词云
  useEffect(() => {
    if (!canvasRef.current || words.length === 0) return
    const canvas = canvasRef.current
    const parent = canvas.parentElement

    const draw = () => {
      const ctx = canvas.getContext('2d')!
      const w = canvas.width = canvas.offsetWidth * 2
      const h = canvas.height = canvas.offsetHeight * 2
      ctx.scale(2, 2)
      ctx.clearRect(0, 0, w, h)

      const colors = ['#7B68EE', '#F0C040', '#22c55e', '#3b82f6', '#ec4899', '#f97316', '#a855f7', '#06b6d4']
      const maxVal = Math.max(...words.map(w => w.value), 1)
      const placed: { x: number; y: number; w: number; h: number }[] = []
      const cw = canvas.offsetWidth, ch = canvas.offsetHeight

      words.slice(0, 40).forEach((word, i) => {
        const size = 12 + (word.value / maxVal) * 28
        ctx.font = `${size}px sans-serif`
        const metrics = ctx.measureText(word.text)
        const ww = metrics.width + 6, hh = size + 4
        let x = 0, y = 0, found = false, attempts = 0
        while (!found && attempts < 50) {
          x = Math.random() * (cw - ww)
          y = Math.random() * (ch - hh) + hh
          found = !placed.some(p => x < p.x + p.w && x + ww > p.x && y < p.y + p.h && y + hh > p.y)
          attempts++
        }
        if (found) {
          placed.push({ x, y, w: ww, h: hh })
          ctx.fillStyle = colors[i % colors.length]
          ctx.globalAlpha = 0.6 + (word.value / maxVal) * 0.4
          ctx.fillText(word.text, x + 3, y - 2)
        }
      })
      ctx.globalAlpha = 1
    }

    draw()

    // 监听父容器尺寸变化时重绘
    if (!parent) return
    const ro = new ResizeObserver(() => draw())
    ro.observe(parent)
    return () => ro.disconnect()
  }, [words])

  if (loading) return <div className="text-center text-cd-text-secondary py-4 text-sm">加载词云...</div>
  if (words.length === 0) return null

  return (
    <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
      <h3 className="text-sm text-cd-text-secondary mb-2">工作关键词</h3>
      <canvas ref={canvasRef} className="w-full h-40" />
    </div>
  )
}
