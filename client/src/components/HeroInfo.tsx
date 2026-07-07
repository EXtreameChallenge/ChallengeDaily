import { useEffect, useMemo, useState, useCallback, type ReactNode } from 'react'
import dayjs from 'dayjs'
import { Solar } from 'lunar-javascript'
import { MapPin, Navigation, CloudSun, Cloud, CloudRain, Snowflake, Wind, Zap, Brain, RefreshCw, Lightbulb, AlertTriangle, Trophy, Sparkles, Eye, Compass } from 'lucide-react'
import { request } from '../api/client'

interface HeroInfoProps {
  todayDurationMin: number
}

interface WeatherInfo {
  temp: number
  code: number
  city?: string
}

interface InsightTag {
  type: 'mood' | 'care' | 'achievement' | 'reminder'
  text: string
}

interface InsightData {
  summary: string
  structured?: {
    headline: string
    mood: string
    story: string
    tags: InsightTag[]
    tips: string[]
  }
}

const WEEKDAYS = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']

const WEATHER_EMOJI: Record<number, string> = {
  0: '☀️',
  1: '🌤️', 2: '⛅', 3: '☁️',
  45: '🌫️', 48: '🌫️',
  51: '🌦️', 53: '🌦️', 55: '🌧️',
  61: '🌧️', 63: '🌧️', 65: '🌧️',
  71: '🌨️', 73: '🌨️', 75: '🌨️',
  95: '⛈️', 96: '⛈️', 99: '⛈️',
}

function getWeatherIcon(code: number) {
  if (code <= 1) return <CloudSun size={18} className="text-cd-green" />
  if (code <= 3) return <CloudSun size={18} className="text-cd-text-secondary" />
  if (code <= 48) return <Cloud size={18} className="text-cd-text-tertiary" />
  if (code <= 67) return <CloudRain size={18} className="text-blue-400" />
  if (code <= 77) return <Snowflake size={18} className="text-cyan-300" />
  if (code <= 99) return <Zap size={18} className="text-yellow-400" />
  return <CloudSun size={18} className="text-cd-text-secondary" />
}

function getWeatherText(code: number) {
  if (code === 0) return '晴朗'
  if (code <= 3) return '多云'
  if (code <= 48) return '雾'
  if (code <= 55) return '细雨'
  if (code <= 65) return '降雨'
  if (code <= 77) return '降雪'
  if (code <= 99) return '雷阵雨'
  return '未知'
}

const tzCity = (() => {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
    return tz.split('/').pop()?.replace(/_/g, ' ') || '本地'
  } catch {
    return '本地'
  }
})()

/** 把故事里的数字、时间、百分比高亮，方便一眼看到重点 */
function highlightStory(text: string): ReactNode[] {
  const result: ReactNode[] = []
  const regex = /(\d{1,2}:\d{2})|(\d+\.?\d*)\s*(小时|分钟|条|%|\/100|h|min)/g
  let lastIndex = 0
  let match: RegExpExecArray | null
  let key = 0
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      result.push(<span key={key++}>{text.slice(lastIndex, match.index)}</span>)
    }
    if (match[1]) {
      result.push(<span key={key++} className="text-purple-300 font-semibold">{match[1]}</span>)
    } else {
      result.push(<span key={key++} className="text-cd-green font-semibold">{match[2]}{match[3]}</span>)
    }
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    result.push(<span key={key++}>{text.slice(lastIndex)}</span>)
  }
  return result
}

