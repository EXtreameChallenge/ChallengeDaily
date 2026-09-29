import { useRelayEngine, type RelayCard } from './RelayEngine'
import { X, ChevronRight } from 'lucide-react'

/**
 * 接力卡片 UI 组件
 *
 * 设计理念：轻量、非阻塞、行动导向
 * - 从右侧滑入，不打断当前工作
 * - 标题+简短说明+1-3个行动按钮
 * - 主按钮高亮，用户一眼知道"推荐做什么"
 * - 可关闭，不强制
 *
 * 科学依据：
 * - BJ Fogg 行为模型：降低"行动"的能力门槛到一次点击
 * - 决策疲劳：最多3个选项，主按钮预推荐
 * - 自主感：永远可以关闭/忽略
 */

interface RelayCardViewProps {
  card: RelayCard
}

export function RelayCardView({ card }: RelayCardViewProps) {
  const { dismissCard, executeAction } = useRelayEngine()

  return (
    <div className="bg-cd-card border border-cd-green/30 rounded-xl shadow-lg shadow-cd-green/5 overflow-hidden animate-slide-in-right">
      {/* 顶部色条 */}
      <div className="h-1 bg-gradient-to-r from-cd-green to-cd-purple" />

      <div className="p-4">
        {/* 标题行 */}
        <div className="flex items-start justify-between gap-2 mb-2">
          <div className="flex items-center gap-2">
            {card.icon && <span className="text-lg">{card.icon}</span>}
            <h4 className="text-sm font-semibold text-cd-text">{card.title}</h4>
          </div>
          {card.dismissible && (
            <button
              onClick={() => dismissCard(card.id)}
              className="p-1 rounded-lg hover:bg-cd-hover transition shrink-0"
              title="关闭"
            >
              <X size={14} className="text-cd-text-tertiary" />
            </button>
          )}
        </div>

        {/* 说明文字 */}
        <p className="text-sm text-cd-text-secondary mb-4 leading-relaxed">
          {card.message}
        </p>

        {/* 行动按钮 */}
        <div className="flex flex-wrap gap-2">
          {card.actions.map((action, idx) => (
            <button
              key={idx}
              onClick={() => executeAction(card.id, idx)}
              className={`flex items-center gap-1 px-3 py-1.5 rounded-2xl text-xs font-medium transition ${
                action.primary
                  ? 'bg-cd-green text-white hover:opacity-90'
                  : 'border border-cd-border text-cd-text-secondary hover:bg-cd-hover hover:text-cd-text'
              }`}
            >
              {action.label}
              {action.primary && <ChevronRight size={12} />}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

/**
 * 接力卡片容器
 * 固定在右下角，堆叠显示当前活跃的接力卡片
 */
export function RelayCardContainer() {
  const { cards } = useRelayEngine()

  if (cards.length === 0) return null

  return (
    <div className="fixed bottom-20 right-4 z-50 flex flex-col gap-3 max-w-sm w-full pointer-events-none">
      {cards.slice(0, 3).map(card => (
        <div key={card.id} className="pointer-events-auto">
          <RelayCardView card={card} />
        </div>
      ))}
      {cards.length > 3 && (
        <div className="text-xs text-cd-text-tertiary text-center pointer-events-auto">
          还有 {cards.length - 3} 条建议
        </div>
      )}
    </div>
  )
}
