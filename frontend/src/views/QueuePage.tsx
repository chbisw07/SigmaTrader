import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import TextField from '@mui/material/TextField'
import MenuItem from '@mui/material/MenuItem'
import Checkbox from '@mui/material/Checkbox'
import FormControlLabel from '@mui/material/FormControlLabel'
import InputAdornment from '@mui/material/InputAdornment'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  DataGrid,
  type GridColDef,
  type GridRenderCellParams,
  type GridRowSelectionModel,
} from '@mui/x-data-grid'

import { RiskRejectedHelpLink } from '../components/RiskRejectedHelpLink'
import {
  cancelOrder,
  fetchQueueOrders,
  executeOrder,
  updateOrder,
  type Order,
  type DistanceMode,
  type RiskSpec,
  type ExecutionTarget,
} from '../services/orders'
import { fetchBrokers, type BrokerInfo } from '../services/brokers'
import { fetchManagedRiskPositions } from '../services/managedRisk'
import {
  fetchBrokerCapabilities,
  fetchLtpForBroker,
  fetchMarginsForBroker,
  previewOrderForBroker,
  type BrokerCapabilities,
} from '../services/brokerRuntime'
import { fetchHoldings, type Holding } from '../services/positions'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'

export function WaitingQueuePanel({
  embedded = false,
  active = true,
}: {
  embedded?: boolean
  active?: boolean
}) {
  const { displayTimeZone } = useTimeSettings()
  const navigate = useNavigate()
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [busyCancelId, setBusyCancelId] = useState<number | null>(null)
  const [busyExecuteId, setBusyExecuteId] = useState<number | null>(null)
  const [editingOrder, setEditingOrder] = useState<Order | null>(null)
  const [editQty, setEditQty] = useState<string>('')
  const [editSide, setEditSide] = useState<'BUY' | 'SELL'>('BUY')
  const [editPrice, setEditPrice] = useState<string>('')
  const [editOrderType, setEditOrderType] = useState<
    'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
  >('MARKET')
  const [editProduct, setEditProduct] = useState<string>('MIS')
  const [editGtt, setEditGtt] = useState<boolean>(false)
  const [editExecutionTarget, setEditExecutionTarget] =
    useState<ExecutionTarget>('LIVE')
  const [savingEdit, setSavingEdit] = useState(false)
  const [fundsAvailable, setFundsAvailable] = useState<number | null>(null)
  const [fundsRequired, setFundsRequired] = useState<number | null>(null)
  const [fundsCurrency, setFundsCurrency] = useState<string | null>(null)
  const [fundsLoading, setFundsLoading] = useState(false)
  const [fundsError, setFundsError] = useState<string | null>(null)
  const [editTriggerPrice, setEditTriggerPrice] = useState<string>('')
  const [editTriggerPercent, setEditTriggerPercent] = useState<string>('')
  const [triggerMode, setTriggerMode] = useState<'PRICE' | 'PERCENT'>('PRICE')
  const [ltp, setLtp] = useState<number | null>(null)
  const [ltpError, setLtpError] = useState<string | null>(null)
  const [selectionModel, setSelectionModel] = useState<GridRowSelectionModel>([])
  const [bulkCancelling, setBulkCancelling] = useState(false)
  const [bulkExecuting, setBulkExecuting] = useState(false)
  const [loadedOnce, setLoadedOnce] = useState(false)
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [selectedBroker, setSelectedBroker] = useState<string>('zerodha')
  const [brokerCaps, setBrokerCaps] = useState<Record<string, BrokerCapabilities>>({})
  const [managedRiskCount, setManagedRiskCount] = useState<number>(0)
  const [holdings, setHoldings] = useState<Holding[] | null>(null)
  const [holdingsBroker, setHoldingsBroker] = useState<string | null>(null)
  const [holdingsLoading, setHoldingsLoading] = useState(false)
  const [holdingsError, setHoldingsError] = useState<string | null>(null)
  const [holdingsPct, setHoldingsPct] = useState<string>('100')

  const [riskSlEnabled, setRiskSlEnabled] = useState(false)
  const [riskSlMode, setRiskSlMode] = useState<DistanceMode>('PCT')
  const [riskSlValue, setRiskSlValue] = useState<string>('')
  const [riskSlAtrPeriod, setRiskSlAtrPeriod] = useState<string>('14')
  const [riskSlAtrTf, setRiskSlAtrTf] = useState<string>('1d')

  const [riskTrailEnabled, setRiskTrailEnabled] = useState(false)
  const [riskTrailMode, setRiskTrailMode] = useState<DistanceMode>('PCT')
  const [riskTrailValue, setRiskTrailValue] = useState<string>('')
  const [riskTrailAtrPeriod, setRiskTrailAtrPeriod] = useState<string>('14')
  const [riskTrailAtrTf, setRiskTrailAtrTf] = useState<string>('1d')

  const [riskActivationEnabled, setRiskActivationEnabled] = useState(false)
  const [riskActivationMode, setRiskActivationMode] = useState<DistanceMode>('PCT')
  const [riskActivationValue, setRiskActivationValue] = useState<string>('')
  const [riskActivationAtrPeriod, setRiskActivationAtrPeriod] = useState<string>('14')
  const [riskActivationAtrTf, setRiskActivationAtrTf] = useState<string>('1d')

  const [riskCooldownMs, setRiskCooldownMs] = useState<string>('')

  const getCaps = (brokerName?: string | null): BrokerCapabilities | null => {
    const name = (brokerName ?? selectedBroker ?? 'zerodha').toLowerCase()
    return brokerCaps[name] ?? null
  }

  const riskSummary = (spec?: RiskSpec | null): string | null => {
    if (!spec) return null
    const parts: string[] = []
    const fmt = (mode: DistanceMode, value: number, tf?: string) => {
      if (mode === 'PCT') return `${value}%`
      if (mode === 'ABS') return `₹${value}`
      return `ATR×${value}${tf ? ` ${tf}` : ''}`
    }
    if (spec.stop_loss?.enabled) {
      parts.push(
        `SL ${fmt(spec.stop_loss.mode, spec.stop_loss.value, spec.stop_loss.atr_tf)}`,
      )
    }
    if (spec.trailing_stop?.enabled) {
      parts.push(
        `Tr ${fmt(spec.trailing_stop.mode, spec.trailing_stop.value, spec.trailing_stop.atr_tf)}`,
      )
    }
    if (spec.trailing_activation?.enabled) {
      parts.push(
        `Act ${fmt(spec.trailing_activation.mode, spec.trailing_activation.value, spec.trailing_activation.atr_tf)}`,
      )
    }
    return parts.length ? parts.join(' • ') : null
  }

  const normalizeSymbolExchange = (
    rawSymbol: string,
    exchange?: string | null,
  ): { symbol: string; exchange: string } => {
    const baseExchange = (exchange ?? 'NSE').trim().toUpperCase() || 'NSE'
    const s = (rawSymbol ?? '').trim()
    if (s.includes(':')) {
      const [ex, sym] = s.split(':', 2)
      return {
        symbol: (sym ?? '').trim().toUpperCase(),
        exchange: (ex ?? '').trim().toUpperCase() || baseExchange,
      }
    }
    return { symbol: s.toUpperCase(), exchange: baseExchange }
  }

  const loadHoldings = async (brokerName: string) => {
    const b = (brokerName ?? 'zerodha').toLowerCase()
    try {
      setHoldingsLoading(true)
      setHoldingsError(null)
      const data = await fetchHoldings(b)
      setHoldings(data)
      setHoldingsBroker(b)
    } catch (err) {
      setHoldings(null)
      setHoldingsBroker(b)
      setHoldingsError(err instanceof Error ? err.message : 'Failed to load holdings')
    } finally {
      setHoldingsLoading(false)
    }
  }

  const loadQueue = async (options: { silent?: boolean } = {}) => {
    const { silent = false } = options
    try {
      if (!silent) {
        setLoading(true)
      }
      const data = await fetchQueueOrders(undefined, selectedBroker)
      setOrders(data)
      setSelectionModel((prev) =>
        prev.filter((id) => data.some((o) => o.id === id)),
      )
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load queue')
    } finally {
      if (!silent) {
        setLoading(false)
      }
    }
  }

  const loadManagedRiskCount = async () => {
    try {
      const data = await fetchManagedRiskPositions({
        status: 'ACTIVE,EXITING,PAUSED',
        broker_name: selectedBroker,
      })
      setManagedRiskCount(data.length)
    } catch {
      setManagedRiskCount(0)
    }
  }

  useEffect(() => {
    if (!active) return
    if (loadedOnce) return
    setLoadedOnce(true)
    void (async () => {
      try {
        const [list, caps] = await Promise.all([
          fetchBrokers(),
          fetchBrokerCapabilities(),
        ])
        setBrokers(list)
        const capsMap: Record<string, BrokerCapabilities> = {}
        for (const item of caps) {
          capsMap[item.name] = item.capabilities
        }
        setBrokerCaps(capsMap)
        if (list.length > 0 && !list.some((b) => b.name === selectedBroker)) {
          setSelectedBroker(list[0].name)
        }
      } catch {
        // Ignore; the queue can still operate with defaults.
      } finally {
        void loadQueue()
        void loadManagedRiskCount()
      }
    })()
  }, [active, loadedOnce, selectedBroker])

  useEffect(() => {
    if (!active || !loadedOnce) return
    void loadQueue()
    void loadManagedRiskCount()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBroker])

  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => {
      void loadQueue({ silent: true })
      void loadManagedRiskCount()
    }, 5000)
    return () => window.clearInterval(id)
  }, [active, selectedBroker])

  useEffect(() => {
    const loadLtp = async () => {
      if (!editingOrder) return
      try {
        setLtpError(null)
        const brokerName = (editingOrder.broker_name ?? selectedBroker ?? 'zerodha')
        const caps = getCaps(brokerName)
        if (caps && !caps.supports_ltp) {
          throw new Error(`LTP not available for ${brokerName}.`)
        }
        const data = await fetchLtpForBroker(
          brokerName,
          editingOrder.symbol,
          editingOrder.exchange ?? 'NSE',
        )
        setLtp(data.ltp)
      } catch (err) {
        setLtp(null)
        setLtpError(
          err instanceof Error ? err.message : 'Failed to fetch LTP.',
        )
      }
    }
    if (editingOrder && (editingOrder.order_type === 'SL' || editingOrder.order_type === 'SL-M')) {
      void loadLtp()
    }
  }, [editingOrder, selectedBroker])

  useEffect(() => {
    if (!editingOrder) return
    const brokerName = (editingOrder.broker_name ?? selectedBroker ?? 'zerodha').toLowerCase()
    if (holdingsLoading) return
    if (holdingsBroker === brokerName && holdings != null) return
    void loadHoldings(brokerName)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingOrder, selectedBroker])

  useEffect(() => {
    if (!editingOrder || ltp == null) return
    if (editOrderType !== 'SL' && editOrderType !== 'SL-M') return

    if (triggerMode === 'PRICE') {
      const tp = Number(editTriggerPrice)
      if (Number.isFinite(tp) && ltp > 0) {
        const pct = ((tp - ltp) / ltp) * 100
        setEditTriggerPercent(pct.toFixed(2))
      } else {
        setEditTriggerPercent('')
      }
    } else if (triggerMode === 'PERCENT') {
      const pct = Number(editTriggerPercent)
      if (Number.isFinite(pct) && ltp > 0) {
        const tp = ltp * (1 + pct / 100)
        setEditTriggerPrice(tp.toFixed(2))
      } else {
        setEditTriggerPrice('')
      }
    }
  }, [
    editingOrder,
    ltp,
    editOrderType,
    triggerMode,
    editTriggerPrice,
    editTriggerPercent,
  ])

  const openEditDialog = (order: Order) => {
    setEditingOrder(order)
    setEditQty(String(order.qty))
    setEditSide(order.side === 'SELL' ? 'SELL' : 'BUY')
    setEditPrice(order.price != null ? String(order.price) : '')
    if (order.order_type === 'LIMIT' || order.order_type === 'SL' || order.order_type === 'SL-M') {
      setEditOrderType(order.order_type as 'LIMIT' | 'SL' | 'SL-M')
    } else {
      setEditOrderType('MARKET')
    }
    setEditTriggerPrice(
      order.trigger_price != null ? String(order.trigger_price) : '',
    )
    setEditTriggerPercent(
      order.trigger_percent != null ? String(order.trigger_percent) : '',
    )
    setEditProduct(order.product)
    setEditGtt(order.gtt)
    setEditExecutionTarget(order.execution_target ?? 'LIVE')
    setFundsAvailable(null)
    setFundsRequired(null)
    setFundsCurrency(null)
    setFundsError(null)
    setTriggerMode('PRICE')
    setLtp(null)
    setLtpError(null)
    setError(null)

    const spec = order.risk_spec ?? null
    setRiskSlEnabled(Boolean(spec?.stop_loss?.enabled))
    setRiskSlMode(spec?.stop_loss?.mode ?? 'PCT')
    setRiskSlValue(spec?.stop_loss?.enabled ? String(spec.stop_loss.value) : '')
    setRiskSlAtrPeriod(String(spec?.stop_loss?.atr_period ?? 14))
    setRiskSlAtrTf(String(spec?.stop_loss?.atr_tf ?? '1d'))

    setRiskTrailEnabled(Boolean(spec?.trailing_stop?.enabled))
    setRiskTrailMode(spec?.trailing_stop?.mode ?? 'PCT')
    setRiskTrailValue(
      spec?.trailing_stop?.enabled ? String(spec.trailing_stop.value) : '',
    )
    setRiskTrailAtrPeriod(String(spec?.trailing_stop?.atr_period ?? 14))
    setRiskTrailAtrTf(String(spec?.trailing_stop?.atr_tf ?? '1d'))

    setRiskActivationEnabled(Boolean(spec?.trailing_activation?.enabled))
    setRiskActivationMode(spec?.trailing_activation?.mode ?? 'PCT')
    setRiskActivationValue(
      spec?.trailing_activation?.enabled
        ? String(spec.trailing_activation.value)
        : '',
    )
    setRiskActivationAtrPeriod(String(spec?.trailing_activation?.atr_period ?? 14))
    setRiskActivationAtrTf(String(spec?.trailing_activation?.atr_tf ?? '1d'))

    setRiskCooldownMs(spec?.cooldown_ms != null ? String(spec.cooldown_ms) : '')
  }

  const editBrokerName = (editingOrder?.broker_name ?? selectedBroker ?? 'zerodha').toLowerCase()
  const editProductNorm = (editProduct ?? '').trim().toUpperCase()
  const editQtyNum = Number(editQty)
  const editSymbolNorm = editingOrder
    ? normalizeSymbolExchange(editingOrder.symbol, editingOrder.exchange)
    : null
  const holdingQty = (() => {
    if (!editSymbolNorm || !holdings) return null
    const sym = editSymbolNorm.symbol
    const ex = editSymbolNorm.exchange
    const h = holdings.find((x) => {
      const hx = (x.exchange ?? 'NSE').toUpperCase()
      return hx === ex && x.symbol.toUpperCase() === sym
    })
    if (!h) return 0
    const q = Number(h.quantity ?? 0)
    return Number.isFinite(q) ? q : 0
  })()
  const queuedCncSellQty = (() => {
    if (!editSymbolNorm) return 0
    const sym = editSymbolNorm.symbol
    const ex = editSymbolNorm.exchange
    return orders
      .filter((o) => {
        if (editingOrder && o.id === editingOrder.id) return false
        if ((o.broker_name ?? selectedBroker ?? 'zerodha').toLowerCase() !== editBrokerName) {
          return false
        }
        if ((o.side ?? '').toUpperCase() !== 'SELL') return false
        if ((o.product ?? '').toUpperCase() !== 'CNC') return false
        if ((o.execution_target ?? 'LIVE').toUpperCase() !== 'LIVE') return false
        const on = normalizeSymbolExchange(o.symbol, o.exchange)
        return on.symbol === sym && on.exchange === ex
      })
      .reduce((acc, o) => acc + Number(o.qty ?? 0), 0)
  })()
  const availableHoldingQty =
    holdingQty == null ? null : Math.max(0, Math.floor(holdingQty) - Math.floor(queuedCncSellQty))

  const setQtyFromHoldings = (qty: number) => {
    const n = Math.max(0, Math.floor(qty))
    setEditQty(String(n))
  }

  const applyHoldingsPctToQty = () => {
    if (holdingQty == null) return
    const pct = Number(holdingsPct)
    if (!Number.isFinite(pct) || pct < 0) return
    const base = Math.floor(holdingQty)
    const computed = Math.floor((base * pct) / 100)
    if (editSide === 'SELL' && editProductNorm === 'CNC' && availableHoldingQty != null) {
      setQtyFromHoldings(Math.min(computed, availableHoldingQty))
      return
    }
    setQtyFromHoldings(computed)
  }

  const closeEditDialog = () => {
    setEditingOrder(null)
    setSavingEdit(false)
  }

  const refreshFundsPreview = async () => {
    if (!editingOrder) return
    setFundsLoading(true)
    setFundsError(null)
    try {
      const brokerName = (editingOrder.broker_name ?? selectedBroker ?? 'zerodha')
      const caps = getCaps(brokerName)
      if (caps && (!caps.supports_margin_preview || !caps.supports_order_preview)) {
        throw new Error(`Funds preview is not available for ${brokerName}.`)
      }

      const qty = Number(editQty)
      if (!Number.isFinite(qty) || qty <= 0) {
        throw new Error('Enter a positive quantity to preview funds.')
      }

      const price =
        editOrderType === 'MARKET' || editPrice.trim() === ''
          ? null
          : Number(editPrice)
      if (price != null && (!Number.isFinite(price) || price < 0)) {
        throw new Error('Enter a non-negative price to preview funds.')
      }

      let triggerPrice: number | null = null
      if (editOrderType === 'SL' || editOrderType === 'SL-M') {
        if (editTriggerPrice.trim() === '') {
          throw new Error('Enter a trigger price for SL / SL-M orders.')
        }
        const tp = Number(editTriggerPrice)
        if (!Number.isFinite(tp) || tp <= 0) {
          throw new Error('Trigger price must be a positive number.')
        }
        triggerPrice = tp
      }

      const margins = await fetchMarginsForBroker(brokerName)
      const preview = await previewOrderForBroker(brokerName, {
        symbol: editingOrder.symbol,
        exchange: editingOrder.exchange ?? 'NSE',
        side: editSide,
        qty,
        product: editProduct,
        order_type: editOrderType,
        price,
        trigger_price: triggerPrice,
      })

      setFundsAvailable(margins.available)
      setFundsRequired(preview.required)
      setFundsCurrency(preview.currency ?? '₹')
    } catch (err) {
      setFundsError(
        err instanceof Error
          ? err.message
          : 'Failed to fetch funds preview.',
      )
      setFundsAvailable(null)
      setFundsRequired(null)
      setFundsCurrency(null)
    } finally {
      setFundsLoading(false)
    }
  }

  const handleSaveEdit = async () => {
    if (!editingOrder) return
    setSavingEdit(true)
    try {
      const qty = Number(editQty)
      if (!Number.isFinite(qty) || qty <= 0) {
        throw new Error('Quantity must be a positive number')
      }

      const price =
        editOrderType === 'MARKET' || editPrice.trim() === ''
          ? null
          : Number(editPrice)
      if (price != null && (!Number.isFinite(price) || price < 0)) {
        throw new Error('Price must be a non-negative number')
      }

      let triggerPrice: number | undefined
      let triggerPercent: number | undefined
      if (editOrderType === 'SL' || editOrderType === 'SL-M') {
        if (editTriggerPrice.trim() === '') {
          throw new Error('Trigger price is required for SL / SL-M orders')
        }
        const tp = Number(editTriggerPrice)
        if (!Number.isFinite(tp) || tp <= 0) {
          throw new Error('Trigger price must be a positive number')
        }
        triggerPrice = tp
        if (editTriggerPercent.trim() !== '') {
          const tpc = Number(editTriggerPercent)
          if (!Number.isFinite(tpc)) {
            throw new Error('Trigger % must be a valid number')
          }
          triggerPercent = tpc
        }
      }

      const payload: {
        qty: number
        price: number | null
        side: 'BUY' | 'SELL'
        order_type: 'MARKET' | 'LIMIT' | 'SL' | 'SL-M'
        product: string
        gtt: boolean
        execution_target: ExecutionTarget
        trigger_price?: number
        trigger_percent?: number
        risk_spec?: RiskSpec | null
      } = {
        qty,
        price,
        side: editSide,
        order_type: editOrderType,
        product: editProduct,
        gtt: editGtt,
        execution_target: editExecutionTarget,
      }
      if (triggerPrice !== undefined) {
        payload.trigger_price = triggerPrice
      }
      if (triggerPercent !== undefined) {
        payload.trigger_percent = triggerPercent
      }

      const parseDistance = (
        enabled: boolean,
        mode: DistanceMode,
        valueRaw: string,
        atrPeriodRaw: string,
        atrTf: string,
        label: string,
      ) => {
        if (!enabled) {
          return { enabled: false, mode, value: 0 }
        }
        const v = Number(valueRaw)
        if (!Number.isFinite(v) || v <= 0) {
          throw new Error(`${label} value must be > 0 when enabled`)
        }
        if (mode === 'ATR') {
          const p = Number(atrPeriodRaw)
          if (!Number.isFinite(p) || p < 2) {
            throw new Error(`${label} ATR period must be >= 2`)
          }
          return { enabled: true, mode, value: v, atr_period: p, atr_tf: atrTf }
        }
        return { enabled: true, mode, value: v }
      }

      const anyRiskEnabled =
        riskSlEnabled || riskTrailEnabled || riskActivationEnabled

      let cooldownMs: number | null | undefined
      if (riskCooldownMs.trim() !== '') {
        const cd = Number(riskCooldownMs)
        if (!Number.isFinite(cd) || cd < 0) {
          throw new Error('Cooldown ms must be a non-negative integer')
        }
        cooldownMs = Math.floor(cd)
      }

      payload.risk_spec = anyRiskEnabled
        ? {
            stop_loss: parseDistance(
              riskSlEnabled,
              riskSlMode,
              riskSlValue,
              riskSlAtrPeriod,
              riskSlAtrTf,
              'Stop-loss',
            ),
            trailing_stop: parseDistance(
              riskTrailEnabled,
              riskTrailMode,
              riskTrailValue,
              riskTrailAtrPeriod,
              riskTrailAtrTf,
              'Trailing stop-loss',
            ),
            trailing_activation: parseDistance(
              riskActivationEnabled,
              riskActivationMode,
              riskActivationValue,
              riskActivationAtrPeriod,
              riskActivationAtrTf,
              'Trailing profit activation',
            ),
            exit_order_type: 'MARKET',
            ...(cooldownMs != null ? { cooldown_ms: cooldownMs } : {}),
          }
        : null

      const updated = await updateOrder(editingOrder.id, payload)

      setOrders((prev) =>
        prev.map((o) => (o.id === updated.id ? updated : o)),
      )
      closeEditDialog()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update order')
      setSavingEdit(false)
    }
  }

  const handleCancel = async (orderId: number) => {
    setBusyCancelId(orderId)
    try {
      setSuccessMessage(null)
      const updated = await cancelOrder(orderId)
      setOrders((prev) =>
        prev.filter((o) => o.id !== updated.id),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel order')
    } finally {
      setBusyCancelId(null)
    }
  }

  const handleExecute = async (orderId: number) => {
    setBusyExecuteId(orderId)
    try {
      setSuccessMessage(null)
      const updated = await executeOrder(orderId)
      if (updated.gtt && updated.synthetic_gtt && updated.status === 'WAITING') {
        setOrders((prev) => prev.map((o) => (o.id === updated.id ? updated : o)))
        setSuccessMessage('Conditional order armed.')
      } else {
        setOrders((prev) => prev.filter((o) => o.id !== updated.id))
        setSuccessMessage('Order executed.')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute order')
    } finally {
      setBusyExecuteId(null)
    }
  }

  const handleSelectAll = () => {
    setSelectionModel(orders.map((o) => o.id))
  }

  const handleBulkCancel = async () => {
    const ids = selectionModel.map((id) => Number(id)).filter((id) =>
      Number.isFinite(id),
    )
    if (!ids.length) return
    const ok = window.confirm(
      `Cancel ${ids.length} selected order${ids.length > 1 ? 's' : ''}?`,
    )
    if (!ok) return
    setBulkCancelling(true)
    try {
      setSuccessMessage(null)
      await Promise.all(ids.map((id) => cancelOrder(id)))
      setOrders((prev) => prev.filter((o) => !ids.includes(o.id)))
      setSelectionModel([])
      setError(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to cancel selected orders',
      )
    } finally {
      setBulkCancelling(false)
    }
  }

  const handleBulkExecute = async () => {
    const ids = selectionModel.map((id) => Number(id)).filter((id) =>
      Number.isFinite(id),
    )
    if (!ids.length) return
    const ok = window.confirm(
      `Execute ${ids.length} selected order${ids.length > 1 ? 's' : ''}? This will send them to ${selectedBroker}.`,
    )
    if (!ok) return

    setBulkExecuting(true)
    setSuccessMessage(null)
    setError(null)
    const failures: Array<{ id: number; message: string }> = []
    try {
      // Execute sequentially to avoid broker/API rate limits.
      for (const id of ids) {
        try {
          await executeOrder(id)
        } catch (err) {
          const message =
            err instanceof Error ? err.message : 'Failed to execute order'
          failures.push({ id, message })
        }
      }

      // Refresh queue to reflect status changes even when the endpoint
      // returns an error after persisting a new status.
      await loadQueue({ silent: true })
      setSelectionModel([])

      if (failures.length > 0) {
        const first = failures[0]
        setError(
          `Failed to execute ${failures.length}/${ids.length} orders. First failure (order ${first.id}): ${first.message}`,
        )
      } else {
        setSuccessMessage(
          `Executed ${ids.length} order${ids.length > 1 ? 's' : ''}.`,
        )
      }
    } finally {
      setBulkExecuting(false)
    }
  }

  const columns: GridColDef[] = [
    {
      field: 'created_at',
      headerName: 'Created At',
      width: 190,
      valueFormatter: (value) =>
        typeof value === 'string'
          ? formatInDisplayTimeZone(value, displayTimeZone)
          : '',
    },
    {
      field: 'broker_name',
      headerName: 'Broker',
      width: 120,
      valueGetter: (_value, row) => {
        const order = row as Order
        return (order.broker_name ?? 'zerodha').toUpperCase()
      },
    },
    {
      field: 'origin',
      headerName: 'Source',
      width: 120,
      valueGetter: (_value, row) => {
        const order = row as Order
        const raw = String(order.origin ?? 'MANUAL').trim().toUpperCase()
        if (raw === 'TRADINGVIEW') return 'TradingView'
        return raw || 'MANUAL'
      },
    },
    {
      field: 'symbol',
      headerName: 'Symbol',
      width: 200,
    },
    {
      field: 'side',
      headerName: 'Side',
      width: 80,
    },
    {
      field: 'qty',
      headerName: 'Qty',
      width: 90,
      type: 'number',
    },
    {
      field: 'price',
      headerName: 'Price',
      width: 110,
      type: 'number',
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'trigger_price',
      headerName: 'Trigger',
      description: 'Trigger price for SL/SL-M orders and conditional (GTT) orders.',
      width: 110,
      type: 'number',
      valueFormatter: (value) =>
        value != null ? Number(value).toFixed(2) : '-',
    },
    {
      field: 'order_type',
      headerName: 'Type',
      width: 110,
      valueFormatter: (value, row) => {
        const order = row as Order
        const base = String(value ?? order.order_type ?? '')
        if (!order.gtt) return base
        return order.synthetic_gtt ? `${base} (COND)` : `${base} (GTT)`
      },
    },
    {
      field: 'product',
      headerName: 'Product',
      width: 110,
    },
    {
      field: 'status',
      headerName: 'Status',
      width: 170,
      renderCell: (params: GridRenderCellParams) => {
        const order = params.row as Order
        const value = params.value
        let base = String(value ?? order.status ?? '')
        if (
          order.gtt &&
          order.synthetic_gtt &&
          base === 'WAITING' &&
          order.armed_at
        ) {
          base = 'WAITING (ARMED)'
        }
        const label = order.execution_target === 'PAPER' ? `${base} (PAPER)` : base
        if (base === 'REJECTED_RISK') {
          return (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              <Typography variant="body2">{label}</Typography>
              <RiskRejectedHelpLink />
            </Box>
          )
        }
        return <Typography variant="body2">{label}</Typography>
      },
    },
    {
      field: 'execution_target',
      headerName: 'Target',
      width: 110,
      valueGetter: (_value, row) => {
        const order = row as Order
        return order.execution_target ?? (order.simulated ? 'PAPER' : 'LIVE')
      },
    },
    {
      field: 'gtt',
      headerName: 'Cond',
      description:
        'Whether this order is conditional: GTT (broker-managed) or Sigma (SigmaTrader-managed).',
      width: 80,
      valueFormatter: (_value, row) => {
        const order = row as Order
        if (!order.gtt) return 'No'
        return order.synthetic_gtt ? 'Sigma' : 'GTT'
      },
    },
    {
      field: 'risk_spec',
      headerName: 'Exits',
      description: 'SigmaTrader-managed risk exits (per-order).',
      width: 190,
      sortable: false,
      filterable: false,
      renderCell: (params: GridRenderCellParams) => {
        const order = params.row as Order
        const summary = riskSummary(order.risk_spec)
        if (summary) {
          return (
            <Tooltip title="Custom SigmaTrader-managed exits configured for this order.">
              <Chip size="small" color="info" variant="outlined" label={summary} />
            </Tooltip>
          )
        }
        return (
          <Tooltip title="No custom exits set on this order. Risk profile defaults may still apply when enabled.">
            <Chip size="small" color="warning" variant="outlined" label="No custom" />
          </Tooltip>
        )
      },
    },
    {
      field: 'actions',
      headerName: 'Actions',
      width: 220,
      sortable: false,
      filterable: false,
      renderCell: (params: GridRenderCellParams) => {
        const order = params.row as Order
        return (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button
              size="small"
              variant="outlined"
              onClick={() => openEditDialog(order)}
            >
              Edit
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="primary"
              disabled={busyExecuteId === order.id}
              onClick={() => {
                void handleExecute(order.id)
              }}
            >
              {busyExecuteId === order.id ? 'Executing…' : 'Execute'}
            </Button>
            <Button
              size="small"
              variant="outlined"
              color="error"
              disabled={busyCancelId === order.id}
              onClick={() => {
                void handleCancel(order.id)
              }}
            >
              {busyCancelId === order.id ? 'Cancelling…' : 'Cancel'}
            </Button>
          </Box>
        )
      },
    },
  ]

  if (!active) return null

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'baseline',
          justifyContent: 'space-between',
          gap: 2,
          mb: embedded ? 1.5 : 2,
          flexWrap: 'wrap',
        }}
      >
        <Box>
          {!embedded && (
            <Typography variant="h4" gutterBottom>
              Waiting Queue
            </Typography>
          )}
          <Typography color="text.secondary">
            Manual review queue for orders in WAITING state. You can edit,
            execute, or cancel pending orders before they are sent to the
            broker.
          </Typography>
          <Typography variant="caption" color="text.secondary">
            PAPER orders will execute via the simulated engine when their strategy
            execution target is set to PAPER.
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {managedRiskCount > 0 && (
            <Button
              size="small"
              variant="outlined"
              onClick={() => navigate('/queue?tab=managed_exits')}
            >
              Managed exits ({managedRiskCount})
            </Button>
          )}
          {brokers.length > 0 && (
            <TextField
              select
              size="small"
              label="Broker"
              value={selectedBroker}
              onChange={(e) => setSelectedBroker(e.target.value)}
              sx={{ minWidth: 170 }}
            >
              {brokers.map((b) => (
                <MenuItem key={b.name} value={b.name}>
                  {b.label}
                </MenuItem>
              ))}
            </TextField>
          )}
          <Button
            variant="outlined"
            size="small"
            onClick={() => {
              void loadQueue()
            }}
            disabled={loading}
          >
            Refresh
          </Button>
	          <Button
	            variant="outlined"
	            size="small"
	            onClick={handleSelectAll}
	            disabled={orders.length === 0}
	          >
	            Select all
	          </Button>
	          <Button
	            variant="contained"
	            size="small"
	            onClick={() => {
	              void handleBulkExecute()
	            }}
	            disabled={
	              selectionModel.length === 0
	              || bulkExecuting
	              || bulkCancelling
	              || busyExecuteId != null
	              || busyCancelId != null
	            }
	          >
	            {bulkExecuting ? 'Executing…' : 'Execute selected'}
	          </Button>
	          <Button
	            variant="contained"
	            size="small"
	            color="error"
	            onClick={() => {
	              void handleBulkCancel()
	            }}
	            disabled={selectionModel.length === 0 || bulkCancelling || bulkExecuting}
	          >
	            {bulkCancelling ? 'Cancelling…' : 'Cancel selected'}
	          </Button>
	        </Box>
	      </Box>

      {successMessage && !error && (
        <Typography sx={{ mt: 1 }} color="success.main">
          {successMessage}
        </Typography>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading queue...</Typography>
        </Box>
      ) : error ? (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      ) : (
        <Paper
          sx={{
            width: '100%',
            mt: 2,
            // In tabbed mode, keep the panel height stable to avoid flicker/layout jumps.
            height: embedded ? 'calc(100vh - 280px)' : undefined,
            minHeight: embedded ? 520 : undefined,
          }}
        >
          <DataGrid
            rows={orders}
            columns={columns}
            getRowId={(row) => row.id}
            {...(embedded ? {} : { autoHeight: true })}
            checkboxSelection
            rowSelectionModel={selectionModel}
            onRowSelectionModelChange={(newSelection) => {
              setSelectionModel(newSelection)
            }}
            disableRowSelectionOnClick
            density="compact"
            sx={embedded ? { height: '100%' } : undefined}
            initialState={{
              sorting: {
                sortModel: [{ field: 'created_at', sort: 'desc' }],
              },
            }}
          />
        </Paper>
      )}

      <Dialog open={editingOrder != null} onClose={closeEditDialog} fullWidth>
        <DialogTitle>Edit queue order</DialogTitle>
        <DialogContent sx={{ pt: 2 }}>
          {editingOrder && (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 2,
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  {editingOrder.symbol}
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Button
                    size="small"
                    variant={editSide === 'BUY' ? 'contained' : 'outlined'}
                    color="primary"
                    onClick={() => setEditSide('BUY')}
                  >
                    BUY
                  </Button>
                  <Button
                    size="small"
                    variant={editSide === 'SELL' ? 'contained' : 'outlined'}
                    color="error"
                    onClick={() => setEditSide('SELL')}
                  >
                    SELL
                  </Button>
                </Box>
              </Box>
              <TextField
                label="Quantity"
                type="number"
                value={editQty}
                onChange={(e) => setEditQty(e.target.value)}
                fullWidth
                size="small"
                error={
                  editSide === 'SELL' &&
                  editProductNorm === 'CNC' &&
                  holdingQty != null &&
                  !holdingsLoading &&
                  holdingsError == null &&
                  Number.isFinite(editQtyNum) &&
                  availableHoldingQty != null &&
                  editQtyNum > availableHoldingQty
                }
                helperText={(() => {
                  if (editSide !== 'SELL') return undefined
                  if (editProductNorm !== 'CNC') {
                    if (holdingQty != null && holdingQty > 0) {
                      return 'For delivery holdings exits, use CNC. MIS is intraday and may not match holdings.'
                    }
                    return undefined
                  }
                  if (holdingsLoading) return 'Loading holdings for quantity helpers…'
                  if (holdingsError) return `Holdings unavailable: ${holdingsError}`
                  if (holdingQty == null) return undefined
                  const hq = Math.floor(holdingQty)
                  const reserved = Math.floor(queuedCncSellQty)
                  const avail = availableHoldingQty ?? hq
                  if (Number.isFinite(editQtyNum) && editQtyNum > avail) {
                    return `Available CNC holdings: ${avail} (holdings ${hq} − queued CNC sells ${reserved}).`
                  }
                  return `Available CNC holdings: ${avail} (holdings ${hq} − queued CNC sells ${reserved}).`
                })()}
              />

              {editSide === 'SELL' && (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => {
                        if (holdingQty == null) return
                        setQtyFromHoldings(holdingQty)
                      }}
                      disabled={
                        editProductNorm !== 'CNC' ||
                        holdingsLoading ||
                        holdingsError != null ||
                        holdingQty == null
                      }
                    >
                      Set = holdings qty
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={() => {
                        if (availableHoldingQty == null) return
                        setQtyFromHoldings(availableHoldingQty)
                      }}
                      disabled={
                        editProductNorm !== 'CNC' ||
                        holdingsLoading ||
                        holdingsError != null ||
                        availableHoldingQty == null
                      }
                    >
                      Set = available qty
                    </Button>
                    <Button
                      size="small"
                      variant="text"
                      onClick={() => {
                        void loadHoldings(editBrokerName)
                      }}
                      disabled={holdingsLoading}
                    >
                      Refresh holdings
                    </Button>
                  </Box>

                  <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                    <TextField
                      label="% of holdings"
                      type="number"
                      value={holdingsPct}
                      onChange={(e) => setHoldingsPct(e.target.value)}
                      size="small"
                      sx={{ width: 170 }}
                      InputProps={{
                        endAdornment: <InputAdornment position="end">%</InputAdornment>,
                      }}
                      disabled={
                        editProductNorm !== 'CNC' ||
                        holdingsLoading ||
                        holdingsError != null ||
                        holdingQty == null
                      }
                    />
                    <Button
                      size="small"
                      variant="outlined"
                      onClick={applyHoldingsPctToQty}
                      disabled={
                        editProductNorm !== 'CNC' ||
                        holdingsLoading ||
                        holdingsError != null ||
                        holdingQty == null
                      }
                    >
                      Set from %
                    </Button>
                    {editProductNorm === 'MIS' && holdingQty != null && holdingQty > 0 && (
                      <Button
                        size="small"
                        variant="outlined"
                        onClick={() => {
                          setEditProduct('CNC')
                          setQtyFromHoldings(holdingQty)
                        }}
                      >
                        Switch to CNC + set qty
                      </Button>
                    )}
                  </Box>

                  {editProductNorm === 'CNC' && holdingQty != null && (
                    <Typography variant="caption" color="text.secondary">
                      Holdings-based helpers use live holdings and clamp to an integer (floor). Available qty subtracts other LIVE CNC SELL orders still in the queue.
                    </Typography>
                  )}
                </Box>
              )}
              <TextField
                label="Order type"
                select
                value={editOrderType}
                onChange={(e) =>
                  setEditOrderType(
                    (e.target.value as 'MARKET' | 'LIMIT' | 'SL' | 'SL-M') ||
                      'MARKET',
                  )
                }
                fullWidth
                size="small"
              >
                <MenuItem value="MARKET">MARKET</MenuItem>
                <MenuItem value="LIMIT">LIMIT</MenuItem>
                <MenuItem value="SL">SL (Stop-loss limit)</MenuItem>
                <MenuItem value="SL-M">SL-M (Stop-loss market)</MenuItem>
              </TextField>
              <TextField
                label="Price"
                type="number"
                value={editPrice}
                onChange={(e) => setEditPrice(e.target.value)}
                fullWidth
                size="small"
                helperText={
                  editOrderType === 'MARKET' || editOrderType === 'SL-M'
                    ? 'Leave blank for pure market orders.'
                    : 'Limit price for LIMIT / SL orders.'
                }
              />
              {(editOrderType === 'SL' || editOrderType === 'SL-M') && (
                <>
                  <Box
                    sx={{
                      display: 'flex',
                      justifyContent: 'flex-end',
                      mb: 0.5,
                      gap: 1,
                    }}
                  >
                    <Button
                      size="small"
                      variant={triggerMode === 'PRICE' ? 'contained' : 'outlined'}
                      onClick={() => setTriggerMode('PRICE')}
                    >
                      Use price
                    </Button>
                    <Button
                      size="small"
                      variant={triggerMode === 'PERCENT' ? 'contained' : 'outlined'}
                      onClick={() => setTriggerMode('PERCENT')}
                      disabled={ltp == null}
                    >
                      Use % vs LTP
                    </Button>
                  </Box>
                  <TextField
                    label="Trigger price"
                    type="number"
                    value={editTriggerPrice}
                    onChange={(e) => setEditTriggerPrice(e.target.value)}
                    fullWidth
                    size="small"
                    disabled={triggerMode === 'PERCENT'}
                  />
                  <TextField
                    label="Trigger % vs LTP (optional)"
                    type="number"
                    value={editTriggerPercent}
                    onChange={(e) => setEditTriggerPercent(e.target.value)}
                    fullWidth
                    size="small"
                    disabled={triggerMode === 'PRICE' || ltp == null}
                    helperText={
                      ltpError
                        ? ltpError
                        : 'Percentage relative to last traded price; derived automatically when using the other field.'
                    }
                  />
                </>
              )}
              <TextField
                label="Product"
                select
                value={editProduct}
                onChange={(e) => setEditProduct(e.target.value)}
                fullWidth
                size="small"
                helperText="Select MIS for intraday or CNC for delivery."
              >
                <MenuItem value="MIS">MIS (Intraday)</MenuItem>
                <MenuItem value="CNC">CNC (Delivery)</MenuItem>
              </TextField>
              <TextField
                label="Execution target"
                select
                value={editExecutionTarget}
                onChange={(e) =>
                  setEditExecutionTarget(
                    (e.target.value as ExecutionTarget) || 'LIVE',
                  )
                }
                fullWidth
                size="small"
                helperText="LIVE sends the order to the broker; PAPER routes it to the simulated engine."
              >
                <MenuItem value="LIVE">LIVE</MenuItem>
                <MenuItem value="PAPER">PAPER</MenuItem>
              </TextField>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={editGtt}
                    onChange={(e) => {
                      const checked = e.target.checked
                      setEditGtt(checked)
                      if (checked && editOrderType === 'MARKET') {
                        setEditOrderType('LIMIT')
                      }
                    }}
                    size="small"
                    disabled={(() => {
                      const brokerName =
                        editingOrder?.broker_name ?? selectedBroker ?? 'zerodha'
                      const caps = getCaps(brokerName)
                      const supported = caps
                        ? caps.supports_gtt || caps.supports_conditional_orders
                        : brokerName === 'zerodha'
                      return !supported
                    })()}
                  />
                }
                label={
                  (() => {
                    const brokerName =
                      editingOrder?.broker_name ?? selectedBroker ?? 'zerodha'
                    const caps = getCaps(brokerName)
                    if (caps?.supports_gtt || brokerName === 'zerodha') {
                      return 'Place as GTT (broker-managed)'
                    }
                    return 'Place as conditional order (SigmaTrader-managed)'
                  })()
                }
              />
              <Box
                sx={{
                  mt: 1,
                  p: 1,
                  borderRadius: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 1,
                }}
              >
                <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    Risk exits (SigmaTrader-managed)
                  </Typography>
                  <Button
                    size="small"
                    variant="text"
                    color="warning"
                    onClick={() => {
                      const ok = window.confirm(
                        'Clear all SigmaTrader-managed risk exits for this order?',
                      )
                      if (!ok) return
                      setRiskSlEnabled(false)
                      setRiskTrailEnabled(false)
                      setRiskActivationEnabled(false)
                      setRiskSlValue('')
                      setRiskTrailValue('')
                      setRiskActivationValue('')
                      setRiskCooldownMs('')
                    }}
                    disabled={
                      !riskSlEnabled &&
                      !riskTrailEnabled &&
                      !riskActivationEnabled &&
                      riskCooldownMs.trim() === ''
                    }
                  >
                    Clear exits
                  </Button>
                </Box>

                {(() => {
                  const anyEnabled =
                    riskSlEnabled || riskTrailEnabled || riskActivationEnabled
                  const spec: RiskSpec | null = anyEnabled
                    ? {
                        stop_loss: {
                          enabled: riskSlEnabled,
                          mode: riskSlMode,
                          value: Number(riskSlValue || 0),
                          atr_period: Number(riskSlAtrPeriod || 14) || 14,
                          atr_tf: riskSlAtrTf,
                        },
                        trailing_stop: {
                          enabled: riskTrailEnabled,
                          mode: riskTrailMode,
                          value: Number(riskTrailValue || 0),
                          atr_period: Number(riskTrailAtrPeriod || 14) || 14,
                          atr_tf: riskTrailAtrTf,
                        },
                        trailing_activation: {
                          enabled: riskActivationEnabled,
                          mode: riskActivationMode,
                          value: Number(riskActivationValue || 0),
                          atr_period:
                            Number(riskActivationAtrPeriod || 14) || 14,
                          atr_tf: riskActivationAtrTf,
                        },
                        exit_order_type: 'MARKET',
                        cooldown_ms:
                          riskCooldownMs.trim() === ''
                            ? null
                            : Number(riskCooldownMs),
                      }
                    : null
                  const summary = riskSummary(spec)
                  if (summary) {
                    return (
                      <Typography variant="caption" color="text.secondary">
                        {summary}
                      </Typography>
                    )
                  }
                  return (
                    <Typography variant="caption" color="warning.main">
                      No custom exits set. This order may rely on risk profile defaults (if enabled) or have no SigmaTrader-managed exits.
                    </Typography>
                  )
                })()}

                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={riskSlEnabled}
                      onChange={(e) => {
                        const checked = e.target.checked
                        setRiskSlEnabled(checked)
                        if (!checked) {
                          setRiskTrailEnabled(false)
                          setRiskActivationEnabled(false)
                          setRiskCooldownMs('')
                        }
                      }}
                    />
                  }
                  label="Stop-loss"
                />
                {riskSlEnabled && (
                  <>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <TextField
                        label="SL mode"
                        select
                        value={riskSlMode}
                        onChange={(e) =>
                          setRiskSlMode(e.target.value as DistanceMode)
                        }
                        size="small"
                        sx={{ flex: 1 }}
                      >
                        <MenuItem value="PCT">%</MenuItem>
                        <MenuItem value="ABS">₹</MenuItem>
                        <MenuItem value="ATR">ATR×</MenuItem>
                      </TextField>
                      <TextField
                        label="SL value"
                        type="number"
                        value={riskSlValue}
                        onChange={(e) => setRiskSlValue(e.target.value)}
                        size="small"
                        sx={{ flex: 1 }}
                      />
                    </Box>
                    {riskSlMode === 'ATR' && (
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <TextField
                          label="ATR period"
                          type="number"
                          value={riskSlAtrPeriod}
                          onChange={(e) => setRiskSlAtrPeriod(e.target.value)}
                          size="small"
                          sx={{ flex: 1 }}
                        />
                        <TextField
                          label="ATR tf"
                          select
                          value={riskSlAtrTf}
                          onChange={(e) => setRiskSlAtrTf(e.target.value)}
                          size="small"
                          sx={{ flex: 1 }}
                        >
                          <MenuItem value="1m">1m</MenuItem>
                          <MenuItem value="5m">5m</MenuItem>
                          <MenuItem value="15m">15m</MenuItem>
                          <MenuItem value="30m">30m</MenuItem>
                          <MenuItem value="1h">1h</MenuItem>
                          <MenuItem value="1d">1d</MenuItem>
                        </TextField>
                      </Box>
                    )}
                  </>
                )}

                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={riskTrailEnabled}
                      onChange={(e) => {
                        const checked = e.target.checked
                        setRiskTrailEnabled(checked)
                        if (checked) {
                          setRiskSlEnabled(true)
                        } else {
                          setRiskActivationEnabled(false)
                        }
                      }}
                    />
                  }
                  label="Trailing stop-loss"
                />
                {riskTrailEnabled && (
                  <>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <TextField
                        label="Trail mode"
                        select
                        value={riskTrailMode}
                        onChange={(e) =>
                          setRiskTrailMode(e.target.value as DistanceMode)
                        }
                        size="small"
                        sx={{ flex: 1 }}
                      >
                        <MenuItem value="PCT">%</MenuItem>
                        <MenuItem value="ABS">₹</MenuItem>
                        <MenuItem value="ATR">ATR×</MenuItem>
                      </TextField>
                      <TextField
                        label="Trail value"
                        type="number"
                        value={riskTrailValue}
                        onChange={(e) => setRiskTrailValue(e.target.value)}
                        size="small"
                        sx={{ flex: 1 }}
                      />
                    </Box>
                    {riskTrailMode === 'ATR' && (
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <TextField
                          label="ATR period"
                          type="number"
                          value={riskTrailAtrPeriod}
                          onChange={(e) => setRiskTrailAtrPeriod(e.target.value)}
                          size="small"
                          sx={{ flex: 1 }}
                        />
                        <TextField
                          label="ATR tf"
                          select
                          value={riskTrailAtrTf}
                          onChange={(e) => setRiskTrailAtrTf(e.target.value)}
                          size="small"
                          sx={{ flex: 1 }}
                        >
                          <MenuItem value="1m">1m</MenuItem>
                          <MenuItem value="5m">5m</MenuItem>
                          <MenuItem value="15m">15m</MenuItem>
                          <MenuItem value="30m">30m</MenuItem>
                          <MenuItem value="1h">1h</MenuItem>
                          <MenuItem value="1d">1d</MenuItem>
                        </TextField>
                      </Box>
                    )}
                  </>
                )}

                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={riskActivationEnabled}
                      onChange={(e) => {
                        const checked = e.target.checked
                        setRiskActivationEnabled(checked)
                        if (checked) {
                          setRiskSlEnabled(true)
                          setRiskTrailEnabled(true)
                        }
                      }}
                    />
                  }
                  label="Trailing profit activation"
                />
                {riskActivationEnabled && (
                  <>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <TextField
                        label="Activation mode"
                        select
                        value={riskActivationMode}
                        onChange={(e) =>
                          setRiskActivationMode(e.target.value as DistanceMode)
                        }
                        size="small"
                        sx={{ flex: 1 }}
                      >
                        <MenuItem value="PCT">%</MenuItem>
                        <MenuItem value="ABS">₹</MenuItem>
                        <MenuItem value="ATR">ATR×</MenuItem>
                      </TextField>
                      <TextField
                        label="Activation value"
                        type="number"
                        value={riskActivationValue}
                        onChange={(e) =>
                          setRiskActivationValue(e.target.value)
                        }
                        size="small"
                        sx={{ flex: 1 }}
                      />
                    </Box>
                    {riskActivationMode === 'ATR' && (
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <TextField
                          label="ATR period"
                          type="number"
                          value={riskActivationAtrPeriod}
                          onChange={(e) =>
                            setRiskActivationAtrPeriod(e.target.value)
                          }
                          size="small"
                          sx={{ flex: 1 }}
                        />
                        <TextField
                          label="ATR tf"
                          select
                          value={riskActivationAtrTf}
                          onChange={(e) => setRiskActivationAtrTf(e.target.value)}
                          size="small"
                          sx={{ flex: 1 }}
                        >
                          <MenuItem value="1m">1m</MenuItem>
                          <MenuItem value="5m">5m</MenuItem>
                          <MenuItem value="15m">15m</MenuItem>
                          <MenuItem value="30m">30m</MenuItem>
                          <MenuItem value="1h">1h</MenuItem>
                          <MenuItem value="1d">1d</MenuItem>
                        </TextField>
                      </Box>
                    )}
                  </>
                )}

                <TextField
                  label="Cooldown ms (optional)"
                  type="number"
                  value={riskCooldownMs}
                  onChange={(e) => setRiskCooldownMs(e.target.value)}
                  size="small"
                  fullWidth
                  disabled={
                    !riskSlEnabled && !riskTrailEnabled && !riskActivationEnabled
                  }
                  helperText="Applies only when exits are enabled."
                />
              </Box>
              <Box
                sx={{
                  mt: 1,
                  p: 1.5,
                  borderRadius: 1,
                  bgcolor: 'action.hover',
                }}
              >
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    mb: 1,
                    gap: 1,
                  }}
                >
                  <Typography variant="subtitle2">Funds &amp; charges</Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      void refreshFundsPreview()
                    }}
                    disabled={(() => {
                      if (fundsLoading) return true
                      const brokerName =
                        editingOrder?.broker_name ?? selectedBroker ?? 'zerodha'
                      const caps = getCaps(brokerName)
                      return caps
                        ? !caps.supports_margin_preview || !caps.supports_order_preview
                        : brokerName !== 'zerodha'
                    })()}
                  >
                    {fundsLoading ? 'Checking…' : 'Recalculate'}
                  </Button>
                </Box>
                {fundsError ? (
                  <Typography variant="body2" color="error">
                    {fundsError}
                  </Typography>
                ) : fundsAvailable != null && fundsRequired != null ? (
                  <Typography variant="body2">
                    Required:{' '}
                    {fundsCurrency ?? '₹'} {fundsRequired.toFixed(2)} (incl. charges)
                    <br />
                    Available:{' '}
                    {fundsCurrency ?? '₹'} {fundsAvailable.toFixed(2)}
                  </Typography>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Click Recalculate to see required vs available funds and
                    charges for this order.
                  </Typography>
                )}
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeEditDialog} disabled={savingEdit}>
            Cancel
          </Button>
          <Button
            onClick={handleSaveEdit}
            variant="contained"
            disabled={savingEdit}
          >
            {savingEdit ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export function QueuePage() {
  return <WaitingQueuePanel />
}
