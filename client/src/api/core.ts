// ── API 核心基础设施：BASE_URL、请求层、Token 管理、后端状态 ──

// 后端 API 基础 URL：优先从 Electron 主进程获取端口，兼容非 Electron 环境
let BASE_URL = 'http://127.0.0.1:58888'

// 异步初始化 BASE_URL 的 Promise（避免启动初期竞态：模块加载时端口尚未就绪）
let _baseUrlPromise: Promise<void> | null = null
function ensureBaseUrl(): Promise<void> {
  if (_baseUrlPromise) return _baseUrlPromise
  _baseUrlPromise = (async () => {
    if (typeof window !== 'undefined' && window.electronAPI?.getBackendPort) {
      try {
        const port = await window.electronAPI.getBackendPort()
        if (port) BASE_URL = `http://127.0.0.1:${port}`
      } catch {
        // 保留默认 BASE_URL
      }
    }
  })()
  return _baseUrlPromise
}

// 启动时也立即触发一次（兼容现有调用模式）
ensureBaseUrl()

// 导出供 SSE 等场景使用
export function getBaseUrl(): string { return BASE_URL }
export { getApiToken, ensureBaseUrl }

// ── 后端连接状态管理（企业级断线重连机制） ──
type BackendState = 'connected' | 'disconnected' | 'connecting'
let _backendState: BackendState = 'connecting'
const _stateListeners = new Set<(s: BackendState) => void>()

// 连续失败计数：只有连续多次失败才标记disconnected，避免单次超时误判
let _consecutiveFailures = 0
const _DISCONNECT_THRESHOLD = 3  // 连续3次失败才标记断连（从2提升到3，减少偶发超时误判）

export function getBackendState(): BackendState { return _backendState }
export function onBackendStateChange(cb: (s: BackendState) => void): () => void {
  _stateListeners.add(cb)
  return () => _stateListeners.delete(cb)
}
function setBackendState(s: BackendState) {
  if (_backendState === s) return
  _backendState = s
  _stateListeners.forEach(cb => cb(s))
}
function markRequestSuccess() {
  _consecutiveFailures = 0
  setBackendState('connected')
}
function markRequestFailure() {
  _consecutiveFailures++
  if (_consecutiveFailures >= _DISCONNECT_THRESHOLD) {
    setBackendState('disconnected')
  }
}

// ── API Token 管理 ──
let _apiToken = ''
let _tokenPromise: Promise<string> | null = null

async function _fetchTokenOnce(): Promise<string> {
  if (!window.electronAPI?.getApiToken) return ''
  try {
    const t = await window.electronAPI.getApiToken()
    return (t || '').trim()
  } catch {
    return ''
  }
}

async function getApiToken(): Promise<string> {
  // 有有效缓存时直接返回；空缓存不返回，继续尝试读取
  if (_apiToken) return _apiToken

  // 避免并发重复请求：但空结果不缓存，下次调用仍会重试
  if (!_tokenPromise) {
    _tokenPromise = (async () => {
      // 启动阶段 token 文件可能尚未写入，最多重试 10 次，每次 300ms
      for (let i = 0; i < 10; i++) {
        const t = await _fetchTokenOnce()
        if (t) {
          _apiToken = t
          _tokenPromise = null
          return t
        }
        if (i < 9) await new Promise(r => setTimeout(r, 300))
      }
      _tokenPromise = null
      return ''
    })()
  }
  return _tokenPromise
}

/** 清除 API Token 缓存（401 时调用，强制下次重新从磁盘读取） */
function invalidateToken() {
  _apiToken = ''
  _tokenPromise = null
}

/** 带指数退避重试的 fetch（参考 resilience4j / Polly 模式）
 * @param timeoutMs - 自定义超时时间（毫秒），默认 10000ms
 * 如果调用方在 options.signal 中传入外部 signal（如 AbortController），
 * 则该 signal 触发 abort 时也会同步中断 fetch；同时保留超时机制。
 */
// P22: GET 请求去重 — 并发相同 GET 共享 Promise，避免重复请求
const _inflightGets = new Map<string, Promise<unknown>>()

export async function request(endpoint: string, options?: RequestInit, timeoutMs = 10000, _retryCount = 0): Promise<unknown> {
  // P22: GET 请求去重 — 同一 endpoint 的并发 GET 共享同一个 Promise
  const isGet = !options?.method || options.method === 'GET'
  if (isGet && _retryCount === 0) {
    const existing = _inflightGets.get(endpoint)
    if (existing) return existing
    // 创建并存储 promise，执行后清理
    const p = _requestImpl(endpoint, options, timeoutMs, _retryCount)
    _inflightGets.set(endpoint, p)
    try {
      return await p
    } finally {
      _inflightGets.delete(endpoint)
    }
  }
  return _requestImpl(endpoint, options, timeoutMs, _retryCount)
}

async function _requestImpl(endpoint: string, options?: RequestInit, timeoutMs = 10000, _retryCount = 0): Promise<unknown> {
  // 确保 BASE_URL 已初始化（避免启动初期端口尚未就绪导致请求失败）
  await ensureBaseUrl()
  const token = await getApiToken()
  const controller = new AbortController()
  // 连接超时：后端是本地服务，默认 10 秒；生成报告等长耗时操作可自定义
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  // 若调用方提供外部 signal，则联动中断 fetch
  const externalSignal = options?.signal
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', () => controller.abort(), { once: true })
  }
  // 剥离外部 signal，避免覆盖 timeout controller（fetch 仍使用 controller.signal）
  const { signal: _stripped, ...restOptions } = options || {}
  try {
    // 不再每次请求都设connecting——高频轮询时会导致UI闪烁
    // 只在真正断连后才设connecting
    if (_backendState === 'disconnected') setBackendState('connecting')
    const res = await fetch(`${BASE_URL}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-API-Token': token } : {}),
      },
      signal: controller.signal,
      ...restOptions,
    })
    if (res.status === 401) {
      // Token 失效/未就绪：清除缓存，短暂等待后重试（最多 3 次）
      // 启动阶段 token 文件可能稍后写入，避免直接判定认证失败
      if (_retryCount < 3) {
        invalidateToken()
        if (_retryCount === 0) {
          // 首次 401 时给后端一点写入 token 的时间
          await new Promise(r => setTimeout(r, 500))
        }
        return request(endpoint, options, timeoutMs, _retryCount + 1)
      }
      throw new Error('认证失败，请重新启动应用')
    }
    if (!res.ok) {
      // 后端已响应但返回错误码（4xx/5xx）——后端在线，只是业务逻辑出错
      // 不应标记为 disconnected，否则会误报"后端服务断开"
      markRequestSuccess()
      throw new Error(`请求失败: ${res.status}`)
    }
    const data = await res.json()
    markRequestSuccess()
    return data
  } catch (err: unknown) {
    // 外部 signal 主动取消：不更新断连状态，向上抛出 AbortError 供调用方识别
    if (externalSignal?.aborted) {
      throw new DOMException('请求已被取消', 'AbortError')
    }
    // 累计连续失败次数，达到阈值才标记disconnected
    markRequestFailure()
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error('请求超时，后端可能未响应')
    }
    if (err instanceof Error) {
      if (err.message?.includes('Failed to fetch') || err.message?.includes('NetworkError') || err.message?.includes('ECONNREFUSED')) {
        throw new Error('无法连接到后端服务，正在尝试自动重连...')
      }
      throw err
    }
    throw new Error('未知请求错误')
  } finally {
    clearTimeout(timeoutId)
  }
}

/** 通用 Blob 下载触发器 */
export function _triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
