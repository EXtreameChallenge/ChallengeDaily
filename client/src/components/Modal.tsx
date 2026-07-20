import { X } from 'lucide-react'
import type { ReactNode } from 'react'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  maxWidth?: string
}

export default function Modal({ open, onClose, title, children, footer, maxWidth = 'max-w-lg' }: ModalProps) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={`flex flex-col rounded-2xl w-full ${maxWidth} shadow-2xl overflow-hidden`}
        style={{ background: 'var(--cd-card)', border: '1px solid var(--cd-border)', maxHeight: '90vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-5 py-3.5 shrink-0" style={{ borderBottom: '1px solid var(--cd-border)' }}>
          <h2 className="text-base font-bold text-cd-text">{title}</h2>
          <button
            onClick={onClose}
            className="text-cd-text-secondary hover:text-cd-text transition p-1 rounded hover:bg-cd-hover"
          >
            <X size={18} />
          </button>
        </div>

        {/* 表单内容 */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4" style={{ minHeight: 0 }}>
          {children}
        </div>

        {/* 底部按钮 */}
        {footer && (
          <div className="px-5 py-3.5 shrink-0" style={{ borderTop: '1px solid var(--cd-border)' }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
