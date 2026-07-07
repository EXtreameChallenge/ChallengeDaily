import { useState, useEffect, useCallback } from 'react'
import { ChevronLeft, ChevronRight, Save, Calendar, Sparkles } from 'lucide-react'
import { getDiary, saveDiary, getDiaries, type Diary as DiaryType } from '../api/client'

const MOODS = [
  { emoji: '😄', label: '开心', color: 'text-yellow-400' },
  { emoji: '😊', label: '平静', color: 'text-green-400' },
  { emoji: '😴', label: '疲惫', color: 'text-blue-400' },
  { emoji: '😤', label: '烦躁', color: 'text-red-400' },
  { emoji: '🤔', label: '思考', color: 'text-purple-400' },
  { emoji: '😎', label: '充实', color: 'text-orange-400' },
  { emoji: '🥱', label: '无聊', color: 'text-gray-400' },
  { emoji: '🥳', label: '兴奋', color: 'text-pink-400' },
]

function formatDate(d: string) {
  const date = new Date(d)
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return `${date.getFullYear()}年${date.getMonth()+1}月${date.getDate()}日 ${weekdays[date.getDay()]}`
}

export default function Diary() {
  const [currentDate, setCurrentDate] = useState(new Date().toISOString().substring(0, 10))
  const [diary, setDiary] = useState<DiaryType | null>(null)
  const [mood, setMood] = useState('')
  const [weather, setWeather] = useState('')
  const [content, setContent] = useState('')
  const [tags, setTags] = useState('')
  const [highlights, setHighlights] = useState('')
  const [gratitude, setGratitude] = useState('')
  const [saving, setSaving] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)
  const [diaryDates, setDiaryDates] = useState<string[]>([])

  const load = useCallback(async () => {
    try {
      const { diary: d } = await getDiary(currentDate)
      setDiary(d)
      setMood(d?.mood || '')
      setWeather(d?.weather || '')
      setContent(d?.content || '')
      setTags(d?.tags || '')
      setHighlights(d?.highlights || '')
      setGratitude(d?.gratitude || '')
    } catch {}
  }, [currentDate])

  const loadDates = useCallback(async () => {
    try {
      const { dates } = await getDiaries(90)
      setDiaryDates(dates)
    } catch {}
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadDates() }, [loadDates])

  const handleSave = async () => {
    setSaving(true)
    try {
      await saveDiary({
        diary_date: currentDate, mood, weather, content, tags, highlights, gratitude,
      })
      setSavedFlash(true)
      setTimeout(() => setSavedFlash(false), 2000)
      loadDates()
    } catch {}
    setSaving(false)
  }

  const goPrev = () => {
    const d = new Date(currentDate)
    d.setDate(d.getDate() - 1)
    setCurrentDate(d.toISOString().substring(0, 10))
  }

  const goNext = () => {
    const d = new Date(currentDate)
    d.setDate(d.getDate() + 1)
    if (d <= new Date()) setCurrentDate(d.toISOString().substring(0, 10))
  }

  const hasDiary = diaryDates.includes(currentDate)

  return (
    <div className="min-h-screen p-6 max-w-3xl mx-auto">
      {/* 顶部导航 */}
      <div className="flex items-center justify-between mb-6">
        <button onClick={goPrev} className="p-2 rounded-lg bg-cd-bg-input border border-white/5 text-cd-text-secondary hover:bg-white/5 transition">
          <ChevronLeft size={20} />
        </button>
        <div className="flex items-center gap-2">
          <Calendar size={18} className="text-purple-400" />
          <h1 className="text-xl font-bold text-cd-text">{formatDate(currentDate)}</h1>
          {hasDiary && <span className="w-2 h-2 rounded-full bg-green-500/60" title="已写日记" />}
        </div>
        <button onClick={goNext} className="p-2 rounded-lg bg-cd-bg-input border border-white/5 text-cd-text-secondary hover:bg-white/5 transition">
          <ChevronRight size={20} />
        </button>
      </div>

      {/* 心情选择 */}
      <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4">
        <div className="text-sm text-cd-text-secondary mb-3">今天的心情</div>
        <div className="flex gap-2 flex-wrap">
          {MOODS.map(m => (
            <button key={m.label} onClick={() => setMood(mood === m.label ? '' : m.label)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border transition ${
                mood === m.label ? `${m.color} bg-white/5 border-white/10` : 'text-cd-text-secondary bg-cd-bg-input border-white/5 hover:bg-white/5'
              }`}>
              <span className="text-base">{m.emoji}</span> {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* 日记内容 */}
      <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4">
        <div className="text-sm text-cd-text-secondary mb-2">日记 · 一日一页</div>
        <textarea value={content} onChange={e => setContent(e.target.value)}
          placeholder="写下今天的故事..."
          className="w-full bg-cd-bg-input border border-white/5 rounded-lg p-3 text-cd-text placeholder:text-cd-text-secondary min-h-[200px] resize-y focus:outline-none focus:border-purple-400/40 text-base leading-[1.8]" />
      </div>

      {/* 亮点和感恩 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-sm text-cd-text-secondary mb-2 flex items-center gap-1"><Sparkles size={14} className="text-gold" /> 今日亮点</div>
          <input type="text" value={highlights} onChange={e => setHighlights(e.target.value)}
            placeholder="今天最棒的事..."
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-cd-text text-sm focus:outline-none focus:border-purple-400/40" />
        </div>
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-sm text-cd-text-secondary mb-2">感恩的事</div>
          <input type="text" value={gratitude} onChange={e => setGratitude(e.target.value)}
            placeholder="今天感谢..."
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-cd-text text-sm focus:outline-none focus:border-purple-400/40" />
        </div>
      </div>

      {/* 标签 */}
      <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4">
        <div className="text-sm text-cd-text-secondary mb-2">标签（逗号分隔）</div>
        <input type="text" value={tags} onChange={e => setTags(e.target.value)}
          placeholder="如：高效,开会,突破..."
          className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-cd-text text-sm focus:outline-none focus:border-purple-400/40" />
      </div>

      {/* 保存按钮 */}
      <button onClick={handleSave} disabled={saving}
        className="w-full py-3 bg-purple-500/20 text-purple-300 rounded-xl border border-purple-400/30 hover:bg-purple-500/30 transition font-medium flex items-center justify-center gap-2 disabled:opacity-50">
        <Save size={18} /> {saving ? '保存中...' : savedFlash ? '已保存 ✓' : '保存日记'}
      </button>

      {/* 日记日历导航（GoalDay翻页体验） */}
      {diaryDates.length > 0 && (
        <div className="mt-6">
          <div className="text-sm text-cd-text-secondary mb-2">历史日记（{diaryDates.length} 篇）</div>
          <div className="flex gap-1 flex-wrap">
            {diaryDates.slice(0, 30).map(d => (
              <button key={d} onClick={() => setCurrentDate(d)}
                className={`px-2 py-1 rounded text-xs transition ${d === currentDate ? 'bg-purple-500/20 text-purple-300' : 'bg-cd-bg-input text-cd-text-secondary hover:bg-white/5'}`}>
                {d.substring(5)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
