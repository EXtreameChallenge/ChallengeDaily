/**
 * API client 单元测试
 * 覆盖：ensureBaseUrl 单例模式、X-API-Token 注入、请求超时中断
 */

describe('API client', () => {
  beforeEach(() => {
    jest.resetModules()
  })

  // ── 测试1：ensureBaseUrl 单例 — getBackendPort 仅调用一次 ──
  it('ensureBaseUrl calls getBackendPort once (singleton pattern)', async () => {
    const mockGetBackendPort = jest.fn().mockResolvedValue(58888)
    ;(window as any).electronAPI = { getBackendPort: mockGetBackendPort }

    const client = await import('./client')

    // 等待模块加载时触发的 ensureBaseUrl() 完成
    await new Promise(r => setTimeout(r, 50))

    // 调用导出函数，内部会再次调用 ensureBaseUrl()（应命中单例缓存）
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: 'ok' }),
    }) as any

    await client.getStatus()

    // 单例模式：getBackendPort 只被调用一次
    expect(mockGetBackendPort).toHaveBeenCalledTimes(1)
  })

  // ── 测试2：request 注入 X-API-Token 头 ──
  it('request sends X-API-Token header', async () => {
    const mockGetBackendPort = jest.fn().mockResolvedValue(58888)
    const mockGetApiToken = jest.fn().mockResolvedValue('test-token-123')
    ;(window as any).electronAPI = {
      getBackendPort: mockGetBackendPort,
      getApiToken: mockGetApiToken,
    }

    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: 'ok' }),
    })
    global.fetch = mockFetch as any

    const client = await import('./client')
    await new Promise(r => setTimeout(r, 50))

    await client.getStatus()

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/status'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'X-API-Token': 'test-token-123',
        }),
      })
    )
  })

  // ── 测试3：请求超时中断 ──
  it('request timeout aborts when server does not respond', async () => {
    const mockGetBackendPort = jest.fn().mockResolvedValue(58888)
    const mockGetApiToken = jest.fn().mockResolvedValue('test-token')
    ;(window as any).electronAPI = {
      getBackendPort: mockGetBackendPort,
      getApiToken: mockGetApiToken,
    }

    // fetch 监听 abort 信号后 reject（模拟真实 fetch 行为）
    global.fetch = jest.fn((_url: string, opts: any) => {
      return new Promise((_, reject) => {
        if (opts?.signal) {
          opts.signal.addEventListener('abort', () => {
            reject(new DOMException('The operation was aborted', 'AbortError'))
          })
        }
      })
    }) as any

    const client = await import('./client')
    // 等待模块级 ensureBaseUrl() 完成
    await new Promise(r => setTimeout(r, 50))

    // 切换到 fake timers 控制 setTimeout
    jest.useFakeTimers()

    const promise = client.getStatus()
    promise.catch(() => {}) // 防止未处理 rejection 警告

    // 刷新微任务：让 ensureBaseUrl + getApiToken 链式 await 完成
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()
    await Promise.resolve()

    // 快进超过默认 10000ms 超时
    jest.advanceTimersByTime(10001)

    await expect(promise).rejects.toThrow()
    jest.useRealTimers()
  })
})
