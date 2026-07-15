import { useState, useEffect, useCallback } from 'react'
import { Users, Wifi, RefreshCw, Trophy, Brain, Coffee, Monitor } from 'lucide-react'
import { getStudyRoomStatus, broadcastStudyRoom, type StudyRoomMember } from '../api/client'
import { useToast } from '../components/Toast'

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: typeof Brain }> = {
  focusing: { label: '专注中', color: 'text-purple-400 bg-purple-400/10', icon: Brain },
  break: { label: '休息中', color: 'text-green-400 bg-green-400/10', icon: Coffee },
  idle: { label: '空闲', color: 'text-cd-text-tertiary bg-white/5', icon: Monitor },
  away: { label: '离开', color: 'text-gray-500 bg-white/5', icon: Monitor },
}

export default function StudyRoom() {
  const [members, setMembers] = useState<StudyRoomMember[]>([])
  const [focusingCount, setFocusingCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [broadcasting, setBroadcasting] = useState(false)
  const { toast } = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getStudyRoomStatus()
      setMembers(data.members)
      setFocusingCount(data.focusing_count)
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, 10000)  // 10秒刷新
    return () => clearInterval(timer)
  }, [load])

  const handleBroadcast = async () => {
    setBroadcasting(true)
    try {
      const result = await broadcastStudyRoom()
      toast('success', `已扫描 ${result.subnet}，发现 ${result.broadcasted} 个设备`)
      setTimeout(load, 2000)
    } catch { toast('error', '广播失败') }
    setBroadcasting(false)
  }

  const sorted = [...members].sort((a, b) => b.today_min - a.today_min)

  return (
    <div className="max-w-5xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-cd-text flex items-center gap-2">
            <Users size={20} className="text-cd-accent" /> 番茄自习室
          </h1>
          <p className="text-sm text-cd-text-secondary mt-1">局域网自动发现 · 一起专注 · 排行榜PK</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-cd-bg-card border border-white/5 text-cd-text-secondary hover:bg-white/5 transition">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> 刷新
          </button>
          <button onClick={handleBroadcast} disabled={broadcasting}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs bg-cd-accent/20 text-cd-accent border border-cd-accent/30 hover:bg-cd-accent/30 transition">
            <Wifi size={12} className={broadcasting ? 'animate-pulse' : ''} /> 扫描局域网
          </button>
        </div>
      </div>

      {/* 状态概览 */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-cd-accent">{members.length}</div>
          <div className="text-sm text-cd-text-secondary mt-1">在线成员</div>
        </div>
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-purple-400">{focusingCount}</div>
          <div className="text-sm text-cd-text-secondary mt-1">正在专注</div>
        </div>
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-2xl font-bold text-orange-400">
            {members.reduce((sum, m) => sum + m.today_min, 0)}
          </div>
          <div className="text-sm text-cd-text-secondary mt-1">全员专注分钟</div>
        </div>
      </div>

      {/* 排行榜 */}
      <div className="bg-cd-bg-card rounded-xl p-5 border border-white/5">
        <h2 className="text-sm font-semibold text-cd-text mb-4 flex items-center gap-2">
          <Trophy size={16} className="text-yellow-400" /> 今日专注排行榜
        </h2>
        {sorted.length === 0 ? (
          <div className="text-center py-8 text-cd-text-tertiary text-sm">
            暂无成员，点击"扫描局域网"发现其他设备
          </div>
        ) : (
          <div className="space-y-2">
            {sorted.map((m, i) => {
              const cfg = STATUS_CONFIG[m.status] || STATUS_CONFIG.idle
              const Icon = cfg.icon
              return (
                <div key={m.id} className={`flex items-center gap-3 p-3 rounded-lg ${
                  m.is_self ? 'bg-cd-accent/10 border border-cd-accent/20' : 'bg-cd-bg-input'
                }`}>
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                    i === 0 ? 'bg-yellow-400/20 text-yellow-400' :
                    i === 1 ? 'bg-gray-300/20 text-gray-300' :
                    i === 2 ? 'bg-orange-700/20 text-orange-600' :
                    'text-cd-text-tertiary'
                  }`}>
                    {i + 1}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-cd-text font-medium">{m.name}</span>
                      {m.is_self && <span className="text-[10px] text-cd-accent">(我)</span>}
                    </div>
                    {m.task && <div className="text-xs text-cd-text-tertiary truncate">{m.task}</div>}
                  </div>
                  <div className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] ${cfg.color}`}>
                    <Icon size={10} /> {cfg.label}
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold text-cd-text">{m.today_min}<span className="text-xs font-normal text-cd-text-tertiary">min</span></div>
                    <div className="text-[10px] text-cd-text-tertiary">{m.today_count} 番茄</div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="text-xs text-cd-text-tertiary text-center mt-4">
        自习室基于局域网自动发现，数据不经过任何服务器 · 每10秒自动刷新
      </div>
    </div>
  )
}
