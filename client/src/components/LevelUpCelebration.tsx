import { useEffect, useRef } from 'react'
import confetti from 'canvas-confetti'

interface Props {
  newLevel: number
  onClose: () => void
}

export default function LevelUpCelebration({ newLevel, onClose }: Props) {
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } })
    const timer = setTimeout(() => onCloseRef.current(), 3000)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-[var(--cd-card)] rounded-2xl p-8 text-center shadow-xl">
        <div className="text-5xl mb-4">🎉</div>
        <div className="text-2xl font-bold mb-2 text-cd-text">升级！</div>
        <div className="text-lg text-emerald-400">Lv.{newLevel - 1} → Lv.{newLevel}</div>
        <div className="text-sm opacity-60 mt-4 text-cd-text-secondary">点击任意处关闭</div>
      </div>
    </div>
  )
}
