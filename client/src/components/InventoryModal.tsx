import { useState, useEffect, useRef, useCallback, useReducer, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Package, Sparkles, Lock } from 'lucide-react'
import { useGrowthStore, type InventoryItem, type ItemRarity, type EquipSlot, type DropResult } from '../stores/growthStore'

// ─── 稀有度配置 ──────────────────────────────────
const RARITY_CONFIG: Record<ItemRarity, { color: string; bg: string; border: string; glow: string; label: string }> = {
  common: { color: '#9CA3AF', bg: 'rgba(156,163,175,0.1)', border: 'rgba(156,163,175,0.4)', glow: '0 0 0 rgba(156,163,175,0)', label: '普通' },
  rare: { color: '#60A5FA', bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.5)', glow: '0 0 12px rgba(96,165,250,0.3)', label: '稀有' },
  epic: { color: '#C084FC', bg: 'rgba(192,132,252,0.15)', border: 'rgba(192,132,252,0.6)', glow: '0 0 16px rgba(192,132,252,0.4)', label: '史诗' },
  legendary: { color: '#FBBF24', bg: 'rgba(251,191,36,0.18)', border: 'rgba(251,191,36,0.7)', glow: '0 0 20px rgba(251,191,36,0.5)', label: '传说' },
}

type TabKey = 'all' | 'equipment' | 'consumable' | 'chest'

const TAB_LABELS: Record<TabKey, string> = {
  all: '全部',
  equipment: '装备',
  consumable: '消耗品',
  chest: '宝箱',
}

interface InventoryModalProps {
  open: boolean
  onClose: () => void
  initialSlot?: EquipSlot | null
}

interface ActionState {
  loading: boolean
  message: string | null
  message_type: 'success' | 'error' | 'info' | null
}

type ActionReducerAction =
  | { type: 'start' }
  | { type: 'success'; message: string }
  | { type: 'error'; message: string }
  | { type: 'info'; message: string }
  | { type: 'clear' }

function actionReducer(_state: ActionState, action: ActionReducerAction): ActionState {
  switch (action.type) {
    case 'start': return { loading: true, message: null, message_type: null }
    case 'success': return { loading: false, message: action.message, message_type: 'success' }
    case 'error': return { loading: false, message: action.message, message_type: 'error' }
    case 'info': return { loading: false, message: action.message, message_type: 'info' }
    case 'clear': return { loading: false, message: null, message_type: null }
    default: return _state
  }
}

