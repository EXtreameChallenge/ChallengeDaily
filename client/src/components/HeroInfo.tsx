import { useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { Solar } from 'lunar-javascript'
import { MapPin, Navigation, CloudSun, Sparkles, Sunrise, Cloud, CloudRain, Snowflake, Wind, Zap, Droplets } from 'lucide-react'
import { request } from '../api/client'

interface HeroInfoProps {
  todayDurationMin: number
  goalHours?: number
}

interface WeatherInfo {
  temp: number
  code: number
  city?: string
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
  if (code <= 1) return <Sunrise size={18} className="text-cd-green" />
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

export default function HeroInfo({ todayDurationMin, goalHours = 8 }: HeroInfoProps) {
  const [now, setNow] = useState(dayjs())
  const [weather, setWeather] = useState<WeatherInfo | null>(null)
  const [city, setCity] = useState<string>(tzCity)
  const [preciseLocation, setPreciseLocation] = useState<string>('')
  const [loadingWeather, setLoadingWeather] = useState(false)
  const [greeting, setGreeting] = useState('')
  const [loadingGreeting, setLoadingGreeting] = useState(false)

  // 实时更新时间
  useEffect(() => {
    const timer = setInterval(() => setNow(dayjs()), 1000)
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

  // 获取 AI 导语（天气/城市就绪后会带着真实信息再请求一次）
  useEffect(() => {
    setLoadingGreeting(true)
    const locationText = preciseLocation ? `${city || tzCity} · ${preciseLocation}` : (city || tzCity)
    const params = new URLSearchParams({
      time: now.format('HH:mm'),
      date: now.format('M月D日'),
      weekday: WEEKDAYS[now.day()],
      lunar: lunarText,
      location: locationText,
    })
    if (weather) {
      params.set('weather', getWeatherText(weather.code))
      params.set('temp', String(weather.temp))
    }
    request(`/api/greeting?${params.toString()}`)
      .then((data: { greeting?: string }) => setGreeting(data.greeting || ''))
      .catch(() => setGreeting(''))
      .finally(() => setLoadingGreeting(false))
  }, [weather, city, preciseLocation])

  const progress = Math.min((todayDurationMin / (goalHours * 60)) * 100, 100)
  const progressColor = progress >= 100 ? 'text-cd-green' : progress >= 50 ? 'text-yellow-400' : 'text-cd-text-secondary'

  return (
    <div className="mb-6">
      <div className="flex flex-col lg:flex-row gap-6 lg:gap-8 items-start">
        {/* 左侧：时间日期 */}
        <div className="flex items-end gap-4">
          <div className="text-6xl font-bold text-cd-text tracking-tight font-brand leading-none">
            {now.format('HH:mm')}
          </div>
          <div className="pb-1">
            <div className="text-base text-cd-text font-medium font-display">{now.format('M月D日')}</div>
            <div className="text-sm text-cd-text-secondary font-display">{WEEKDAYS[now.day()]}</div>
            <div className="text-xs text-cd-text-tertiary mt-0.5 font-display">{lunarText}</div>
          </div>
        </div>

        {/* 中间：天气定位 */}
        <div className="flex items-center gap-4 lg:ml-auto">
          <div className="flex items-start gap-2 text-sm text-cd-text-secondary">
            <MapPin size={16} className="text-cd-text-tertiary mt-0.5 shrink-0" />
            <div className="flex flex-col">
              <span className="font-display leading-tight">{city || tzCity}</span>
              {preciseLocation && (
                <span className="text-[11px] text-cd-text-tertiary font-display leading-tight mt-0.5 flex items-center gap-1">
                  <Navigation size={10} className="shrink-0" />
                  {preciseLocation}
                </span>
              )}
            </div>
          </div>
          {loadingWeather ? (
            <div className="flex items-center gap-2 text-sm text-cd-text-tertiary">
              <Wind size={16} className="animate-spin" />
              <span>天气获取中</span>
            </div>
          ) : weather ? (
            <div className="flex items-center gap-2 text-sm text-cd-text">
              {getWeatherIcon(weather.code)}
              <span className="font-brand font-semibold">{weather.temp}°C</span>
              <span className="text-cd-text-secondary font-display">{getWeatherText(weather.code)}</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-cd-text-tertiary">
              <CloudSun size={16} />
              <span>天气暂不可用</span>
            </div>
          )}
        </div>
      </div>

      {/* 下方：AI 导语 + 图形化进度 */}
      <div className="mt-5 flex flex-col sm:flex-row gap-5 items-start">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles size={16} className="text-cd-green" />
            <span className="text-xs text-cd-green font-medium uppercase tracking-wider">AI 今日寄语</span>
          </div>
          {loadingGreeting ? (
            <p className="text-sm text-cd-text-tertiary animate-pulse">正在为你准备今日寄语...</p>
          ) : (
            <p className="text-base text-cd-text leading-relaxed">
              {greeting || '早安！新的一天，愿你高效而从容。'}
            </p>
          )}
        </div>

        {/* 今日进度环 */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="relative w-16 h-16">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
              <path
                className="text-cd-bg-secondary"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
              />
              <path
                className={progressColor}
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeDasharray={`${progress}, 100`}
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-[10px] font-brand font-semibold text-cd-text">{Math.round(progress)}%</span>
            </div>
          </div>
          <div>
            <div className="text-xs text-cd-text-tertiary">今日目标进度</div>
            <div className="text-sm text-cd-text font-medium font-brand">
              {todayDurationMin >= 60
                ? `${(todayDurationMin / 60).toFixed(1)}h / ${goalHours}h`
                : `${todayDurationMin}m / ${goalHours}h`}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
