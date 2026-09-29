import { useState, useEffect, useRef, useCallback, useMemo, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Coins, Heart, Sparkles, Package, ChevronRight, X, Utensils } from 'lucide-react'
import { useGrowthStore, type EquipSlot, type EquippedItem, type PetStage } from '../stores/growthStore'
import InventoryModal from './InventoryModal'

// ─── 装备槽配置 ──────────────────────────────────
const SLOT_CONFIG: Record<EquipSlot, { label: string; icon: string; placeholder: string }> = {
  head: { label: '头部', icon: '🪖', placeholder: '👒' },
  body: { label: '身体', icon: '🧥', placeholder: '👕' },
  accessory: { label: '饰品', icon: '💍', placeholder: '📿' },
  weapon: { label: '武器', icon: '⚔️', placeholder: '🪄' },
}

const SLOT_ORDER: EquipSlot[] = ['head', 'body', 'weapon', 'accessory']

const PET_STAGE_LABELS: Record<PetStage, string> = {
  egg: '蛋',
  hatchling: '幼体',
  juvenile: '少年',
  adult: '成年',
  ultimate: '终极',
}

const PET_STAGE_EMOJI: Record<PetStage, string> = {
  egg: '🥚',
  hatchling: '🐣',
  juvenile: '🐥',
  adult: '🦅',
  ultimate: '✨',
}

const FEED_COST = 10

interface RpgPanelProps {
  /** 紧凑模式：在 Sidebar 等窄空间使用 */
  compact?: boolean
}

