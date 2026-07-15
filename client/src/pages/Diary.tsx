import { useState, useEffect, useCallback, useRef } from 'react'
import { ChevronLeft, ChevronRight, Save, Calendar, Sparkles, Image as ImageIcon, Mic, Link2, X } from 'lucide-react'
import { getDiary, saveDiary, getDiaries, getTodayStr, formatLocalDate, type Diary as DiaryType, type DiaryMedia } from '../api/client'
import { useToast } from '../components/Toast'

const MOODS = [
  { emoji: '😄', label: '开心', color: 'text-yellow-400' },
  { emoji: '😊', label: '平静', color: 'text-green-400' },
  { emoji: '😴', label: '疲惫', color: 'text-blue-400' },
  { emoji: '😤', label: '烦躁', color: 'text-red-400' },
  { emoji: '🤔', label: '思考', color: 'text-cd-accent' },
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
  const [currentDate, setCurrentDate] = useState(getTodayStr())
  const [diary, setDiary] = useState<DiaryType | null>(null)
  const [mood, setMood] = useState('')
  const [weather, setWeather] = useState('')
  const [content, setContent] = useState('')
  const [tags, setTags] = useState('')
  const [highlights, setHighlights] = useState('')
  const [gratitude, setGratitude] = useState('')
  const [media, setMedia] = useState<DiaryMedia[]>([])
  const [linkInput, setLinkInput] = useState('')
  const [showLinkInput, setShowLinkInput] = useState(false)
  const [recording, setRecording] = useState(false)
  const [saving, setSaving] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const recordChunksRef = useRef<Blob[]>([])
  const recordStartRef = useRef<number>(0)
  const [savedFlash, setSavedFlash] = useState(false)
  const [diaryDates, setDiaryDates] = useState<string[]>([])
  const toast = useToast()
  // 用于在组件卸载时清理 savedFlash 的 setTimeout
  const flashTimerRef = useRef<number | undefined>(undefined)

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
      try { setMedia(d?.media_json ? JSON.parse(d.media_json) : []) } catch { setMedia([]) }
    } catch { toast.error('加载日记失败') }
  }, [currentDate, toast])

  const loadDates = useCallback(async () => {
    try {
      const { dates } = await getDiaries(90)
      setDiaryDates(dates)
    } catch { toast.error('加载日期列表失败') }
  }, [toast])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadDates() }, [loadDates])

  // 组件卸载时清理 flash 定时器
  useEffect(() => {
    return () => { if (flashTimerRef.current) clearTimeout(flashTimerRef.current) }
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await saveDiary({
        diary_date: currentDate, mood, weather, content, tags, highlights, gratitude,
        media_json: JSON.stringify(media),
      })
      setSavedFlash(true)
      if (flashTimerRef.current) clearTimeout(flashTimerRef.current)
      flashTimerRef.current = window.setTimeout(() => setSavedFlash(false), 2000)
      loadDates()
    } catch { toast.error('保存失败，请重试') }
    setSaving(false)
  }

  const goPrev = () => {
    const d = new Date(currentDate)
    d.setDate(d.getDate() - 1)
    setCurrentDate(formatLocalDate(d))
  }

  const goNext = () => {
    const d = new Date(currentDate)
    d.setDate(d.getDate() + 1)
    if (d <= new Date()) setCurrentDate(formatLocalDate(d))
  }

  // 图片上传：转 base64 存储（本地日记，不上云）
  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return
    Array.from(files).forEach(file => {
      const reader = new FileReader()
      reader.onload = () => {
        setMedia(prev => [...prev, { type: 'image', url: reader.result as string, title: file.name }])
      }
      reader.readAsDataURL(file)
    })
    e.target.value = ''
  }

  // 录音
  const handleRecordToggle = async () => {
    if (recording) {
      mediaRecorderRef.current?.stop()
      setRecording(false)
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const recorder = new MediaRecorder(stream)
        recordChunksRef.current = []
        recorder.ondataavailable = e => { if (e.data.size > 0) recordChunksRef.current.push(e.data) }
        recorder.onstop = () => {
          const blob = new Blob(recordChunksRef.current, { type: 'audio/webm' })
          const reader = new FileReader()
          reader.onload = () => {
            const duration = Math.round((Date.now() - recordStartRef.current) / 1000)
            setMedia(prev => [...prev, { type: 'audio', url: reader.result as string, duration }])
          }
          reader.readAsDataURL(blob)
          stream.getTracks().forEach(t => t.stop())
        }
        recorder.start()
        mediaRecorderRef.current = recorder
        recordStartRef.current = Date.now()
        setRecording(true)
      } catch { toast.error('无法访问麦克风') }
    }
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
          <Calendar size={18} className="text-cd-accent" />
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
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm text-cd-text-secondary">日记 · 一日一页</div>
          {/* 多媒体工具栏 */}
          <div className="flex gap-1">
            <button onClick={() => imageInputRef.current?.click()} title="插入图片"
              className="p-1.5 rounded-lg text-cd-text-tertiary hover:text-cd-accent hover:bg-white/5 transition">
              <ImageIcon size={15} />
            </button>
            <button onClick={handleRecordToggle} title="录音"
              className={`p-1.5 rounded-lg transition ${recording ? 'text-red-400 bg-red-400/10' : 'text-cd-text-tertiary hover:text-cd-accent hover:bg-white/5'}`}>
              <Mic size={15} />
            </button>
            <button onClick={() => setShowLinkInput(!showLinkInput)} title="插入链接"
              className="p-1.5 rounded-lg text-cd-text-tertiary hover:text-cd-accent hover:bg-white/5 transition">
              <Link2 size={15} />
            </button>
          </div>
          <input ref={imageInputRef} type="file" accept="image/*" multiple className="hidden"
            onChange={handleImageUpload} />
        </div>

        {/* 链接输入框 */}
        {showLinkInput && (
          <div className="flex gap-2 mb-2">
            <input type="url" value={linkInput} onChange={e => setLinkInput(e.target.value)}
              placeholder="粘贴链接 URL..."
              className="flex-1 bg-cd-bg-input border border-white/5 rounded-lg px-3 py-1.5 text-xs text-cd-text" />
            <button onClick={() => { if (linkInput.trim()) { setMedia([...media, { type: 'link', url: linkInput.trim() }]); setLinkInput(''); setShowLinkInput(false) } }}
              className="px-3 py-1.5 bg-cd-accent/20 text-cd-accent rounded-lg text-xs border border-cd-accent/30">
              添加
            </button>
          </div>
        )}

        {/* 媒体预览区 */}
        {media.length > 0 && (
          <div className="flex gap-2 flex-wrap mb-2">
            {media.map((m, i) => (
              <div key={i} className="relative group">
                {m.type === 'image' && (
                  <img src={m.url} alt={m.title || ''} className="w-20 h-20 object-cover rounded-lg border border-white/10" />
                )}
                {m.type === 'audio' && (
                  <div className="w-20 h-20 flex flex-col items-center justify-center bg-cd-bg-input rounded-lg border border-white/10">
                    <Mic size={20} className="text-cd-accent mb-1" />
                    <span className="text-[10px] text-cd-text-tertiary">{m.duration || 0}s</span>
                  </div>
                )}
                {m.type === 'link' && (
                  <div className="w-20 h-20 flex flex-col items-center justify-center bg-cd-bg-input rounded-lg border border-white/10 p-1">
                    <Link2 size={18} className="text-cd-accent mb-1" />
                    <span className="text-[9px] text-cd-text-tertiary truncate w-full text-center">{m.title || new URL(m.url).hostname}</span>
                  </div>
                )}
                <button onClick={() => setMedia(media.filter((_, idx) => idx !== i))}
                  className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition">
                  <X size={10} />
                </button>
              </div>
            ))}
          </div>
        )}

        <textarea value={content} onChange={e => setContent(e.target.value)}
          placeholder="写下今天的故事..."
          className="w-full bg-cd-bg-input border border-white/5 rounded-lg p-3 text-cd-text placeholder:text-cd-text-secondary min-h-[200px] resize-y focus:outline-none focus:border-cd-accent/40 text-base leading-[1.8]" />
      </div>

      {/* 亮点和感恩 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-sm text-cd-text-secondary mb-2 flex items-center gap-1"><Sparkles size={14} className="text-gold" /> 今日亮点</div>
          <input type="text" value={highlights} onChange={e => setHighlights(e.target.value)}
            placeholder="今天最棒的事..."
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-cd-text text-sm focus:outline-none focus:border-cd-accent/40" />
        </div>
        <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5">
          <div className="text-sm text-cd-text-secondary mb-2">感恩的事</div>
          <input type="text" value={gratitude} onChange={e => setGratitude(e.target.value)}
            placeholder="今天感谢..."
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-cd-text text-sm focus:outline-none focus:border-cd-accent/40" />
        </div>
      </div>

      {/* 标签 */}
      <div className="bg-cd-bg-card rounded-xl p-4 border border-white/5 mb-4">
        <div className="text-sm text-cd-text-secondary mb-2">标签（逗号分隔）</div>
        <input type="text" value={tags} onChange={e => setTags(e.target.value)}
          placeholder="如：高效,开会,突破..."
          className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-cd-text text-sm focus:outline-none focus:border-cd-accent/40" />
      </div>

      {/* 保存按钮 */}
      <button onClick={handleSave} disabled={saving}
        className="w-full py-3 bg-cd-accent/20 text-cd-accent rounded-xl border border-cd-accent/30 hover:bg-cd-accent/30 transition font-medium flex items-center justify-center gap-2 disabled:opacity-50">
        <Save size={18} /> {saving ? '保存中...' : savedFlash ? '已保存 ✓' : '保存日记'}
      </button>

      {/* 日记日历导航（GoalDay翻页体验） */}
      {diaryDates.length > 0 && (
        <div className="mt-6">
          <div className="text-sm text-cd-text-secondary mb-2">历史日记（{diaryDates.length} 篇）</div>
          <div className="flex gap-1 flex-wrap">
            {diaryDates.slice(0, 30).map(d => (
              <button key={d} onClick={() => setCurrentDate(d)}
                className={`px-2 py-1 rounded text-xs transition ${d === currentDate ? 'bg-cd-accent/20 text-cd-accent' : 'bg-cd-bg-input text-cd-text-secondary hover:bg-white/5'}`}>
                {d.substring(5)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
