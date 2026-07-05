import { Component, type ReactNode, type ErrorInfo } from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full min-h-[400px] p-8 text-center">
          <div className="w-14 h-14 rounded-2xl bg-cd-red-light flex items-center justify-center mb-4">
            <AlertTriangle size={28} className="text-cd-red" />
          </div>
          <h2 className="text-lg font-semibold text-cd-text mb-2">页面出了点问题</h2>
          <p className="text-sm text-cd-text-secondary mb-1 max-w-md">
            抱歉，这个页面发生了意外错误。你可以尝试重新加载，如果问题持续，请重启应用。
          </p>
          {this.state.error && (
            <details className="mt-3 text-left max-w-md">
              <summary className="text-xs text-cd-text-tertiary cursor-pointer">错误详情</summary>
              <pre className="mt-1 text-xs text-cd-red bg-cd-red-light p-3 rounded-lg overflow-auto max-h-40">
                {this.state.error.message}
              </pre>
            </details>
          )}
          <button
            onClick={this.handleReload}
            className="mt-5 flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium bg-cd-green text-white hover:bg-cd-green-dark transition-colors"
          >
            <RotateCcw size={14} />
            重新加载
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