export default function HeroInfo({ todayDurationMin }: HeroInfoProps) {
  const [now, setNow] = useState(dayjs())
  const [weather, setWeather] = useState<WeatherInfo | null>(null)
  const [city, setCity] = useState<string>(tzCity)
  const [preciseLocation, setPreciseLocation] = useState<string>('')
  const [loadingWeather, setLoadingWeather] = useState(false)
  const [insight, setInsight] = useState<InsightData | null>(null)
  const [loadingInsight, setLoadingInsight] = useState(false)

  // 实时更新时间
  // 优化：从 1 秒调整为 10 秒，仅在分钟变化时重渲染
  // HH:mm 显示只需分钟级精度，1 秒轮询导致每秒 React 重渲染 + lunar 计算
  useEffect(() => {
    let lastMinute = dayjs().minute()
    const timer = setInterval(() => {
      const current = dayjs()
      if (current.minute() !== lastMinute) {
        lastMinute = current.minute()
        setNow(current)
      }
    }, 10000) // 10 秒检查一次
    return () => clearInterval(timer)
  }, [])

  // 农历
  const lunarText = useMemo(() => {
    const solar = Solar.fromYmd(now.year(), now.month() + 1, now.date())
    const lunar = solar.getLunar()
    const month = lunar.getMonthInChinese()
    const day = lunar.getDayInChinese()
    const term = lunar.getJieQi()
    return `农历${month}月${day}${term ? ` · ${term}` : ''}`
  }, [now])

  // 获取定位 + 天气（Windows 系统定位 → 浏览器 GPS → 多 IP 源 → 时区兜底）
  useEffect(() => {
    setLoadingWeather(true)
    let cancelled = false
    const done = () => { if (!cancelled) setLoadingWeather(false) }

    const fetchWeather = async (lat: number, lon: number) => {
      const res = await fetch(
        `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,weather_code&timezone=auto`,
        { signal: AbortSignal.timeout(8000) }
      )
      const data = await res.json()
      if (!cancelled) {
        setWeather({
          temp: Math.round(data.current.temperature_2m),
          code: data.current.weather_code,
        })
      }
    }

    // 逆地理编码：从坐标解析出城市 + 精确位置（街道/建筑/POI）
    const fetchCityByCoords = async (lat: number, lon: number, precise = false) => {
      // ── 第一层：BigDataCloud（免费，返回 neighbourhood / POI / locality 字段）──
      try {
        const res = await fetch(
          `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lon}&localityLanguage=zh`,
          { signal: AbortSignal.timeout(8000) }
        )
        const data = await res.json()
        const cityName = data.city || data.locality || data.principalSubdivision
        if (cityName && !cancelled) setCity(cityName)

        // 提取精确位置：locality(区县) > POI > neighbourhood
        const poiParts: string[] = []
        // 区县级别（BigDataCloud 对中国支持较好）
        if (data.locality && data.locality !== data.city) poiParts.push(data.locality)
        if (data.poi) poiParts.push(data.poi)
        if (data.neighbourhood && data.neighbourhood !== data.city && data.neighbourhood !== data.locality) {
          poiParts.push(data.neighbourhood)
        }
        if (data.poiDescription) {
          const desc = data.poiDescription
          if (!poiParts.some(p => desc.toLowerCase().includes(p.toLowerCase()))) {
            poiParts.push(desc)
          }
        }
        if (poiParts.length > 0 && !cancelled) {
          setPreciseLocation(poiParts.join(' · '))
        }
      } catch { /* ignore */ }

      // ── 第二层：Nominatim（OSM，高精度坐标时解析到建筑/道路级，国内可能超时）──
      if (!precise) return
      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&zoom=18&addressdetails=1&accept-language=zh-CN`,
          {
            signal: AbortSignal.timeout(5000),
            headers: { 'User-Agent': 'ChallengeDaily/1.5.0' },
          }
        )
        const data = await res.json()
        const addr = data.address || {}

        const place =
          addr.building ||
          addr.college ||
          addr.school ||
          addr.university ||
          addr.hospital ||
          addr.mall ||
          addr.office ||
          addr.hotel ||
          addr.restaurant ||
          addr.shop ||
          addr.amenity ||
          addr.suburb ||
          addr.quarter ||
          addr.neighbourhood ||
          addr.road

        if (place && !cancelled) {
          const currentPrecise = preciseLocation
          if (!currentPrecise) {
            const detailParts: string[] = []
            if (addr.road) detailParts.push(addr.road)
            if (addr.house_number) detailParts.push(addr.house_number + '号')
            if (addr.building && addr.building !== addr.road) detailParts.push(addr.building)
            const detail = detailParts.join('')
            if (detail) {
              setPreciseLocation(detail)
            } else {
              setPreciseLocation(place)
            }
          }
          const betterCity = addr.city || addr.town || addr.county || addr.state
          if (betterCity && betterCity !== city) {
            setCity(betterCity)
          }
        }
      } catch { /* Nominatim 国内经常超时，静默忽略 */ }
    }

    const fetchWeatherByCityName = async (name: string) => {
      try {
        const res = await fetch(
          `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(name)}&count=1`,
          { signal: AbortSignal.timeout(8000) }
        )
        const data = await res.json()
        const r = data.results?.[0]
        if (r) {
          if (!cancelled) setCity(r.name || name)
          await fetchWeather(r.latitude, r.longitude)
          return true
        }
      } catch { /* ignore */ }
      return false
    }

    const tryWindowsLocation = async (): Promise<boolean> => {
      try {
        const loc = await window.electronAPI?.getWindowsLocation?.()
        if (loc && loc.lat && loc.lon) {
          await Promise.all([
            fetchWeather(loc.lat, loc.lon),
            fetchCityByCoords(loc.lat, loc.lon, true),
          ])
          return true
        }
      } catch (e) {
        console.warn('[HeroInfo] Windows location failed:', e)
      }
      return false
    }

    const tryBrowserGeo = async (): Promise<boolean> => {
      return new Promise((resolve) => {
        if (!('geolocation' in navigator)) return resolve(false)
        navigator.geolocation.getCurrentPosition(
          async (pos) => {
            try {
              const { latitude, longitude } = pos.coords
              await Promise.all([
                fetchWeather(latitude, longitude),
                fetchCityByCoords(latitude, longitude, true),
              ])
              resolve(true)
            } catch {
              resolve(false)
            }
          },
          () => resolve(false),
          { timeout: 10000, enableHighAccuracy: true }
        )
      })
    }

    // 百度智能云免费 IP 定位（国内最准，无需 Key，返回 WGS84 坐标）
    const tryBaiduQifu = async (): Promise<boolean> => {
      try {
        const res = await fetch('https://qifu-api.baidubce.com/ip/local/geo/v1/district', {
          signal: AbortSignal.timeout(6000),
        })
        const data = await res.json()
        if (data.code === 'Success' && Array.isArray(data.data?.location)) {
          const [lon, lat] = data.data.location
          if (lat && lon) {
            if (data.data.city && !cancelled) setCity(data.data.city)
            await Promise.all([
              fetchWeather(lat, lon),
              fetchCityByCoords(lat, lon),
            ])
            return true
          }
        }
      } catch { /* try next */ }
      return false
    }

    // 腾讯 IP 定位（需要 Key 才能返回坐标，无 Key 时仅返回城市名）
    const tryTencentIP = async (): Promise<boolean> => {
      try {
        const res = await fetch('https://apis.map.qq.com/ws/location/v1/ip', {
          signal: AbortSignal.timeout(6000),
        })
        const data = await res.json()
        if (data.status === 0 && data.result) {
          const r = data.result
          const loc = r.location
          const adInfo = r.ad_info
          const districtName = adInfo?.district || adInfo?.city || ''
          if (districtName && !cancelled) setCity(districtName)
          if (loc?.lat && loc?.lng) {
            await Promise.all([
              fetchWeather(loc.lat, loc.lng),
              fetchCityByCoords(loc.lat, loc.lng),
            ])
            return true
          }
          if (districtName) return true
        }
        // status !== 0 说明需要 Key，静默跳过
      } catch { /* try next */ }
      return false
    }

    // 搜狐免费 IP 城市（只返回城市名，用 open-meteo 地理编码转坐标）
    const trySohu = async (): Promise<boolean> => {
      try {
        const res = await fetch('https://pv.sohu.com/cityjson?ie=utf-8', {
          signal: AbortSignal.timeout(6000),
        })
        const text = await res.text()
        const match = text.match(/returnCitySN\s*=\s*(\{[^}]+\})/)
        if (match) {
          const data = JSON.parse(match[1])
          if (data.cname) return await fetchWeatherByCityName(data.cname)
        }
      } catch { /* try next */ }
      return false
    }

    // 新浪免费 IP 城市
    const trySina = async (): Promise<boolean> => {
      try {
        const res = await fetch('https://int.dpool.sina.com.cn/iplookup/iplookup.php?format=js', {
          signal: AbortSignal.timeout(6000),
        })
        const text = await res.text()
        const match = text.match(/remote_ip_info\s*=\s*(\{[^}]+\})/)
        if (match) {
          const data = JSON.parse(match[1])
          if (data.city) return await fetchWeatherByCityName(data.city)
        }
      } catch { /* try next */ }
      return false
    }

    // 海外 IP 定位兜底（常把国内 IP 归到上海，仅作最后备选）
    const tryOverseasIP = async (): Promise<boolean> => {
      const services = [
        {
          url: 'https://ipapi.co/json/',
          parse: (d: any) => (d.latitude && d.longitude ? { lat: d.latitude, lon: d.longitude, city: d.city } : null),
        },
        {
          url: 'https://ipinfo.io/json',
          parse: (d: any) => {
            if (!d.loc) return null
            const [lat, lon] = d.loc.split(',').map(Number)
            return { lat, lon, city: d.city }
          },
        },
        {
          url: 'https://ip-api.com/json/',
          parse: (d: any) => (d.lat && d.lon ? { lat: d.lat, lon: d.lon, city: d.city } : null),
        },
      ]
      for (const svc of services) {
        try {
          const res = await fetch(svc.url, { signal: AbortSignal.timeout(6000) })
          const data = await res.json()
          const info = svc.parse(data)
          if (info && info.lat && info.lon) {
            if (info.city && !cancelled) setCity(info.city)
            await fetchWeather(info.lat, info.lon)
            return true
          }
        } catch { /* try next */ }
      }
      return false
    }

    const run = async () => {
      if (await tryWindowsLocation()) return done()
      if (await tryBrowserGeo()) return done()
      if (await tryBaiduQifu()) return done()
      if (await tryTencentIP()) return done()
      if (await trySohu()) return done()
      if (await trySina()) return done()
      if (await tryOverseasIP()) return done()
      // 最终兜底：时区城市
      await fetchWeatherByCityName(tzCity)
      done()
    }

    run()
    return () => { cancelled = true }
  }, [])

  // 获取 AI 洞察（基于真实活动数据的分析，非空话寄语）
  const fetchInsight = useCallback(() => {
    setLoadingInsight(true)
    request('/api/ai/overview-summary')
      .then((raw) => {
        const data = raw as InsightData
        if (data.summary || data.structured) setInsight(data)
      })
      .catch(() => { /* 静默失败 */ })
      .finally(() => setLoadingInsight(false))
  }, [])

  useEffect(() => {
    fetchInsight()
    // 启动后 3 秒再拉一次，避免后端初始化未完成导致空数据
    const retryTimer = setTimeout(() => {
      if (!insight) fetchInsight()
    }, 3000)
    // 5 分钟刷新一次（与后端缓存 TTL 对齐）
    const timer = setInterval(fetchInsight, 300000)
    return () => {
      clearTimeout(retryTimer)
      clearInterval(timer)
    }
  }, [fetchInsight, insight])

  return (
    <div>
      {/* 第一行：时间日期 + 天气 */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        {/* 时间日期 */}
        <div className="flex items-end gap-3">
          <div className="text-5xl font-bold text-cd-text tracking-tight font-brand leading-none">
            {now.format('HH:mm')}
          </div>
          <div className="pb-0.5">
            <div className="text-sm text-cd-text font-medium font-display">{now.format('M月D日')}</div>
            <div className="text-xs text-cd-text-secondary font-display">{WEEKDAYS[now.day()]}</div>
            <div className="text-[11px] text-cd-text-tertiary font-display">{lunarText}</div>
          </div>
        </div>

        {/* 位置 + 天气 */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-cd-text-secondary">
            <MapPin size={13} className="text-cd-text-tertiary shrink-0" />
            <span className="font-display">{city || tzCity}</span>
            {preciseLocation && (
              <span className="text-[10px] text-cd-text-tertiary font-display flex items-center gap-0.5">
                <Navigation size={9} className="shrink-0" />
                {preciseLocation}
              </span>
            )}
          </div>
          {loadingWeather ? (
            <div className="flex items-center gap-1.5 text-xs text-cd-text-tertiary">
              <Wind size={13} className="animate-spin" />
            </div>
          ) : weather ? (
            <div className="flex items-center gap-1.5 text-xs text-cd-text">
              {getWeatherIcon(weather.code)}
              <span className="font-brand font-semibold">{weather.temp}°C</span>
              <span className="text-cd-text-secondary font-display">{getWeatherText(weather.code)}</span>
            </div>
          ) : null}
        </div>
      </div>

      {/* 第二行：AI 洞察（温柔朋友风格） */}
      <div className="mt-4">
        <div className="flex items-center gap-1.5 mb-2">
          <Brain size={16} className="text-cd-green" />
          <span className="text-xs text-cd-green font-medium uppercase tracking-wider">AI 洞察</span>
          {!loadingInsight && insight && (
            <button onClick={fetchInsight} className="text-cd-text-tertiary hover:text-cd-text transition" title="刷新">
              <RefreshCw size={12} />
            </button>
          )}
        </div>
        {loadingInsight ? (
          <p className="text-base text-cd-text-tertiary animate-pulse">正在分析今日工作数据...</p>
        ) : insight ? (
          <div className="rounded-2xl bg-gradient-to-br from-[#1E1E2E] to-[#252538] border border-white/5 p-4 shadow-sm">
            {insight.structured ? (
              <div className="space-y-4">
                {/* 顶部：心情 emoji + headline */}
                <div className="flex items-start gap-2.5">
                  <span className="text-2xl shrink-0 leading-none mt-0.5">
                    {insight.structured.mood === 'proud' && '🌟'}
                    {insight.structured.mood === 'tired' && '😴'}
                    {insight.structured.mood === 'focused' && '🎯'}
                    {insight.structured.mood === 'balanced' && '☕'}
                    {insight.structured.mood === 'scattered' && '🍃'}
                    {insight.structured.mood === 'excited' && '✨'}
                    {(!insight.structured.mood || insight.structured.mood === 'warm') && '🌸'}
                  </span>
                  <p className="text-xl text-cd-text font-semibold leading-snug">{insight.structured.headline || insight.summary}</p>
                </div>

                {/* 主体：朋友式小作文，字号加大、行距宽松，数字高亮 */}
                {insight.structured.story && (
                  <p className="text-lg text-cd-text-secondary leading-[1.8]">{highlightStory(insight.structured.story)}</p>
                )}

                {/* 可爱的情绪/关怀标签 */}
                {insight.structured.tags.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {insight.structured.tags.map((tag, idx) => {
                      const styles = {
                        mood: 'text-pink-300 bg-pink-400/10 border-pink-400/20',
                        care: 'text-orange-300 bg-orange-400/10 border-orange-400/20',
                        achievement: 'text-green-300 bg-green-400/10 border-green-400/20',
                        reminder: 'text-sky-300 bg-sky-400/10 border-sky-400/20',
                      }
                      return (
                        <span
                          key={idx}
                          className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium border ${styles[tag.type]}`}
                        >
                          {tag.text}
                        </span>
                      )
                    })}
                  </div>
                )}

                {/* 温柔小建议 */}
                {insight.structured.tips.length > 0 && (
                  <div className="flex items-start gap-2.5 pt-2 border-t border-white/5">
                    <Sparkles size={16} className="shrink-0 mt-1 text-purple-400" />
                    <p className="text-base text-purple-300 leading-relaxed">{insight.structured.tips[0]}</p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-lg text-cd-text leading-relaxed">{insight.summary}</p>
            )}
          </div>
        ) : (
          <p className="text-base text-cd-text-tertiary">配置 AI 后，这里会基于真实工作数据给出温柔洞察。</p>
        )}
      </div>
    </div>
  )
}
