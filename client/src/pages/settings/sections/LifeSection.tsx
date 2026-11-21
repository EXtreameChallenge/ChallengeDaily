import { Heart } from 'lucide-react'

interface LifeSectionProps {
  birthday: string
  setBirthday: (v: string) => void
  lifeExpectancy: number
  setLifeExpectancy: (v: number) => void
}

export function LifeSection({ birthday, setBirthday, lifeExpectancy, setLifeExpectancy }: LifeSectionProps) {
  return (
      <section className="card space-y-4">
        <div className="flex items-center gap-2">
          <Heart size={16} className="text-cd-green" />
          <h2 className="text-sm font-semibold text-cd-text">人生配置</h2>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          设置生日和预期寿命，开启「人生进度」可视化 — 让每一天都有坐标感。
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">生日</label>
            <input
              type="date"
              value={birthday}
              onChange={(e) => setBirthday(e.target.value)}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
          <div>
            <label className="text-xs text-cd-text-secondary block mb-1">预期寿命（岁）</label>
            <input
              type="number"
              value={lifeExpectancy}
              onChange={(e) => setLifeExpectancy(Number(e.target.value))}
              min={1}
              max={150}
              className="w-full bg-cd-bg-secondary text-cd-text border border-cd-border rounded-2xl px-3 py-1.5 text-sm focus:outline-none focus:border-cd-green transition-colors"
            />
          </div>
        </div>
        <div className="text-xs text-cd-text-tertiary">
          人生进度条将显示在首页顶部信息栏，让你直观感受时间流逝。
        </div>
      </section>
  )
}


