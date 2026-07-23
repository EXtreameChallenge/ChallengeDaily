/**
 * 幕布 SSE 客户端（Electron 主进程侧）
 * ====================================
 * 后端通过 event_bus.push_event() 发布事件，Flask /api/events/stream 提供 SSE 流。
 * 本模块长连接该 SSE 流，收到 mubu:login:request / mubu:sync:request 后调用 mubuSync。
 *
 * 为什么不用 IPC？
 *   renderer 进程调用 preload.invoke 在某些场景下会出现 "No handler registered"，
 *   因为主进程 IPC 注册时机/上下文不稳定。SSE 基于 HTTP，不依赖 IPC 注册，更可靠。
 */
const http = require('http')
const { app } = require('electron')

const BACKEND_HOST = '127.0.0.1'
const BACKEND_PORT = 58888
const SSE_PATH = '/api/events/stream'
const RECONNECT_MS = 5000

let _eventSource = null
let _reconnectTimer = null
let _stopped = false
let _mubuSync = null
let _onError = null

function _readLocalToken() {
  try {
    const fs = require('fs')
    const path = require('path')
    const tokenPath = path.join(app.getPath('userData'), 'backend-data', '.api_token')
    if (fs.existsSync(tokenPath)) {
      return fs.readFileSync(tokenPath, 'utf-8').trim()
    }
  } catch (e) {
    console.error('[MubuSSE] read token failed:', e)
  }
  return ''
}

function _connect() {
  if (_stopped || _eventSource) return

  const token = _readLocalToken()
  if (!token) {
    console.warn('[MubuSSE] no token, retry in', RECONNECT_MS, 'ms')
    _scheduleReconnect()
    return
  }

  const url = `http://${BACKEND_HOST}:${BACKEND_PORT}${SSE_PATH}?token=${encodeURIComponent(token)}`

  try {
    // 用 Node http 实现 SSE（避免引入额外依赖）
    const req = http.get(url, { headers: { Accept: 'text/event-stream' } }, (res) => {
      if (res.statusCode !== 200) {
        console.error('[MubuSSE] SSE status:', res.statusCode)
        _eventSource = null
        _scheduleReconnect()
        return
      }

      console.log('[MubuSSE] connected to', url)
      let buffer = ''

      res.on('data', (chunk) => {
        buffer += chunk.toString('utf-8')
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let dataLine = ''
        for (const line of lines) {
          if (line.startsWith('data:')) {
            dataLine = line.slice(5).trim()
          } else if (line.trim() === '' && dataLine) {
            try {
              const evt = JSON.parse(dataLine)
              _handleEvent(evt)
            } catch (e) {
              // 心跳或解析失败，忽略
            }
            dataLine = ''
          }
        }
      })

      res.on('end', () => {
        console.log('[MubuSSE] connection ended')
        _eventSource = null
        _scheduleReconnect()
      })

      res.on('error', (err) => {
        console.error('[MubuSSE] connection error:', err.message)
        _eventSource = null
        _scheduleReconnect()
      })
    })

    req.on('error', (err) => {
      console.error('[MubuSSE] request error:', err.message)
      _eventSource = null
      _scheduleReconnect()
    })

    _eventSource = req
  } catch (e) {
    console.error('[MubuSSE] connect error:', e)
    _scheduleReconnect()
  }
}

function _handleEvent(evt) {
  if (!evt || !evt.type) return
  console.log('[MubuSSE] received event:', evt.type)

  if (evt.type === 'mubu:login:request') {
    try {
      _mubuSync?.showLoginWindow()
    } catch (e) {
      console.error('[MubuSSE] showLoginWindow failed:', e)
    }
  } else if (evt.type === 'mubu:sync:request') {
    try {
      _mubuSync?.startSync()
    } catch (e) {
      console.error('[MubuSSE] startSync failed:', e)
    }
  }
}

function _scheduleReconnect() {
  if (_stopped || _reconnectTimer) return
  _reconnectTimer = setTimeout(() => {
    _reconnectTimer = null
    _connect()
  }, RECONNECT_MS)
}

function start(mubuSyncModule) {
  if (_mubuSync) return
  _mubuSync = mubuSyncModule
  _stopped = false
  // 等 5 秒让后端完全启动
  setTimeout(_connect, 5000)
  console.log('[MubuSSE] client scheduled')
}

function stop() {
  _stopped = true
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer)
    _reconnectTimer = null
  }
  if (_eventSource) {
    try { _eventSource.destroy() } catch (_) {}
    _eventSource = null
  }
}

module.exports = { start, stop }
