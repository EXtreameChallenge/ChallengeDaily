import { useState, useEffect, useCallback } from 'react'
import { Lock, Unlock, Fingerprint, Eye, EyeOff, ShieldCheck } from 'lucide-react'

// 应用级隐私锁：密码 + Windows Hello + 闲置自动锁 + 模块级锁
const LOCK_STORAGE_KEY = 'cd_app_lock_v1'
const IDLE_LOCK_KEY = 'cd_idle_lock_v1'
const MODULE_LOCK_KEY = 'cd_module_lock_v1'
const MAX_FAIL_ATTEMPTS = 5

interface LockConfig {
  enabled: boolean
  passwordHash: string  // 仅存 hash，不存明文
  useHello: boolean     // Windows Hello 生物识别
  idleMinutes: number   // 闲置自动锁分钟数（0=不锁）
  moduleLock: {         // 模块级锁
    diary: boolean
    profile: boolean
    settings: boolean
  }
  failAttempts: number
  lastFailAt: number
}

const DEFAULT_CONFIG: LockConfig = {
  enabled: false,
  passwordHash: '',
  useHello: false,
  idleMinutes: 0,
  moduleLock: { diary: false, profile: false, settings: false },
  failAttempts: 0,
  lastFailAt: 0,
}

async function hashPassword(pw: string): Promise<string> {
  const enc = new TextEncoder().encode('cd_salt_v1_' + pw)
  const buf = await crypto.subtle.digest('SHA-256', enc)
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

function loadConfig(): LockConfig {
  try {
    const raw = localStorage.getItem(LOCK_STORAGE_KEY)
    if (!raw) return DEFAULT_CONFIG
    return { ...DEFAULT_CONFIG, ...JSON.parse(raw) }
  } catch { return DEFAULT_CONFIG }
}

function saveConfig(cfg: LockConfig) {
  localStorage.setItem(LOCK_STORAGE_KEY, JSON.stringify(cfg))
}

// 闲置检测 hook
function useIdleDetection(minutes: number, onIdle: () => void) {
  useEffect(() => {
    if (minutes <= 0) return
    let timer: ReturnType<typeof setTimeout>
    const reset = () => {
      clearTimeout(timer)
      timer = setTimeout(onIdle, minutes * 60 * 1000)
    }
    const events = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart']
    events.forEach(e => window.addEventListener(e, reset, { passive: true }))
    reset()
    return () => {
      clearTimeout(timer)
      events.forEach(e => window.removeEventListener(e, reset))
    }
  }, [minutes, onIdle])
}

// 解锁界面
export function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [cfg, setCfg] = useState(loadConfig())
  const [locked, setLocked] = useState(true)

  const tryHello = useCallback(async () => {
    if (!window.electronAPI?.windowsHello) {
      setError('当前系统不支持 Windows Hello')
      return
    }
    try {
      const ok = await window.electronAPI.windowsHello('解锁 ChallengeDaily')
      if (ok) {
        setLocked(false)
        onUnlock()
      } else {
        setError('生物识别失败')
      }
    } catch { setError('Windows Hello 调用失败') }
  }, [onUnlock])

  const submit = useCallback(async () => {
    const hash = await hashPassword(password)
    if (hash === cfg.passwordHash) {
      setLocked(false)
      onUnlock()
      const next = { ...cfg, failAttempts: 0, lastFailAt: 0 }
      setCfg(next)
      saveConfig(next)
    } else {
      const next = { ...cfg, failAttempts: cfg.failAttempts + 1, lastFailAt: Date.now() }
      setCfg(next)
      saveConfig(next)
      setError(`密码错误（第 ${next.failAttempts}/${MAX_FAIL_ATTEMPTS} 次）`)
      setPassword('')
      if (next.failAttempts >= MAX_FAIL_ATTEMPTS) {
        setError('尝试次数过多，请 5 分钟后再试')
      }
    }
  }, [password, cfg, onUnlock])

  if (!locked) return null

  return (
    <div className="fixed inset-0 z-[100] bg-black/90 flex flex-col items-center justify-center select-none">
      <div className="w-80 max-w-[90vw]">
        <div className="text-center mb-6">
          <Lock size={48} className="text-cd-accent mx-auto mb-3" />
          <h2 className="text-lg text-white font-medium">应用已锁定</h2>
          <p className="text-xs text-white/40 mt-1">输入密码或使用 Windows Hello 解锁</p>
        </div>
        <div className="space-y-3">
          <div className="relative">
            <input type={show ? 'text' : 'password'} value={password}
              onChange={e => { setPassword(e.target.value); setError('') }}
              onKeyDown={e => e.key === 'Enter' && submit()}
              placeholder="输入密码"
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-3 text-white placeholder:text-white/30 focus:outline-none focus:border-cd-accent/40 pr-10" />
            <button onClick={() => setShow(!show)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/70">
              {show ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
          {error && <div className="text-xs text-red-400 text-center">{error}</div>}
          <button onClick={submit} disabled={!password}
            className="w-full py-3 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 transition disabled:opacity-40">
            解锁
          </button>
          {cfg.useHello && (
            <button onClick={tryHello}
              className="w-full py-3 bg-white/5 text-white/70 rounded-lg border border-white/10 hover:bg-white/10 transition flex items-center justify-center gap-2">
              <Fingerprint size={18} /> Windows Hello
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// 设置面板（嵌入 Settings 页）
export function AppLockSettings() {
  const [cfg, setCfg] = useState(loadConfig())
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [msg, setMsg] = useState('')

  const update = (patch: Partial<LockConfig>) => {
    const next = { ...cfg, ...patch }
    setCfg(next)
    saveConfig(next)
  }

  const setPassword = async () => {
    if (newPw.length < 4) { setMsg('密码至少 4 位'); return }
    if (newPw !== confirmPw) { setMsg('两次输入不一致'); return }
    const hash = await hashPassword(newPw)
    update({ enabled: true, passwordHash: hash })
    setNewPw(''); setConfirmPw('')
    setMsg('应用锁已启用')
  }

  const disable = () => {
    update({ enabled: false, passwordHash: '' })
    setNewPw(''); setConfirmPw('')
    setMsg('应用锁已关闭')
  }

  return (
    <div className="bg-cd-bg-card rounded-xl p-5 border border-white/5 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck size={18} className="text-cd-accent" />
        <h3 className="text-sm text-cd-text font-medium">应用级隐私锁</h3>
        <span className={`ml-auto text-xs px-2 py-0.5 rounded ${cfg.enabled ? 'bg-green-500/20 text-green-400' : 'bg-white/5 text-cd-text-tertiary'}`}>
          {cfg.enabled ? '已启用' : '未启用'}
        </span>
      </div>

      {!cfg.enabled ? (
        <div className="space-y-2">
          <input type="password" value={newPw} onChange={e => setNewPw(e.target.value)}
            placeholder="设置密码（至少4位）"
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-sm text-cd-text" />
          <input type="password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)}
            placeholder="确认密码"
            className="w-full bg-cd-bg-input border border-white/5 rounded-lg px-3 py-2 text-sm text-cd-text" />
          <button onClick={setPassword}
            className="w-full py-2 bg-cd-accent/20 text-cd-accent rounded-lg border border-cd-accent/30 hover:bg-cd-accent/30 text-sm">
            启用应用锁
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Windows Hello */}
          <label className="flex items-center justify-between cursor-pointer">
            <span className="text-sm text-cd-text flex items-center gap-1.5">
              <Fingerprint size={14} /> Windows Hello 生物识别
            </span>
            <input type="checkbox" checked={cfg.useHello}
              onChange={e => update({ useHello: e.target.checked })} className="accent-cd-accent" />
          </label>
          {/* 闲置自动锁 */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-cd-text">闲置自动锁</span>
            <select value={cfg.idleMinutes} onChange={e => update({ idleMinutes: parseInt(e.target.value) })}
              className="bg-cd-bg-input border border-white/5 rounded px-2 py-1 text-xs text-cd-text">
              <option value={0}>不自动锁</option>
              <option value={5}>5 分钟</option>
              <option value={10}>10 分钟</option>
              <option value={30}>30 分钟</option>
            </select>
          </div>
          {/* 模块级锁 */}
          <div className="space-y-1.5 pt-2 border-t border-white/5">
            <div className="text-xs text-cd-text-tertiary">模块级二次锁</div>
            {([
              ['diary', '日记'],
              ['profile', '深度画像'],
              ['settings', '设置'],
            ] as const).map(([k, label]) => (
              <label key={k} className="flex items-center justify-between cursor-pointer">
                <span className="text-xs text-cd-text-secondary">{label}</span>
                <input type="checkbox" checked={cfg.moduleLock[k]}
                  onChange={e => update({ moduleLock: { ...cfg.moduleLock, [k]: e.target.checked } })}
                  className="accent-cd-accent" />
              </label>
            ))}
          </div>
          <button onClick={disable}
            className="w-full py-2 bg-red-500/10 text-red-400 rounded-lg border border-red-400/20 hover:bg-red-500/20 text-sm">
            关闭应用锁
          </button>
        </div>
      )}
      {msg && <div className="text-xs text-cd-accent text-center">{msg}</div>}
    </div>
  )
}

// 主 Hook：在 App.tsx 使用
export function useAppLock() {
  const [cfg, setCfg] = useState(loadConfig())
  const [locked, setLocked] = useState(false)

  // 启动时若启用则锁定
  useEffect(() => {
    const c = loadConfig()
    setCfg(c)
    if (c.enabled) setLocked(true)
  }, [])

  // 闲置自动锁
  useIdleDetection(cfg.idleMinutes, () => {
    if (cfg.enabled) setLocked(true)
  })

  const unlock = useCallback(() => setLocked(false), [])

  return { locked, unlock, cfg }
}

// 模块级锁检查（用于日记等敏感模块）
export function checkModuleLock(module: 'diary' | 'profile' | 'settings'): boolean {
  const cfg = loadConfig()
  return cfg.enabled && cfg.moduleLock[module]
}
