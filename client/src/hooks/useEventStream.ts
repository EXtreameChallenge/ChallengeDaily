import { useState, useEffect, useRef, useCallback } from 'react'
import { getBaseUrl, getApiToken, ensureBaseUrl } from '../api/client'

export interface SSEEvent {
  type: string
  data: Record<string, unknown>
  timestamp: number
}

/**
 * SSE 事件流 Hook
 *
 * 连接 /api/events/stream，自动重连，返回最新事件。
 * token 通过 query param 传递（SSE 不支持自定义 header）。
 *
 * @returns { event, connected } 最新事件与连接状态
 */
export function useEventStream() {
  const [event, setEvent] = useState<SSEEvent | null>(null)
  const [connected, setConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const retryRef = useRef<number>(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(async () => {
    // 确保 BASE_URL 已初始化
    await ensureBaseUrl()
    const token = await getApiToken()
    if (!token) {
      // token 未就绪，稍后重试
      timerRef.current = setTimeout(connect, 1000)
      return
    }
    const url = `${getBaseUrl()}/api/events/stream?token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => {
      setConnected(true)
      retryRef.current = 0
    }

    es.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data) as SSEEvent
        setEvent(parsed)
      } catch {
        // 忽略心跳/解析失败
      }
    }

    es.onerror = () => {
      setConnected(false)
      es.close()
      esRef.current = null
      // 指数退避重连（max 30s）
      retryRef.current += 1
      const delay = Math.min(30000, 1000 * Math.pow(2, retryRef.current))
      timerRef.current = setTimeout(connect, delay)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [connect])

  return { event, connected }
}