export default function RpgPanel({ compact = false }: RpgPanelProps) {
  const hp = useGrowthStore(s => s.hp)
  const maxHp = useGrowthStore(s => s.maxHp)
  const mp = useGrowthStore(s => s.mp)
  const maxMp = useGrowthStore(s => s.maxMp)
  const gold = useGrowthStore(s => s.gold)
  const equippedItems = useGrowthStore(s => s.equippedItems)
  const inventory = useGrowthStore(s => s.inventory)
  const petStage = useGrowthStore(s => s.petStage)
  const petExp = useGrowthStore(s => s.petExp)
  const petExpToNext = useGrowthStore(s => s.petExpToNext)
  const petCanEvolve = useGrowthStore(s => s.petCanEvolve)
  const feedPet = useGrowthStore(s => s.feedPet)
  const fetchPet = useGrowthStore(s => s.fetchPet)

  const [inventoryOpen, setInventoryOpen] = useState(false)
  const [inventoryInitialSlot, setInventoryInitialSlot] = useState<EquipSlot | null>(null)
  const [slotPicker, setSlotPicker] = useState<EquipSlot | null>(null)
  const [feeding, setFeeding] = useState(false)
  const [feedMsg, setFeedMsg] = useState<string | null>(null)
  const feedMsgTimer = useRef<number | null>(null)

  // 初次挂载拉取宠物状态和装备
  useEffect(() => {
    void fetchPet()
  }, [fetchPet])

  // 清理定时器
  useEffect(() => {
    return () => {
      if (feedMsgTimer.current) window.clearTimeout(feedMsgTimer.current)
    }
  }, [])

  // 槽位 → 已装备道具
  const equippedMap = useMemo(() => {
    const map = new Map<EquipSlot, EquippedItem>()
    for (const e of equippedItems) map.set(e.slot, e)
    return map
  }, [equippedItems])

  // 当前槽位可装备的物品（从背包筛选 equipment 类型且 slot 匹配）
  const slotCandidates = useMemo(() => {
    if (!slotPicker) return []
    return inventory.filter(i => i.type === 'equipment' && i.slot === slotPicker)
  }, [slotPicker, inventory])

  const hpPct = maxHp > 0 ? Math.max(0, Math.min(100, (hp / maxHp) * 100)) : 0
  const mpPct = maxMp > 0 ? Math.max(0, Math.min(100, (mp / maxMp) * 100)) : 0
  const petExpPct = petExpToNext > 0 ? Math.min(100, (petExp / petExpToNext) * 100) : 0

  const handleSlotClick = useCallback((slot: EquipSlot) => {
    setSlotPicker(slot)
    setInventoryInitialSlot(slot)
  }, [])

  const handleOpenInventory = useCallback(() => {
    setInventoryInitialSlot(null)
    setInventoryOpen(true)
  }, [])

  const handleFeed = useCallback(async () => {
    if (feeding) return
    if (gold < FEED_COST) {
      setFeedMsg(`金币不足，需要 ${FEED_COST} 金币`)
      if (feedMsgTimer.current) window.clearTimeout(feedMsgTimer.current)
      feedMsgTimer.current = window.setTimeout(() => setFeedMsg(null), 2500)
      return
    }
    setFeeding(true)
    try {
      const res = await feedPet()
      if (res) {
        setFeedMsg(res.message || `+${res.exp_gained} 宠物经验`)
      } else {
        setFeedMsg('喂养失败')
      }
    } catch {
      setFeedMsg('喂养失败')
    } finally {
      setFeeding(false)
      if (feedMsgTimer.current) window.clearTimeout(feedMsgTimer.current)
      feedMsgTimer.current = window.setTimeout(() => setFeedMsg(null), 2500)
    }
  }, [feeding, gold, feedPet])

  return (
    <div className={`rpg-panel ${compact ? 'compact' : ''}`}>
      {/* ─── HP / MP 条 ─────────────────────────── */}
      <div className="space-y-1.5">
        <StatusBar
          label="HP"
          value={hp}
          max={maxHp}
          pct={hpPct}
          gradient="linear-gradient(90deg, #ef4444, #f87171)"
          icon={<Heart size={10} className="text-red-400" fill="currentColor" />}
        />
        <StatusBar
          label="MP"
          value={mp}
          max={maxMp}
          pct={mpPct}
          gradient="linear-gradient(90deg, #3b82f6, #60a5fa)"
          icon={<Sparkles size={10} className="text-blue-400" />}
        />
      </div>

      {/* ─── 金币 + 背包按钮 ──────────────────── */}
      <div className="flex items-center gap-1.5 mt-2">
        <div
          className="flex items-center gap-1 px-2 py-1 rounded-xl flex-1"
          style={{
            background: 'linear-gradient(90deg, rgba(251,191,36,0.12), rgba(255,149,0,0.08))',
            border: '1px solid rgba(251,191,36,0.25)',
          }}
          title={`金币：${gold}`}
        >
          <Coins size={12} className="text-amber-400" fill="currentColor" />
          <span className="text-[11px] font-bold text-amber-500">{gold}</span>
        </div>
        <button
          onClick={handleOpenInventory}
          className="flex items-center gap-1 px-2 py-1 rounded-xl text-[11px] text-cd-text-secondary hover:text-cd-text transition-colors"
          style={{
            background: 'var(--cd-bg-secondary)',
            border: '1px solid var(--cd-border)',
          }}
          aria-label="打开背包"
        >
          <Package size={12} />
          <span>背包</span>
          <span className="text-[10px] text-cd-text-tertiary">({inventory.length})</span>
        </button>
      </div>

      {/* ─── 装备槽 ────────────────────────────── */}
      <div className="mt-2">
        <div className="text-[10px] text-cd-text-tertiary mb-1 px-0.5">装备</div>
        <div className="grid grid-cols-4 gap-1">
          {SLOT_ORDER.map(slot => {
            const eq = equippedMap.get(slot)
            const cfg = SLOT_CONFIG[slot]
            return (
              <button
                key={slot}
                onClick={() => handleSlotClick(slot)}
                title={`${cfg.label}：${eq ? eq.name : '空'}`}
                className="relative aspect-square rounded-xl flex items-center justify-center transition-all hover:scale-105"
                style={{
                  background: eq ? 'rgba(175,82,222,0.1)' : 'var(--cd-bg-secondary)',
                  border: `1px solid ${eq ? 'rgba(175,82,222,0.4)' : 'var(--cd-border)'}`,
                }}
                aria-label={`${cfg.label}槽位，${eq ? `已装备 ${eq.name}` : '空'}`}
              >
                <span className="text-lg leading-none">{eq ? (eq.icon || cfg.icon) : cfg.placeholder}</span>
                {eq && (
                  <span className="absolute -top-1 -right-1 w-3 h-3 rounded-full" style={{
                    background: 'linear-gradient(135deg, #af52de, #ff9500)',
                  }} />
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* ─── 宠物状态 ──────────────────────────── */}
      <div className="mt-2 px-2 py-1.5 rounded-xl" style={{
        background: 'rgba(175,82,222,0.06)',
        border: '1px solid rgba(175,82,222,0.18)',
      }}>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-1">
            <span className="text-sm">{PET_STAGE_EMOJI[petStage]}</span>
            <span className="text-[11px] font-medium text-cd-text">{PET_STAGE_LABELS[petStage]}</span>
            {petCanEvolve && (
              <span className="text-[9px] px-1 rounded-lg bg-amber-400/20 text-amber-500 animate-pulse">可进化</span>
            )}
          </div>
          <button
            onClick={handleFeed}
            disabled={feeding}
            className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-lg text-cd-orange hover:bg-cd-orange/10 disabled:opacity-50"
            title={`喂养宠物（消耗 ${FEED_COST} 金币）`}
            aria-label="喂养宠物"
          >
            <Utensils size={10} />
            <span>喂养</span>
          </button>
        </div>
        <div className="h-1 rounded-full bg-cd-bg-tertiary overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            style={{ background: 'linear-gradient(90deg, #af52de, #ff9500)' }}
            initial={{ width: 0 }}
            animate={{ width: `${petExpPct}%` }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
          />
        </div>
        <div className="text-[9px] text-cd-text-tertiary mt-0.5 text-right">
          {petExp} / {petExpToNext}
        </div>
        {feedMsg && (
          <div className="text-[10px] text-cd-orange mt-0.5 text-center">{feedMsg}</div>
        )}
      </div>

      {/* ─── 背包弹窗 ──────────────────────────── */}
      <InventoryModal
        open={inventoryOpen}
        onClose={() => setInventoryOpen(false)}
        initialSlot={inventoryInitialSlot}
      />

      {/* ─── 装备槽选择弹层 ────────────────────── */}
      <AnimatePresence>
        {slotPicker && (
          <SlotPicker
            slot={slotPicker}
            equipped={equippedMap.get(slotPicker) || null}
            candidates={slotCandidates}
            onClose={() => setSlotPicker(null)}
            onOpenInventory={() => {
              setInventoryInitialSlot(slotPicker)
              setInventoryOpen(true)
              setSlotPicker(null)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── HP/MP 状态条 ─────────────────────────────────
interface StatusBarProps {
  label: string
  value: number
  max: number
  pct: number
  gradient: string
  icon: ReactNode
}

function StatusBar({ label, value, max, pct, gradient, icon }: StatusBarProps) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex items-center gap-0.5 w-7 shrink-0">
        {icon}
        <span className="text-[9px] font-bold text-cd-text-tertiary">{label}</span>
      </div>
      <div className="flex-1 h-2.5 rounded-full overflow-hidden relative" style={{ background: 'var(--cd-bg-tertiary)' }}>
        <motion.div
          className="h-full rounded-full relative"
          style={{ background: gradient }}
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
        >
          {/* 光泽效果 */}
          <span className="absolute inset-0" style={{
            background: 'linear-gradient(180deg, rgba(255,255,255,0.3) 0%, transparent 50%)',
          }} />
        </motion.div>
      </div>
      <span className="text-[9px] text-cd-text-secondary w-12 text-right tabular-nums shrink-0">
        {Math.round(value)}/{Math.round(max)}
      </span>
    </div>
  )
}

// ─── 装备槽选择浮层 ────────────────────────────────
interface SlotPickerProps {
  slot: EquipSlot
  equipped: EquippedItem | null
  candidates: { item_key: string; name: string; icon: string; rarity: string; quantity: number }[]
  onClose: () => void
  onOpenInventory: () => void
}

function SlotPicker({ slot, equipped, candidates, onClose, onOpenInventory }: SlotPickerProps) {
  const equipItem = useGrowthStore(s => s.equipItem)
  const unequipItem = useGrowthStore(s => s.unequipItem)
  const pickerRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(false)

  // ESC 关闭
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // 点击外部关闭
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    // 延迟绑定，避免触发本点击事件
    const t = window.setTimeout(() => {
      document.addEventListener('mousedown', onClick)
    }, 0)
    return () => {
      window.clearTimeout(t)
      document.removeEventListener('mousedown', onClick)
    }
  }, [onClose])

  const cfg = SLOT_CONFIG[slot]

  const handleEquip = async (itemKey: string) => {
    if (loading) return
    setLoading(true)
    try {
      await equipItem(itemKey)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  const handleUnequip = async () => {
    if (loading || !equipped) return
    setLoading(true)
    try {
      await unequipItem(slot)
      onClose()
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        ref={pickerRef}
        className="rounded-xl shadow-2xl w-72 overflow-hidden bg-cd-card border border-cd-border"
        initial={{ scale: 0.9, opacity: 0, y: 10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.9, opacity: 0, y: 10 }}
        transition={{ duration: 0.18 }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`${cfg.label}槽位选择`}
      >
        <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: '1px solid var(--cd-border)' }}>
          <div className="flex items-center gap-1.5">
            <span className="text-base">{cfg.icon}</span>
            <span className="text-sm font-semibold text-cd-text">{cfg.label}</span>
          </div>
          <button onClick={onClose} className="text-cd-text-tertiary hover:text-cd-text p-1 rounded-lg hover:bg-cd-hover" aria-label="关闭">
            <X size={14} />
          </button>
        </div>

        <div className="p-2 max-h-72 overflow-y-auto">
          {/* 当前装备 */}
          {equipped && (
            <div className="mb-2">
              <div className="text-[10px] text-cd-text-tertiary px-1 mb-1">当前装备</div>
              <div className="flex items-center gap-2 px-2 py-1.5 rounded-xl" style={{
                background: 'rgba(175,82,222,0.08)',
                border: '1px solid rgba(175,82,222,0.3)',
              }}>
                <span className="text-lg">{equipped.icon || cfg.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-medium text-cd-text truncate">{equipped.name}</div>
                  <div className="text-[10px] text-cd-text-tertiary">{equipped.rarity}</div>
                </div>
                <button
                  onClick={handleUnequip}
                  disabled={loading}
                  className="text-[10px] px-2 py-1 rounded-lg bg-cd-red/10 text-cd-red hover:bg-cd-red/20 disabled:opacity-50"
                >
                  卸下
                </button>
              </div>
            </div>
          )}

          {/* 可装备候选 */}
          <div className="text-[10px] text-cd-text-tertiary px-1 mb-1">
            可装备 {candidates.length > 0 && `(${candidates.length})`}
          </div>
          {candidates.length === 0 ? (
            <div className="text-center py-4 text-xs text-cd-text-tertiary">
              背包中没有该槽位的装备
            </div>
          ) : (
            <div className="space-y-1">
              {candidates.map(item => (
                <button
                  key={item.item_key}
                  onClick={() => handleEquip(item.item_key)}
                  disabled={loading}
                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl hover:bg-cd-hover disabled:opacity-50 text-left transition-colors"
                >
                  <span className="text-lg">{item.icon || cfg.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-cd-text truncate">{item.name}</div>
                    <div className="text-[10px] text-cd-text-tertiary">{item.rarity}{item.quantity > 1 && ` · ×${item.quantity}`}</div>
                  </div>
                  <ChevronRight size={12} className="text-cd-text-tertiary" />
                </button>
              ))}
            </div>
          )}

          <button
            onClick={onOpenInventory}
            className="mt-2 w-full flex items-center justify-center gap-1 px-2 py-1.5 rounded-xl text-[11px] text-cd-purple hover:bg-cd-purple/10"
          >
            <Package size={11} />
            打开完整背包
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