export default function InventoryModal({ open, onClose, initialSlot = null }: InventoryModalProps) {
  const inventory = useGrowthStore(s => s.inventory)
  const equippedItems = useGrowthStore(s => s.equippedItems)
  const consumeItem = useGrowthStore(s => s.useItem)
  const equipItem = useGrowthStore(s => s.equipItem)
  const unequipItem = useGrowthStore(s => s.unequipItem)
  const openChest = useGrowthStore(s => s.openChest)
  const fetchInventory = useGrowthStore(s => s.fetchInventory)
  const fetchEquipment = useGrowthStore(s => s.fetchEquipment)
  const [tab, setTab] = useState<TabKey>('all')
  const [hoveredItem, setHoveredItem] = useState<InventoryItem | null>(null)
  const [dropResult, setDropResult] = useState<DropResult | null>(null)
  const [state, dispatch] = useReducer(actionReducer, { loading: false, message: null, message_type: null })

  const dialogRef = useRef<HTMLDivElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)
  const messageTimer = useRef<number | null>(null)

  // 焦点管理：打开时聚焦关闭按钮，关闭时清理
  useEffect(() => {
    if (open) {
      // 等 DOM 渲染完成
      const t = window.setTimeout(() => closeBtnRef.current?.focus(), 50)
      return () => window.clearTimeout(t)
    }
  }, [open])

  // ESC 关闭 + 焦点陷阱
  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key === 'Tab' && dialogRef.current) {
        // 简单焦点陷阱：在 modal 内循环
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
        if (focusable.length === 0) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  // 清理消息定时器
  useEffect(() => {
    return () => {
      if (messageTimer.current) window.clearTimeout(messageTimer.current)
    }
  }, [])

  const showMessage = useCallback((type: 'success' | 'error' | 'info', msg: string) => {
    dispatch({ type, message: msg })
    if (messageTimer.current) window.clearTimeout(messageTimer.current)
    messageTimer.current = window.setTimeout(() => dispatch({ type: 'clear' }), 3000)
  }, [])

  // 初次打开拉取背包
  useEffect(() => {
    if (open) {
      void fetchInventory()
      void fetchEquipment()
      // 根据 initialSlot 跳到装备标签
      if (initialSlot) setTab('equipment')
    }
  }, [open, initialSlot, fetchInventory, fetchEquipment])

  // 按标签筛选
  const filteredItems = useMemo(() => {
    if (tab === 'all') return inventory
    return inventory.filter(i => i.type === tab)
  }, [inventory, tab])

  // 已装备道具 item_key 集合（便于显示状态）
  const equippedKeys = useMemo(() => new Set(equippedItems.map(e => e.item_key)), [equippedItems])

  const handleItemClick = useCallback(async (item: InventoryItem) => {
    if (state.loading) return
    dispatch({ type: 'start' })
    try {
      if (item.type === 'equipment') {
        // 已装备 → 卸下；未装备 → 装备
        if (item.slot && equippedKeys.has(item.item_key)) {
          await unequipItem(item.slot)
          showMessage('success', `卸下 ${item.name}`)
        } else {
          const res = await equipItem(item.item_key)
          if (res) showMessage('success', `装备 ${item.name}`)
          else showMessage('error', '装备失败')
        }
      } else if (item.type === 'consumable') {
        const res = await consumeItem(item.item_key)
        if (res) showMessage('success', res.message || `使用 ${item.name}`)
        else showMessage('error', '使用失败')
      } else if (item.type === 'chest') {
        const res = await openChest(item.item_key)
        if (res) {
          showMessage('success', res.message)
          setDropResult(res)
        } else {
          showMessage('error', '开启宝箱失败')
        }
      }
    } catch {
      showMessage('error', '操作失败')
    }
  }, [state.loading, equippedKeys, equipItem, unequipItem, consumeItem, openChest, showMessage])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-labelledby="inventory-modal-title"
        >
          <motion.div
            ref={dialogRef}
            className="flex flex-col rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden"
            style={{
              background: 'var(--cd-card)',
              border: '1px solid var(--cd-border)',
              maxHeight: '85vh',
            }}
            initial={{ scale: 0.92, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.92, opacity: 0, y: 20 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* 标题栏 */}
            <div
              className="flex items-center justify-between px-5 py-3.5 shrink-0"
              style={{ borderBottom: '1px solid var(--cd-border)', background: 'linear-gradient(90deg, rgba(175,82,222,0.08), rgba(255,149,0,0.08))' }}
            >
              <div className="flex items-center gap-2">
                <Package size={18} className="text-cd-purple" />
                <h2 id="inventory-modal-title" className="text-base font-bold text-cd-text">背包</h2>
                <span className="text-xs text-cd-text-tertiary">({inventory.length})</span>
              </div>
              <button
                ref={closeBtnRef}
                onClick={onClose}
                aria-label="关闭背包"
                className="text-cd-text-secondary hover:text-cd-text transition p-1 rounded-lg hover:bg-cd-hover"
              >
                <X size={18} />
              </button>
            </div>

            {/* 标签页 */}
            <div className="flex gap-1 px-4 pt-3 shrink-0" role="tablist">
              {(Object.keys(TAB_LABELS) as TabKey[]).map(key => {
                const count = key === 'all' ? inventory.length : inventory.filter(i => i.type === key).length
                return (
                  <button
                    key={key}
                    role="tab"
                    aria-selected={tab === key}
                    onClick={() => setTab(key)}
                    className={`px-3 py-1.5 rounded-t-md text-xs transition-colors ${
                      tab === key
                        ? 'text-cd-text font-medium'
                        : 'text-cd-text-tertiary hover:text-cd-text-secondary'
                    }`}
                    style={tab === key ? {
                      background: 'var(--cd-bg-secondary)',
                      borderBottom: '2px solid #af52de',
                    } : undefined}
                  >
                    {TAB_LABELS[key]} <span className="opacity-60">({count})</span>
                  </button>
                )
              })}
            </div>

            {/* 物品网格 */}
            <div
              className="flex-1 overflow-y-auto px-4 py-3"
              style={{ background: 'var(--cd-bg-secondary)', minHeight: 0 }}
              role="tabpanel"
            >
              {filteredItems.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-cd-text-tertiary">
                  <Package size={40} className="opacity-30 mb-2" />
                  <p className="text-sm">背包空空如也，去完成任务获得道具吧~</p>
                </div>
              ) : (
                <div className="grid grid-cols-4 sm:grid-cols-5 gap-2">
                  {filteredItems.map(item => (
                    <InventoryGridItem
                      key={item.item_key}
                      item={item}
                      equipped={equippedKeys.has(item.item_key)}
                      onHover={setHoveredItem}
                      onClick={() => handleItemClick(item)}
                      disabled={state.loading}
                    />
                  ))}
                </div>
              )}

              {/* 消息提示条 */}
              <AnimatePresence>
                {state.message && state.message_type && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 10 }}
                    className={`mt-3 px-3 py-2 rounded-2xl text-xs ${
                      state.message_type === 'success' ? 'bg-cd-green/10 text-cd-green' :
                      state.message_type === 'error' ? 'bg-cd-red/10 text-cd-red' :
                      'bg-cd-blue/10 text-cd-blue'
                    }`}
                  >
                    {state.message}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Tooltip */}
              {hoveredItem && (
                <div className="mt-3 p-3 rounded-2xl text-xs" style={{
                  background: 'var(--cd-card)',
                  border: `1px solid ${RARITY_CONFIG[hoveredItem.rarity].border}`,
                }}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-base">{hoveredItem.icon}</span>
                    <span className="font-semibold" style={{ color: RARITY_CONFIG[hoveredItem.rarity].color }}>
                      {hoveredItem.name}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded-lg" style={{
                      background: RARITY_CONFIG[hoveredItem.rarity].bg,
                      color: RARITY_CONFIG[hoveredItem.rarity].color,
                    }}>
                      {RARITY_CONFIG[hoveredItem.rarity].label}
                    </span>
                  </div>
                  <p className="text-cd-text-secondary leading-relaxed">{hoveredItem.description}</p>
                  {hoveredItem.stat_effects && Object.keys(hoveredItem.stat_effects).length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {Object.entries(hoveredItem.stat_effects).map(([k, v]) => (
                        <span key={k} className="text-[10px] px-1.5 py-0.5 rounded-lg bg-cd-bg-secondary text-cd-text-secondary">
                          {k}: +{v}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-1.5 text-[10px] text-cd-text-tertiary">
                    {hoveredItem.type === 'equipment' ? '点击装备/卸下' :
                     hoveredItem.type === 'consumable' ? '点击使用' :
                     '点击开启'}
                  </div>
                </div>
              )}
            </div>
          </motion.div>

          {/* 宝箱掉落结果弹层 */}
          <AnimatePresence>
            {dropResult && (
              <DropResultOverlay
                result={dropResult}
                onClose={() => setDropResult(null)}
              />
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

// ─── 单个背包格子 ──────────────────────────────────
interface GridItemProps {
  item: InventoryItem
  equipped: boolean
  onHover: (item: InventoryItem | null) => void
  onClick: () => void
  disabled: boolean
}

function InventoryGridItem({ item, equipped, onHover, onClick, disabled }: GridItemProps) {
  const rCfg = RARITY_CONFIG[item.rarity]
  return (
    <button
      onMouseEnter={() => onHover(item)}
      onMouseLeave={() => onHover(null)}
      onClick={onClick}
      disabled={disabled}
      aria-label={`${item.name} ${equipped ? '已装备' : ''}`}
      className="relative aspect-square rounded-2xl flex flex-col items-center justify-center transition-all hover:scale-105 disabled:opacity-50 disabled:cursor-wait"
      style={{
        background: rCfg.bg,
        border: `1.5px solid ${rCfg.border}`,
        boxShadow: item.rarity === 'legendary' ? rCfg.glow : 'none',
      }}
    >
      <span className="text-2xl leading-none">{item.icon || '📦'}</span>
      {item.quantity > 1 && (
        <span className="absolute bottom-0.5 right-1 text-[10px] font-bold text-cd-text" style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
          ×{item.quantity}
        </span>
      )}
      {equipped && (
        <span className="absolute top-0.5 left-0.5 text-[9px] px-1 rounded-lg bg-cd-green text-white font-bold">
          E
        </span>
      )}
      {item.rarity === 'legendary' && (
        <span className="absolute inset-0 rounded-2xl pointer-events-none" style={{
          background: 'linear-gradient(45deg, transparent 30%, rgba(251,191,36,0.15) 50%, transparent 70%)',
          animation: 'inv-legendary-shine 2s linear infinite',
        }} />
      )}
      <style>{`@keyframes inv-legendary-shine { 0% { transform: translateX(-100%) } 100% { transform: translateX(100%) } }`}</style>
    </button>
  )
}

// ─── 宝箱开启结果 ──────────────────────────────────
function DropResultOverlay({ result, onClose }: { result: DropResult; onClose: () => void }) {
  useEffect(() => {
    const t = window.setTimeout(onClose, 3500)
    return () => window.clearTimeout(t)
  }, [onClose])

  const dropped = result.dropped_item
  const rarity = dropped?.rarity || 'common'
  const rCfg = RARITY_CONFIG[rarity]

  return (
    <motion.div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="flex flex-col items-center p-8 rounded-2xl"
        style={{
          background: 'var(--cd-card)',
          border: `2px solid ${rCfg.border}`,
          boxShadow: rCfg.glow,
        }}
        initial={{ scale: 0.5, rotateY: 180 }}
        animate={{ scale: 1, rotateY: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-3 text-cd-purple">
          <Sparkles size={16} />
          <span className="text-sm font-medium">获得道具</span>
        </div>
        {dropped ? (
          <>
            <motion.div
              className="text-6xl mb-3"
              animate={rarity === 'legendary' ? { scale: [1, 1.15, 1] } : {}}
              transition={{ duration: 1.2, repeat: Infinity }}
            >
              {dropped.icon || '📦'}
            </motion.div>
            <div className="text-lg font-bold mb-1" style={{ color: rCfg.color }}>
              {dropped.name}
            </div>
            <div className="text-xs px-2 py-0.5 rounded-lg mb-2" style={{
              background: rCfg.bg,
              color: rCfg.color,
            }}>
              {rCfg.label}
            </div>
          </>
        ) : (
          <div className="text-4xl mb-3">
            <Lock size={48} className="text-cd-text-tertiary" />
          </div>
        )}
        <p className="text-sm text-cd-text-secondary text-center max-w-xs">{result.message}</p>
        <button
          onClick={onClose}
          className="mt-4 px-4 py-1.5 rounded-2xl text-xs bg-cd-purple text-white hover:opacity-90"
        >
          确定
        </button>
      </motion.div>
    </motion.div>
  )
}
