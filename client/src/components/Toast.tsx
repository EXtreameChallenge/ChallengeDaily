import { useState, useCallback, useRef, createContext, useContext, type ReactNode } from 'react'
import { CheckCircle, XCircle, AlertCircle, Info, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface ToastAction {
  label: string
  onClick: () => void
}

interface Toast {
  id: number
  type: ToastType
  message: string
  action?: ToastAction
  duration?: number  // 自定义持续时间
}

interface ToastContextValue {
  toast: (type: ToastType, message: string, options?: { action?: ToastAction; duration?: number }) => void
  success: (message: string, options?: { action?: ToastAction; duration?: number }) => void
  error: (message: string, options?: { action?: ToastAction; duration?: number }) => void
  warning: (message: string, options?: { action?: ToastAction; duration?: number }) => void
  info: (message: string, options?: { action?: ToastAction; duration?: number }) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

let _toastId = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const removeToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const addToast = useCallback((type: ToastType, message: string, options?: { action?: ToastAction; duration?: number }) => {
    const id = ++_toastId
    const duration = options?.duration ?? (options?.action ? 6000 : 4000) // 有 action 时延长到 6 秒
    setToasts(prev => [...prev.slice(-4), { id, type, message, action: options?.action, duration }])
    const timer = setTimeout(() => removeToast(id), duration)
    timers.current.set(id, timer)
  }, [removeToast])

  const value: ToastContextValue = {
    toast: addToast,
    success: (msg, opts) => addToast('success', msg, opts),
    error: (msg, opts) => addToast('error', msg, opts),
    warning: (msg, opts) => addToast('warning', msg, opts),
    info: (msg, opts) => addToast('info', msg, opts),
  }

  const ICON_MAP: Record<ToastType, typeof CheckCircle> = {
    success: CheckCircle,
    error: XCircle,
    warning: AlertCircle,
    info: Info,
  }
  const COLOR_MAP: Record<ToastType, string> = {
    success: '#27AE60',
    error: '#E53935',
    warning: '#FF9800',
    info: '#2196F3',
  }

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"
        style={{ maxWidth: 360 }}
      >
        {toasts.map(t => {
          const Icon = ICON_MAP[t.type]
          return (
            <div
              key={t.id}
              className="animate-slide-in pointer-events-auto flex items-start gap-2.5 px-4 py-3 rounded-xl shadow-lg border bg-cd-card"
              style={{ borderColor: COLOR_MAP[t.type] + '30' }}
            >
              <Icon size={16} className="shrink-0 mt-0.5" style={{ color: COLOR_MAP[t.type] }} />
              <p className="text-sm text-cd-text flex-1">{t.message}</p>
              {t.action && (
                <button
                  onClick={() => {
                    t.action!.onClick()
                    removeToast(t.id)
                  }}
                  className="shrink-0 text-xs font-medium text-cd-green hover:text-cd-green-dark transition-colors px-2 py-0.5 rounded bg-cd-green/5"
                >
                  {t.action.label}
                </button>
              )}
              <button
                onClick={() => removeToast(t.id)}
                className="shrink-0 text-cd-text-tertiary hover:text-cd-text transition-colors"
              >
                <X size={14} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
