import Box from '@mui/material/Box'
import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import FormControlLabel from '@mui/material/FormControlLabel'
import Checkbox from '@mui/material/Checkbox'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import MenuItem from '@mui/material/MenuItem'
import Typography from '@mui/material/Typography'
import Tooltip from '@mui/material/Tooltip'
import { useEffect, useMemo, useRef, useState } from 'react'
import { DataGrid, GridToolbar, type GridCellParams, type GridColDef } from '@mui/x-data-grid'
import ClearIcon from '@mui/icons-material/Clear'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { useNavigate } from 'react-router-dom'

import {
  PriceChart,
  type PriceCandle,
  type PriceOverlay,
  type PriceSignalMarker,
} from '../components/PriceChart'
import {
  fetchDailyPositions,
  syncPositions,
  type PositionSnapshot,
} from '../services/positions'
import { fetchBrokers, type BrokerInfo } from '../services/brokers'
import { fetchOrdersInsights, type OrdersInsights } from '../services/orders'
import {
  clearZerodhaPostbackFailures,
  fetchZerodhaPostbackEvents,
  fetchZerodhaStatus,
  type ZerodhaPostbackEvent,
  type ZerodhaStatus,
} from '../services/zerodha'
import { fetchCoverageUnmanagedCount } from '../services/aiTradingManager'
import { useTimeSettings } from '../timeSettingsContext'
import { formatInDisplayTimeZone } from '../utils/datetime'

const formatDateLocal = (d: Date): string => {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const defaultDateRange = (): { from: string; to: string } => {
  const today = new Date()
  return {
    from: formatDateLocal(today),
    to: formatDateLocal(today),
  }
}

const formatInr = (n: number | null | undefined, opts?: { fractionDigits?: number }) => {
  if (n == null || !Number.isFinite(Number(n))) return '—'
  const fractionDigits = opts?.fractionDigits ?? 0
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: fractionDigits,
  }).format(Number(n))
}

const asRecord = (v: unknown): Record<string, unknown> | null => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  return v as Record<string, unknown>
}

function PnlChip({ value }: { value: number }) {
  const color = value > 0 ? 'success' : value < 0 ? 'error' : 'default'
  return <Chip size="small" label={formatInr(value, { fractionDigits: 0 })} color={color as any} />
}

function HeaderWithTooltip({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <Stack direction="row" spacing={0.5} alignItems="center">
      <span>{label}</span>
      <Tooltip title={tooltip} arrow>
        <span>
          <InfoOutlinedIcon fontSize="small" sx={{ opacity: 0.7 }} />
        </span>
      </Tooltip>
    </Stack>
  )
}

export function PositionsPage() {
  const { displayTimeZone } = useTimeSettings()
  const navigate = useNavigate()
  const defaults = defaultDateRange()
  type PositionsTab = 'snapshots' | 'analysis' | 'transactions'
  const [activeTab, setActiveTab] = useState<PositionsTab>('snapshots')
  const [positions, setPositions] = useState<PositionSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [polling, setPolling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [coverageCount, setCoverageCount] = useState<{ unmanaged_open: number; open_total: number } | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [live, setLive] = useState(true)
  const [orderInsights, setOrderInsights] = useState<OrdersInsights | null>(null)
  const [orderInsightsLoading, setOrderInsightsLoading] = useState(false)
  const [orderInsightsError, setOrderInsightsError] = useState<string | null>(null)
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [selectedBroker, setSelectedBroker] = useState<string>('zerodha')
  const loadSeqRef = useRef(0)
  const positionsKeyRef = useRef<string>('')
  const [lastLiveUpdateAt, setLastLiveUpdateAt] = useState<string | null>(null)
  const symbolApplyTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    let active = true
    void (async () => {
      try {
        const c = await fetchCoverageUnmanagedCount({ account_id: 'default' })
        if (!active) return
        setCoverageCount({ unmanaged_open: c.unmanaged_open, open_total: c.open_total })
      } catch {
        if (!active) return
        setCoverageCount(null)
      }
    })()
    return () => {
      active = false
    }
  }, [])
  const symbolAutoApplyMountedRef = useRef(false)

  const [startDate, setStartDate] = useState<string>(defaults.from)
  const [endDate, setEndDate] = useState<string>(defaults.to)
  const [symbolQuery, setSymbolQuery] = useState<string>('')
  const [includeZero, setIncludeZero] = useState(true)
  const [startingCash, setStartingCash] = useState(0)
  const [analysisSelectedDate, setAnalysisSelectedDate] = useState<string | null>(null)

  const [zerodhaStatus, setZerodhaStatus] = useState<ZerodhaStatus | null>(null)
  const [postbackEvents, setPostbackEvents] = useState<ZerodhaPostbackEvent[]>([])
  const [postbackLoading, setPostbackLoading] = useState(false)
  const [postbackError, setPostbackError] = useState<string | null>(null)
  const [postbackIncludeOk, setPostbackIncludeOk] = useState(false)
  const [postbackSelectedId, setPostbackSelectedId] = useState<number | null>(null)
  const [postbackClearing, setPostbackClearing] = useState(false)

  const _positionsKey = (rows: PositionSnapshot[]) => {
    if (!rows.length) return '0:0'
    let maxTs = 0
    for (const r of rows) {
      const ts = Date.parse(r.captured_at)
      if (Number.isFinite(ts)) maxTs = Math.max(maxTs, ts)
    }
    return `${rows.length}:${maxTs}`
  }

  const loadSnapshots = async (opts?: {
    preferLatest?: boolean
    includeZeroOverride?: boolean
    silent?: boolean
    startDateOverride?: string
    endDateOverride?: string
  }) => {
    const seq = (loadSeqRef.current += 1)
    try {
      if (opts?.silent) setPolling(true)
      else setLoading(true)
      const startDateParam = opts?.startDateOverride ?? startDate
      const endDateParam = opts?.endDateOverride ?? endDate
      const params =
        opts?.preferLatest && !startDateParam && !endDateParam && !symbolQuery
          ? { broker_name: selectedBroker }
          : {
              broker_name: selectedBroker,
              start_date: startDateParam || undefined,
              end_date: endDateParam || undefined,
              symbol: symbolQuery || undefined,
              include_zero: opts?.includeZeroOverride ?? includeZero,
            }
      const data = await fetchDailyPositions(params)
      if (seq !== loadSeqRef.current) return
      const nextKey = _positionsKey(data)
      if (nextKey !== positionsKeyRef.current) {
        positionsKeyRef.current = nextKey
        setPositions(data)
        setLastLiveUpdateAt(new Date().toISOString())
      }
      if (!opts?.silent) setError(null)
    } catch (err) {
      if (seq !== loadSeqRef.current) return
      // Silent polling should not disrupt the table UX. The manual refresh button
      // remains the source of truth for broker-side changes.
      if (!opts?.silent) {
        setError(err instanceof Error ? err.message : 'Failed to load positions')
      }
    } finally {
      if (seq === loadSeqRef.current) {
        if (opts?.silent) setPolling(false)
        else setLoading(false)
      }
    }
  }

  const loadOrderInsights = async (opts?: { startDateOverride?: string; endDateOverride?: string }) => {
    setOrderInsightsLoading(true)
    setOrderInsightsError(null)
    try {
      const startDateParam = opts?.startDateOverride ?? startDate
      const endDateParam = opts?.endDateOverride ?? endDate
      const data = await fetchOrdersInsights({
        brokerName: selectedBroker,
        startDate: startDateParam || undefined,
        endDate: endDateParam || undefined,
        includeSimulated: false,
        topN: 20,
      })
      setOrderInsights(data)
    } catch (err) {
      setOrderInsightsError(err instanceof Error ? err.message : 'Failed to load order insights')
    } finally {
      setOrderInsightsLoading(false)
    }
  }

  const loadZerodhaPostbacks = async (opts?: { silent?: boolean }) => {
    if (selectedBroker !== 'zerodha') return
    if (!opts?.silent) setPostbackLoading(true)
    setPostbackError(null)
    try {
      const [st, evs] = await Promise.all([
        fetchZerodhaStatus(),
        fetchZerodhaPostbackEvents({
          limit: 100,
          include_ok: postbackIncludeOk,
          include_error: true,
          include_noise: true,
          include_legacy: true,
        }),
      ])
      setZerodhaStatus(st)
      setPostbackEvents(evs)
      setPostbackSelectedId((prev) => (prev != null && evs.some((e) => e.id === prev) ? prev : null))
    } catch (err) {
      setPostbackError(err instanceof Error ? err.message : 'Failed to load Zerodha postback events')
    } finally {
      if (!opts?.silent) setPostbackLoading(false)
    }
  }

  const handleClearPostbackFailures = async () => {
    if (selectedBroker !== 'zerodha') return
    setPostbackClearing(true)
    try {
      await clearZerodhaPostbackFailures({ include_legacy: true })
      await loadZerodhaPostbacks()
    } catch (err) {
      setPostbackError(err instanceof Error ? err.message : 'Failed to clear postback failures')
    } finally {
      setPostbackClearing(false)
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        const list = await fetchBrokers()
        setBrokers(list)
        if (list.length > 0 && !list.some((b) => b.name === selectedBroker)) {
          setSelectedBroker(list[0].name)
        }
      } catch {
        // Ignore; page can still operate with defaults.
      }
    })()
    void loadSnapshots({ preferLatest: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    // When switching brokers, immediately clear the previous broker's rows so
    // the grid doesn't look "stuck" on the old broker while the request runs.
    setPositions([])
    positionsKeyRef.current = ''
    setError(null)
    setOrderInsights(null)
    setOrderInsightsError(null)
    setZerodhaStatus(null)
    setPostbackEvents([])
    setPostbackError(null)
    setPostbackSelectedId(null)
    if (activeTab === 'snapshots') void loadSnapshots()
    else void loadSnapshots({ includeZeroOverride: true })
    if (selectedBroker === 'zerodha') void loadZerodhaPostbacks()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBroker])

  useEffect(() => {
    if (!live) return
    // Live mode only re-fetches cached rows from SigmaTrader DB; it does not
    // hit the broker. Broker changes still require "Refresh from <broker>".
	    const id = window.setInterval(() => {
	      if (activeTab === 'snapshots') void loadSnapshots({ silent: true })
	      else if (activeTab === 'transactions') {
	        void loadSnapshots({ includeZeroOverride: true, silent: true })
	      } else if (activeTab === 'analysis') void loadSnapshots({ includeZeroOverride: true, silent: true })
	    }, 4000)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, activeTab, selectedBroker, startDate, endDate, symbolQuery, includeZero, startingCash])

  useEffect(() => {
    if (selectedBroker !== 'zerodha') return
    const id = window.setInterval(() => {
      void loadZerodhaPostbacks({ silent: true })
    }, 10000)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedBroker, postbackIncludeOk])

  useEffect(() => {
    if (selectedBroker !== 'zerodha') return
    void loadZerodhaPostbacks({ silent: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postbackIncludeOk])

  useEffect(() => {
    if (!symbolAutoApplyMountedRef.current) {
      symbolAutoApplyMountedRef.current = true
      return
    }

    if (symbolApplyTimeoutRef.current != null) {
      window.clearTimeout(symbolApplyTimeoutRef.current)
      symbolApplyTimeoutRef.current = null
    }

    // Symbol filter should apply as-you-type (debounced) to avoid extra clicks.
    // Other filters still use the "Apply" button.
    symbolApplyTimeoutRef.current = window.setTimeout(() => {
      symbolApplyTimeoutRef.current = null
      if (activeTab === 'snapshots') void loadSnapshots()
      if (activeTab === 'transactions') void loadSnapshots({ includeZeroOverride: true })
    }, 350)

    return () => {
      if (symbolApplyTimeoutRef.current != null) {
        window.clearTimeout(symbolApplyTimeoutRef.current)
        symbolApplyTimeoutRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbolQuery])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await syncPositions(selectedBroker)
      if (activeTab === 'snapshots') {
        await loadSnapshots({ preferLatest: true })
      } else if (activeTab === 'transactions') {
        await loadSnapshots({ preferLatest: true, includeZeroOverride: true })
      } else {
        await loadSnapshots({ preferLatest: true, includeZeroOverride: true })
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : `Failed to sync positions from ${selectedBroker}`,
      )
    } finally {
      setRefreshing(false)
    }
  }

  const handleApply = async (opts?: { startDate?: string; endDate?: string }) => {
    if (symbolApplyTimeoutRef.current != null) {
      window.clearTimeout(symbolApplyTimeoutRef.current)
      symbolApplyTimeoutRef.current = null
    }
    if (activeTab === 'snapshots') {
      await loadSnapshots({ startDateOverride: opts?.startDate, endDateOverride: opts?.endDate })
    } else if (activeTab === 'transactions') {
      await loadSnapshots({
        includeZeroOverride: true,
        startDateOverride: opts?.startDate,
        endDateOverride: opts?.endDate,
      })
    } else {
      await loadSnapshots({
        includeZeroOverride: true,
        startDateOverride: opts?.startDate,
        endDateOverride: opts?.endDate,
      })
      if (orderInsights != null) {
        await loadOrderInsights({ startDateOverride: opts?.startDate, endDateOverride: opts?.endDate })
      }
    }
  }

  const applyDatePreset = (days: 1 | 7 | 15) => {
    const today = new Date()
    const to = formatDateLocal(today)
    const fromDate = new Date(today)
    fromDate.setDate(today.getDate() - (days - 1))
    const from = formatDateLocal(fromDate)
    setStartDate(from)
    setEndDate(to)
    void handleApply({ startDate: from, endDate: to })
  }

  type TransactionRow = {
    id: string
    as_of_date: string
    symbol: string
    exchange: string
    product: string
    side: 'BUY' | 'SELL'
    qty: number
    avg_price: number
    notional: number
  }

  type DailyCashRow = {
    id: string
    as_of_date: string
    turnover_buy: number
    turnover_sell: number
    net_cashflow: number
    cash_balance: number
    holdings_value: number
    net_liq: number
    tx_count: number
  }

  const transactions = useMemo((): TransactionRow[] => {
    if (!positions || positions.length === 0) return []

    const txs: TransactionRow[] = []
    for (const r of positions) {
      const date = String(r.as_of_date || '').slice(0, 10)
      if (!date) continue

      const exchange = String(r.exchange || 'NSE')
      const symbol = String(r.symbol || '').toUpperCase()
      const product = String(r.product || '')

      const buyQty = Number(r.day_buy_qty ?? r.buy_qty ?? 0) || 0
      const sellQty = Number(r.day_sell_qty ?? r.sell_qty ?? 0) || 0
      const buyPx =
        Number(r.day_buy_avg_price ?? r.buy_avg_price ?? r.avg_buy_price ?? 0) || 0
      const sellPx =
        Number(r.day_sell_avg_price ?? r.sell_avg_price ?? r.avg_sell_price ?? 0) || 0

      if (buyQty > 0 && buyPx > 0) {
        txs.push({
          id: `${date}:${exchange}:${symbol}:${product}:BUY`,
          as_of_date: date,
          symbol,
          exchange,
          product,
          side: 'BUY',
          qty: buyQty,
          avg_price: buyPx,
          notional: buyQty * buyPx,
        })
      }
      if (sellQty > 0 && sellPx > 0) {
        txs.push({
          id: `${date}:${exchange}:${symbol}:${product}:SELL`,
          as_of_date: date,
          symbol,
          exchange,
          product,
          side: 'SELL',
          qty: sellQty,
          avg_price: sellPx,
          notional: sellQty * sellPx,
        })
      }
    }

    return txs.sort((a, b) =>
      a.as_of_date === b.as_of_date
        ? a.symbol.localeCompare(b.symbol)
        : a.as_of_date.localeCompare(b.as_of_date),
    )
  }, [positions])

  type DailyRealityRow = {
    id: string
    as_of_date: string
    captured_at: string | null
    realised_pnl: number
    unrealised_pnl: number
    net_pnl: number
    open_value: number
    turnover_buy: number
    turnover_sell: number
    traded_symbols: number
    open_positions: number
  }

  const deriveSnapshotParts = (r: PositionSnapshot) => {
    const product = String(r.product ?? '').toUpperCase()
    const netQty = Number(r.qty ?? 0) || 0
    const openQty = product === 'CNC' || product === 'DELIVERY' ? Math.max(0, netQty) : netQty
    const isOpen = openQty !== 0

    const buyQty = Number(r.day_buy_qty ?? r.buy_qty ?? 0) || 0
    const sellQty = Number(r.day_sell_qty ?? r.sell_qty ?? 0) || 0
    const hasTrades = buyQty > 0 || sellQty > 0

    const netPnl = Number(r.pnl ?? 0) || 0
    const realisedPnl = !isOpen && (hasTrades || netQty !== 0) ? netPnl : 0
    const unrealisedPnl = isOpen ? netPnl : 0

    const px =
      Number(r.ltp ?? r.last_price ?? r.close_price ?? r.avg_price ?? 0) || 0
    const openValue = px > 0 ? Math.abs(openQty) * px : 0

    return {
      product,
      netQty,
      openQty,
      buyQty,
      sellQty,
      hasTrades,
      netPnl,
      realisedPnl,
      unrealisedPnl,
      openValue,
    }
  }

  const dailyReality = useMemo((): DailyRealityRow[] => {
    if (!positions || positions.length === 0) return []

    const byDate = new Map<
      string,
      {
        realised: number
        unrealised: number
        net: number
        openValue: number
        turnoverBuy: number
        turnoverSell: number
        tradedKeys: Set<string>
        openKeys: Set<string>
        capturedAtMax: number
      }
    >()

    for (const r of positions) {
      const date = String(r.as_of_date || '').slice(0, 10)
      if (!date) continue

      const key = `${String(r.symbol || '').toUpperCase()}:${String(r.exchange || '').toUpperCase()}:${String(
        r.product || '',
      ).toUpperCase()}`

      const cur =
        byDate.get(date) ?? {
          realised: 0,
          unrealised: 0,
          net: 0,
          openValue: 0,
          turnoverBuy: 0,
          turnoverSell: 0,
          tradedKeys: new Set<string>(),
          openKeys: new Set<string>(),
          capturedAtMax: 0,
        }

      const parts = deriveSnapshotParts(r)
      cur.realised += parts.realisedPnl
      cur.unrealised += parts.unrealisedPnl
      cur.net += parts.netPnl
      cur.openValue += parts.openValue

      const buyQty = parts.buyQty
      const sellQty = parts.sellQty
      const buyPx = Number(r.day_buy_avg_price ?? r.buy_avg_price ?? r.avg_buy_price ?? 0) || 0
      const sellPx = Number(r.day_sell_avg_price ?? r.sell_avg_price ?? r.avg_sell_price ?? 0) || 0
      if (buyQty > 0 && buyPx > 0) {
        cur.turnoverBuy += buyQty * buyPx
        cur.tradedKeys.add(key)
      }
      if (sellQty > 0 && sellPx > 0) {
        cur.turnoverSell += sellQty * sellPx
        cur.tradedKeys.add(key)
      }

      if (parts.openQty !== 0) cur.openKeys.add(key)

      const cap = Date.parse(String(r.captured_at || ''))
      if (Number.isFinite(cap)) cur.capturedAtMax = Math.max(cur.capturedAtMax, cap)

      byDate.set(date, cur)
    }

    return Array.from(byDate.entries())
      .map(([d, v]) => ({
        id: d,
        as_of_date: d,
        captured_at: v.capturedAtMax ? new Date(v.capturedAtMax).toISOString() : null,
        realised_pnl: v.realised,
        unrealised_pnl: v.unrealised,
        net_pnl: v.net,
        open_value: v.openValue,
        turnover_buy: v.turnoverBuy,
        turnover_sell: v.turnoverSell,
        traded_symbols: v.tradedKeys.size,
        open_positions: v.openKeys.size,
      }))
      .sort((a, b) => b.as_of_date.localeCompare(a.as_of_date))
  }, [positions])

  const realityTotals = useMemo(() => {
    let realised = 0
    let unrealised = 0
    let net = 0
    let openValue = 0
    let buy = 0
    let sell = 0
    for (const d of dailyReality) {
      realised += Number(d.realised_pnl) || 0
      unrealised += Number(d.unrealised_pnl) || 0
      net += Number(d.net_pnl) || 0
      openValue += Number(d.open_value) || 0
      buy += Number(d.turnover_buy) || 0
      sell += Number(d.turnover_sell) || 0
    }
    return { realised, unrealised, net, openValue, buy, sell, total: buy + sell }
  }, [dailyReality])

  useEffect(() => {
    if (activeTab !== 'analysis') return
    if (!dailyReality.length) return
    if (analysisSelectedDate && dailyReality.some((d) => d.as_of_date === analysisSelectedDate)) return
    setAnalysisSelectedDate(dailyReality[0].as_of_date)
  }, [activeTab, dailyReality, analysisSelectedDate])

  const dailyCash = useMemo((): DailyCashRow[] => {
    if (!positions || positions.length === 0) return []

    const byDate = new Map<
      string,
      {
        turnoverBuy: number
        turnoverSell: number
        holdingsValue: number
        txCount: number
      }
    >()

    for (const r of positions) {
      const date = String(r.as_of_date || '').slice(0, 10)
      if (!date) continue
      const cur = byDate.get(date) || {
        turnoverBuy: 0,
        turnoverSell: 0,
        holdingsValue: 0,
        txCount: 0,
      }

      const buyQty = Number(r.day_buy_qty ?? r.buy_qty ?? 0) || 0
      const sellQty = Number(r.day_sell_qty ?? r.sell_qty ?? 0) || 0
      const buyPx =
        Number(r.day_buy_avg_price ?? r.buy_avg_price ?? r.avg_buy_price ?? 0) || 0
      const sellPx =
        Number(r.day_sell_avg_price ?? r.sell_avg_price ?? r.avg_sell_price ?? 0) || 0
      if (buyQty > 0 && buyPx > 0) {
        cur.turnoverBuy += buyQty * buyPx
        cur.txCount += 1
      }
      if (sellQty > 0 && sellPx > 0) {
        cur.turnoverSell += sellQty * sellPx
        cur.txCount += 1
      }

      let value = Number(r.value ?? NaN)
      if (!Number.isFinite(value) || value === 0) {
        const qty = Number(r.qty ?? 0) || 0
        const px =
          Number(r.ltp ?? r.last_price ?? r.close_price ?? r.avg_price ?? 0) || 0
        value = qty * px
      }
      if (Number.isFinite(value)) cur.holdingsValue += value

      byDate.set(date, cur)
    }

    const dates = Array.from(byDate.keys()).sort((a, b) => a.localeCompare(b))
    let cash = Number(startingCash) || 0
    const out: DailyCashRow[] = []
    for (const date of dates) {
      const row = byDate.get(date)!
      const net = row.turnoverSell - row.turnoverBuy
      cash += net
      const holdings = row.holdingsValue
      out.push({
        id: date,
        as_of_date: date,
        turnover_buy: row.turnoverBuy,
        turnover_sell: row.turnoverSell,
        net_cashflow: net,
        cash_balance: cash,
        holdings_value: holdings,
        net_liq: cash + holdings,
        tx_count: row.txCount,
      })
    }
    return out
  }, [positions, startingCash])

  const mkLineCandles = useMemo(
    () =>
      (rows: Array<{ as_of_date: string; value: number }>): PriceCandle[] =>
        rows
          .filter((r) => r.as_of_date && Number.isFinite(r.value))
          .map((r) => ({
            ts: r.as_of_date,
            open: r.value,
            high: r.value,
            low: r.value,
            close: r.value,
            volume: 0,
          })),
    [],
  )

  const txMarkers = useMemo((): PriceSignalMarker[] => {
    return transactions.map((t) => ({
      ts: t.as_of_date,
      kind: t.side === 'BUY' ? 'CROSSOVER' : 'CROSSUNDER',
      text: `${t.side === 'BUY' ? 'B' : 'S'} ${t.symbol}`,
    }))
  }, [transactions])

  const holdingsCandles = useMemo(
    () =>
      mkLineCandles(
        dailyCash.map((d) => ({ as_of_date: d.as_of_date, value: d.holdings_value })),
      ),
    [dailyCash, mkLineCandles],
  )
  const cashCandles = useMemo(
    () =>
      mkLineCandles(
        dailyCash.map((d) => ({ as_of_date: d.as_of_date, value: d.cash_balance })),
      ),
    [dailyCash, mkLineCandles],
  )
  const fundsOverlays = useMemo((): PriceOverlay[] => {
    const holdingsPoints = dailyCash.map((d) => ({ ts: d.as_of_date, value: d.holdings_value }))
    const netLiqPoints = dailyCash.map((d) => ({ ts: d.as_of_date, value: d.net_liq }))
    return [
      { name: 'Holdings value', points: holdingsPoints },
      { name: 'Net liquidation', points: netLiqPoints },
    ]
  }, [dailyCash])

  const dailyRealityAsc = useMemo(
    () => [...dailyReality].sort((a, b) => a.as_of_date.localeCompare(b.as_of_date)),
    [dailyReality],
  )

  const netPnlCandles = useMemo(
    () => mkLineCandles(dailyRealityAsc.map((d) => ({ as_of_date: d.as_of_date, value: d.net_pnl }))),
    [dailyRealityAsc, mkLineCandles],
  )

  const pnlOverlays = useMemo((): PriceOverlay[] => {
    const realisedPoints = dailyRealityAsc.map((d) => ({ ts: d.as_of_date, value: d.realised_pnl }))
    const unrealisedPoints = dailyRealityAsc.map((d) => ({ ts: d.as_of_date, value: d.unrealised_pnl }))
    return [
      { name: 'Realised P&L', points: realisedPoints },
      { name: 'Unrealised P&L', points: unrealisedPoints },
    ]
  }, [dailyRealityAsc])

  const dailyRealityColumns: GridColDef[] = [
    { field: 'as_of_date', headerName: 'Date', width: 110 },
    {
      field: 'captured_at',
      headerName: 'Captured',
      width: 180,
      valueFormatter: (v) => (v ? formatInDisplayTimeZone(String(v), displayTimeZone) : ''),
    },
    {
      field: 'realised_pnl',
      headerName: 'Realised P&L',
      width: 130,
      type: 'number',
      renderCell: (params) => <PnlChip value={Number(params.value || 0)} />,
    },
    {
      field: 'unrealised_pnl',
      headerName: 'Unrealised',
      width: 120,
      type: 'number',
      renderCell: (params) => <PnlChip value={Number(params.value || 0)} />,
    },
    {
      field: 'net_pnl',
      headerName: 'Net P&L',
      width: 120,
      type: 'number',
      renderCell: (params) => <PnlChip value={Number(params.value || 0)} />,
    },
    {
      field: 'open_value',
      headerName: 'Open value',
      width: 130,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
    {
      field: 'turnover_buy',
      headerName: 'Buy turnover',
      width: 130,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
    {
      field: 'turnover_sell',
      headerName: 'Sell turnover',
      width: 130,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
    {
      field: 'traded_symbols',
      headerName: '# Traded',
      width: 95,
      type: 'number',
    },
    {
      field: 'open_positions',
      headerName: '# Open pos',
      width: 100,
      type: 'number',
    },
  ]

  const dayDrillRows = useMemo(() => {
    if (!analysisSelectedDate) return []
    return positions
      .filter((r) => String(r.as_of_date || '').slice(0, 10) === analysisSelectedDate)
      .sort((a, b) => String(a.symbol).localeCompare(String(b.symbol)))
  }, [positions, analysisSelectedDate])

  const dayDrillTotals = useMemo(() => {
    let realised = 0
    let unrealised = 0
    let net = 0
    let openValue = 0
    let buy = 0
    let sell = 0
    let traded = 0
    let openPositions = 0
    for (const r of dayDrillRows) {
      const parts = deriveSnapshotParts(r)
      realised += parts.realisedPnl
      unrealised += parts.unrealisedPnl
      net += parts.netPnl
      openValue += parts.openValue
      if (parts.openQty !== 0) openPositions += 1
      const buyQty = Number(r.day_buy_qty ?? r.buy_qty ?? 0) || 0
      const sellQty = Number(r.day_sell_qty ?? r.sell_qty ?? 0) || 0
      const buyPx = Number(r.day_buy_avg_price ?? r.buy_avg_price ?? r.avg_buy_price ?? 0) || 0
      const sellPx = Number(r.day_sell_avg_price ?? r.sell_avg_price ?? r.avg_sell_price ?? 0) || 0
      if (buyQty > 0 && buyPx > 0) buy += buyQty * buyPx
      if (sellQty > 0 && sellPx > 0) sell += sellQty * sellPx
      if (buyQty > 0 || sellQty > 0) traded += 1
    }
    return { realised, unrealised, net, openValue, openPositions, buy, sell, total: buy + sell, traded }
  }, [dayDrillRows])

  const dayDrillColumns: GridColDef[] = [
    { field: 'symbol', headerName: 'Symbol', width: 220 },
    {
      field: 'product',
      headerName: 'Product',
      width: 95,
      renderCell: (params) => {
        const v = String(params.value ?? '').toUpperCase()
        const color = v === 'CNC' ? 'warning' : v === 'MIS' ? 'info' : 'default'
        return (
          <Chip
            size="small"
            label={v || '—'}
            color={color as any}
            variant="outlined"
            sx={{ height: 20, fontWeight: 700 }}
          />
        )
      },
    },
    {
      field: 'order_type',
      headerName: 'Type',
      width: 95,
      renderCell: (params) => {
        const v = String(params.value ?? '').toUpperCase()
        const color = v === 'BUY' ? 'success' : v === 'SELL' ? 'error' : 'default'
        return (
          <Chip
            size="small"
            label={v || '—'}
            color={color as any}
            variant="filled"
            sx={{ height: 20, fontWeight: 800 }}
          />
        )
      },
    },
    { field: 'day_buy_qty', headerName: 'Buy qty', width: 90, type: 'number' },
    { field: 'day_sell_qty', headerName: 'Sell qty', width: 90, type: 'number' },
    {
      field: '__open_qty',
      headerName: 'Open qty',
      width: 90,
      type: 'number',
      valueGetter: (_v, row) => deriveSnapshotParts(row as PositionSnapshot).openQty,
    },
    {
      field: 'realised',
      headerName: 'Realised',
      width: 120,
      type: 'number',
      renderCell: (params) => {
        const r = params.row as PositionSnapshot
        const val = deriveSnapshotParts(r).realisedPnl
        return <PnlChip value={val} />
      },
    },
    {
      field: 'unrealised',
      headerName: 'Unrealised',
      width: 120,
      type: 'number',
      renderCell: (params) => {
        const r = params.row as PositionSnapshot
        return <PnlChip value={deriveSnapshotParts(r).unrealisedPnl} />
      },
    },
    {
      field: 'pnl',
      headerName: 'Net P&L',
      width: 120,
      type: 'number',
      renderCell: (params) => <PnlChip value={Number(params.value || 0)} />,
    },
    {
      field: '__open_value',
      headerName: 'Open value',
      width: 130,
      type: 'number',
      valueGetter: (_v, row) => deriveSnapshotParts(row as PositionSnapshot).openValue,
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
  ]

  const columns: GridColDef[] = [
    { field: 'as_of_date', headerName: 'Date', width: 110 },
    {
      field: 'symbol',
      headerName: 'Symbol',
      width: 240,
      renderCell: (params) => {
        const r = params.row as PositionSnapshot
        const symbol = String(params.value ?? '').toUpperCase()
        const product = String(r.product ?? '').toUpperCase()
        const buyQty = Number(r.day_buy_qty ?? r.buy_qty ?? 0) || 0
        const sellQty = Number(r.day_sell_qty ?? r.sell_qty ?? 0) || 0
        const side = String(
          r.order_type ?? (sellQty > 0 && buyQty === 0 ? 'SELL' : buyQty > 0 && sellQty === 0 ? 'BUY' : ''),
        ).toUpperCase()
        const showSoldHolding = product === 'CNC' && side === 'SELL' && buyQty === 0 && sellQty > 0
        return (
          <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0 }}>
            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {symbol || '—'}
            </span>
            {showSoldHolding ? (
              <Chip
                size="small"
                label="SOLD HOLDING"
                variant="outlined"
                color="warning"
                sx={{ height: 20, fontWeight: 600 }}
              />
            ) : null}
          </Stack>
        )
      },
    },
    { field: 'exchange', headerName: 'Exch', width: 80 },
    {
      field: 'product',
      headerName: 'Product',
      width: 95,
      renderCell: (params) => {
        const v = String(params.value ?? '').toUpperCase()
        const color = v === 'CNC' ? 'warning' : v === 'MIS' ? 'info' : 'default'
        return (
          <Chip
            size="small"
            label={v || '—'}
            color={color as any}
            variant="outlined"
            sx={{ height: 20, fontWeight: 700 }}
          />
        )
      },
    },
    {
      field: 'order_type',
      headerName: 'Type',
      width: 95,
      renderCell: (params) => {
        const v = String(params.value ?? '').toUpperCase()
        const color = v === 'BUY' ? 'success' : v === 'SELL' ? 'error' : 'default'
        return (
          <Chip
            size="small"
            label={v || '—'}
            color={color as any}
            variant="filled"
            sx={{ height: 20, fontWeight: 800 }}
          />
        )
      },
    },
    {
      field: 'qty',
      headerName: 'Qty',
      width: 90,
      type: 'number',
    },
    {
      field: 'remaining_qty',
      headerName: 'Holding Qty',
      width: 100,
      type: 'number',
    },
    {
      field: 'traded_qty',
      headerName: 'Traded Qty',
      width: 105,
      type: 'number',
      renderHeader: () => (
        <HeaderWithTooltip
          label="Traded Qty"
          tooltip="Total traded quantity (buy+sell) for the day. Realized P&L uses realized qty (typically min(buy_qty, sell_qty))."
        />
      ),
    },
    {
      field: 'avg_price',
      headerName: 'Avg',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'avg_buy_price',
      headerName: 'Buy Avg',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'avg_sell_price',
      headerName: 'Sell Avg',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'pnl_value',
      headerName: 'Realized P&L',
      width: 140,
      type: 'number',
      renderHeader: () => (
        <HeaderWithTooltip
          label="Realized P&L"
          tooltip="Realized P&L = (avg sell - avg buy) * realized qty. Realized qty is usually min(buy_qty, sell_qty); for delivery sells against holdings, it can be the sell qty."
        />
      ),
      valueGetter: (_value, row) => {
        const r = row as PositionSnapshot
        if (r.avg_buy_price == null || r.avg_sell_price == null) return null
        return r.pnl_value ?? null
      },
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'pnl_pct',
      headerName: 'Realized %',
      width: 130,
      type: 'number',
      renderHeader: () => (
        <HeaderWithTooltip
          label="Realized %"
          tooltip="Realized % = Realized P&L / (avg buy * realized qty). Uses the same realized qty logic as Realized P&L."
        />
      ),
      valueGetter: (_value, row) => {
        const r = row as PositionSnapshot
        if (r.avg_buy_price == null || r.avg_sell_price == null) return null
        return r.pnl_pct ?? null
      },
      valueFormatter: (v) => (v != null ? `${Number(v).toFixed(2)}%` : '-'),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'ltp',
      headerName: 'LTP',
      width: 100,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'today_pnl',
      headerName: 'Today P&L',
      width: 120,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'today_pnl_pct',
      headerName: 'Today %',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? `${Number(v).toFixed(2)}%` : ''),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'captured_at',
      headerName: 'Captured',
      width: 190,
      valueFormatter: (v) =>
        v ? formatInDisplayTimeZone(String(v), displayTimeZone) : '',
    },
  ]

  const txColumns: GridColDef[] = [
    { field: 'as_of_date', headerName: 'Date', width: 110 },
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    { field: 'exchange', headerName: 'Exch', width: 80 },
    { field: 'product', headerName: 'Product', width: 90 },
    { field: 'side', headerName: 'Side', width: 90 },
    {
      field: 'qty',
      headerName: 'Qty',
      width: 100,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(0) : ''),
    },
    {
      field: 'avg_price',
      headerName: 'Avg',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'notional',
      headerName: 'Notional',
      width: 140,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
  ]

  const dailyColumns: GridColDef[] = [
    { field: 'as_of_date', headerName: 'Date', width: 110 },
    {
      field: 'turnover_buy',
      headerName: 'Buy turnover',
      width: 140,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
    {
      field: 'turnover_sell',
      headerName: 'Sell turnover',
      width: 140,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
    {
      field: 'net_cashflow',
      headerName: 'Net cash',
      width: 130,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'cash_balance',
      headerName: 'Cash',
      width: 140,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
    {
      field: 'holdings_value',
      headerName: 'Holdings',
      width: 150,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
    {
      field: 'net_liq',
      headerName: 'Net liq',
      width: 150,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
    { field: 'tx_count', headerName: '# Tx', width: 90, type: 'number' },
  ]

  const postbackRows = useMemo(() => {
    return postbackEvents.map((e) => {
      const details = asRecord(e.details)
      const statusCode = details?.status_code
      const detail = (details?.detail as string | undefined) || e.message
      const kind =
        e.category === 'zerodha_postback'
          ? 'Received'
          : e.category === 'zerodha_postback_error'
            ? 'Rejected'
            : e.category === 'zerodha_postback_noise'
              ? 'Ignored'
              : e.category
      return {
        id: e.id,
        created_at: e.created_at,
        kind,
        level: e.level,
        status_code: statusCode != null ? Number(statusCode) : null,
        detail,
      }
    })
  }, [postbackEvents])

  const selectedPostbackEvent = useMemo(() => {
    if (postbackSelectedId == null) return null
    return postbackEvents.find((e) => e.id === postbackSelectedId) ?? null
  }, [postbackEvents, postbackSelectedId])

  const selectedPostbackDetailsText = useMemo(() => {
    if (!selectedPostbackEvent) return ''
    if (selectedPostbackEvent.details != null) {
      return JSON.stringify(selectedPostbackEvent.details, null, 2)
    }
    if (selectedPostbackEvent.raw_details) {
      return String(selectedPostbackEvent.raw_details)
    }
    return ''
  }, [selectedPostbackEvent])

  const postbackColumns: GridColDef[] = [
    {
      field: 'created_at',
      headerName: 'Time',
      width: 190,
      valueFormatter: (v) => formatInDisplayTimeZone(String(v), displayTimeZone),
    },
    { field: 'kind', headerName: 'Type', width: 110 },
    { field: 'status_code', headerName: 'Code', width: 90, type: 'number' },
    { field: 'detail', headerName: 'Detail', flex: 1, minWidth: 260 },
  ]

  const postbackFailureCount = useMemo(() => {
    let n = 0
    for (const e of postbackEvents) {
      if (e.category === 'zerodha_postback_error' || e.category === 'zerodha_postback_noise') n += 1
    }
    return n
  }, [postbackEvents])

  const postbackLastFailureAt = useMemo(() => {
    const failures = postbackEvents.filter(
      (e) => e.category === 'zerodha_postback_error' || e.category === 'zerodha_postback_noise',
    )
    if (failures.length === 0) return null
    let maxTs = -1
    let best: string | null = null
    for (const e of failures) {
      const ts = Date.parse(e.created_at)
      if (Number.isFinite(ts) && ts > maxTs) {
        maxTs = ts
        best = e.created_at
      }
    }
    return best ?? failures[0].created_at
  }, [postbackEvents])

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Positions
      </Typography>
      {coverageCount ? (
        <Box sx={{ mb: 1 }}>
          <Tooltip title="Broker-direct holdings/positions without an attached playbook are surfaced as unmanaged. Click to review." arrow>
            <Chip
              size="small"
              color={coverageCount.unmanaged_open > 0 ? 'warning' : 'success'}
              label={coverageCount.unmanaged_open > 0 ? `Unmanaged: ${coverageCount.unmanaged_open}` : 'Coverage OK'}
              onClick={() => navigate('/ai?tab=coverage')}
              sx={{ cursor: 'pointer' }}
            />
          </Tooltip>
        </Box>
      ) : null}
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 3,
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        <Typography color="text.secondary">
	          {activeTab === 'snapshots'
	            ? 'Daily position snapshots (from broker positions). Refresh captures a new snapshot for today.'
	            : activeTab === 'transactions'
	              ? 'Transaction timeline and cash/funds curve derived from daily position snapshots (day buy/sell fields).'
	              : 'Day-by-day P&L derived from broker snapshots (realised/unrealised/pnl) with drilldown.'}
	        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          {brokers.length > 0 && (
            <TextField
              select
              label="Broker"
              size="small"
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
          <TextField
            label="From"
            type="date"
            size="small"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label="To"
            type="date"
            size="small"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
          <Button
            size="small"
            variant="outlined"
            onClick={() => applyDatePreset(1)}
            disabled={loading || refreshing}
          >
            Today
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => applyDatePreset(7)}
            disabled={loading || refreshing}
          >
            7D
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={() => applyDatePreset(15)}
            disabled={loading || refreshing}
          >
            15D
          </Button>
          <TextField
            label="Symbol"
            size="small"
            value={symbolQuery}
            onChange={(e) => setSymbolQuery(e.target.value.toUpperCase())}
            sx={{ minWidth: 140 }}
            InputProps={{
              endAdornment: symbolQuery ? (
                <InputAdornment position="end">
                  <IconButton
                    size="small"
                    aria-label="Clear symbol"
                    onClick={() => setSymbolQuery('')}
                    edge="end"
                  >
                    <ClearIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ) : null,
            }}
          />
	          <FormControlLabel
	            control={
	              <Checkbox
	                checked={activeTab === 'snapshots' ? includeZero : true}
	                onChange={(e) => setIncludeZero(e.target.checked)}
	                disabled={activeTab !== 'snapshots'}
	              />
	            }
	            label="Include zero qty"
	            sx={{ mr: 0 }}
	          />
          <FormControlLabel
            control={
              <Switch checked={live} onChange={(e) => setLive(e.target.checked)} disabled={refreshing} />
            }
            label="Live"
            sx={{ mr: 0 }}
          />
	          {live ? (
	            <Stack direction="row" alignItems="center" spacing={0.75} sx={{ ml: 0.5 }}>
	              {polling ? <CircularProgress size={14} /> : null}
	              <Typography variant="caption" color="text.secondary">
	                {lastLiveUpdateAt
	                  ? `Updated ${formatInDisplayTimeZone(lastLiveUpdateAt, displayTimeZone)}`
	                  : '—'}
              </Typography>
            </Stack>
          ) : null}
          {activeTab === 'transactions' && (
            <TextField
              label="Starting cash (₹)"
              size="small"
              type="number"
              value={startingCash}
              onChange={(e) => setStartingCash(Number(e.target.value))}
              inputProps={{ min: 0 }}
              sx={{ width: 190 }}
              helperText="Used to build cash curve"
            />
          )}
          <Button size="small" variant="outlined" onClick={() => void handleApply()} disabled={loading || refreshing}>
            Apply
          </Button>
          <Button size="small" variant="outlined" onClick={handleRefresh} disabled={loading || refreshing}>
            {refreshing ? 'Refreshing…' : `Refresh from ${selectedBroker}`}
          </Button>
        </Stack>
      </Box>

      {selectedBroker === 'zerodha' && (
        <Accordion sx={{ mb: 2 }} defaultExpanded={false}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ width: '100%', flexWrap: 'wrap' }}>
              <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 220 }}>
                Zerodha postback failures
              </Typography>
              <Chip
                size="small"
                label={`${postbackFailureCount} issue${postbackFailureCount === 1 ? '' : 's'}`}
                color={postbackFailureCount > 0 ? 'warning' : 'default'}
                variant={postbackFailureCount > 0 ? 'filled' : 'outlined'}
              />
              <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>
                {postbackLastFailureAt
                  ? `Last: ${formatInDisplayTimeZone(postbackLastFailureAt, displayTimeZone)}`
                  : 'Last: —'}
              </Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={postbackIncludeOk}
                    onChange={(e) => setPostbackIncludeOk(e.target.checked)}
                    disabled={postbackLoading || postbackClearing}
                  />
                }
                label="Include received"
                sx={{ mr: 0 }}
              />
              <Button
                size="small"
                variant="outlined"
                onClick={() => void loadZerodhaPostbacks()}
                disabled={postbackLoading || postbackClearing}
              >
                {postbackLoading ? 'Loading…' : 'Refresh log'}
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="warning"
                onClick={() => void handleClearPostbackFailures()}
                disabled={postbackLoading || postbackClearing}
              >
                {postbackClearing ? 'Clearing…' : 'Clear failures'}
              </Button>
            </Box>

            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              {zerodhaStatus?.last_postback_at
                ? `Last received: ${formatInDisplayTimeZone(zerodhaStatus.last_postback_at, displayTimeZone)}`
                : 'Last received: (none yet)'}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              {zerodhaStatus?.last_postback_reject_at
                ? `Last rejected: ${formatInDisplayTimeZone(zerodhaStatus.last_postback_reject_at, displayTimeZone)}`
                : 'Last rejected: (none)'}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              {zerodhaStatus?.last_postback_noise_at
                ? `Last ignored (missing checksum/signature): ${formatInDisplayTimeZone(zerodhaStatus.last_postback_noise_at, displayTimeZone)}`
                : 'Last ignored (missing checksum/signature): (none)'}
            </Typography>

            {postbackError && (
              <Typography variant="caption" color="error" sx={{ display: 'block', mt: 0.5 }}>
                {postbackError}
              </Typography>
            )}

            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mt: 1, alignItems: 'stretch' }}>
              <Box sx={{ flex: 1, minWidth: 520, height: 260 }}>
                <DataGrid
                  rows={postbackRows}
                  columns={postbackColumns}
                  density="compact"
                  disableRowSelectionOnClick
                  hideFooter
                  onRowClick={(params) => setPostbackSelectedId(Number(params.id))}
                />
              </Box>
              <TextField
                size="small"
                label="Selected event details"
                value={selectedPostbackDetailsText}
                sx={{ flex: 1, minWidth: 340 }}
                multiline
                minRows={12}
                inputProps={{ readOnly: true, style: { fontFamily: 'monospace' } }}
                placeholder="Click an event row to view details"
              />
            </Box>
          </AccordionDetails>
        </Accordion>
      )}

      <Paper sx={{ mb: 2 }}>
        <Tabs
          value={activeTab}
          onChange={(_e, v) => {
            setActiveTab(v)
            if (v === 'analysis') void loadSnapshots({ includeZeroOverride: true })
            if (v === 'transactions') void loadSnapshots({ includeZeroOverride: true })
          }}
          variant="scrollable"
          scrollButtons="auto"
	        >
	          <Tab value="snapshots" label="Daily snapshots" />
	          <Tab value="analysis" label="Daily P&L" />
	          <Tab value="transactions" label="Transactions charts" />
	        </Tabs>
	      </Paper>

      {activeTab === 'snapshots' ? (
        loading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Loading positions…</Typography>
          </Box>
        ) : error ? (
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        ) : (
          <Box sx={{ height: 'calc(100vh - 280px)', minHeight: 360 }}>
            <DataGrid
              rows={positions}
              columns={columns}
              getRowId={(r) => r.id}
              density="compact"
              disableRowSelectionOnClick
              sx={{
                '& .pnl-negative': {
                  color: 'error.main',
                },
              }}
              slots={{ toolbar: GridToolbar }}
              slotProps={{
                toolbar: {
                  showQuickFilter: true,
                  quickFilterProps: { debounceMs: 300 },
                },
              }}
              initialState={{
                pagination: { paginationModel: { pageSize: 25 } },
              }}
              pageSizeOptions={[25, 50, 100]}
            />
          </Box>
        )
      ) : activeTab === 'transactions' ? (
        loading ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CircularProgress size={20} />
            <Typography variant="body2">Loading snapshots…</Typography>
          </Box>
        ) : error ? (
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        ) : dailyCash.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No data available for this date range. Try widening the range and click Apply.
          </Typography>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Trades on holdings value
              </Typography>
              <PriceChart
                candles={holdingsCandles}
                chartType="line"
                markers={txMarkers}
                height={300}
                showLegend
                baseSeriesName="Holdings value"
              />
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', mt: 1 }}
              >
                Markers use day buy/sell qty and avg prices from broker snapshots (end-of-day view).
              </Typography>
            </Paper>

            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Cash and funds curve
              </Typography>
              <PriceChart
                candles={cashCandles}
                chartType="line"
                overlays={fundsOverlays}
                height={300}
                showLegend
                baseSeriesName="Cash balance"
              />
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: 'block', mt: 1 }}
              >
                Cash curve starts at your provided “Starting cash (₹)”. Net liquidation = cash + holdings value.
              </Typography>
            </Paper>

            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Daily funds table
              </Typography>
              <Box sx={{ height: 320 }}>
                <DataGrid
                  rows={dailyCash}
                  columns={dailyColumns}
                  getRowId={(r) => r.id}
                  density="compact"
                  disableRowSelectionOnClick
                  sx={{ '& .pnl-negative': { color: 'error.main' } }}
                  initialState={{ pagination: { paginationModel: { pageSize: 15 } } }}
                  pageSizeOptions={[15, 30, 100]}
                />
              </Box>
            </Paper>

            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Transactions table
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <Box sx={{ height: 420 }}>
                <DataGrid
                  rows={transactions}
                  columns={txColumns}
                  getRowId={(r) => r.id}
                  density="compact"
                  disableRowSelectionOnClick
                  slots={{ toolbar: GridToolbar }}
                  slotProps={{
                    toolbar: {
                      showQuickFilter: true,
                      quickFilterProps: { debounceMs: 300 },
                    },
                  }}
                  initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
                  pageSizeOptions={[25, 50, 100]}
                />
              </Box>
            </Paper>
	          </Box>
	        )
	      ) : loading ? (
	        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
	          <CircularProgress size={20} />
	          <Typography variant="body2">Loading snapshots…</Typography>
	        </Box>
	      ) : error ? (
	        <Typography variant="body2" color="error">
	          {error}
	        </Typography>
	      ) : dailyReality.length === 0 ? (
	        <Typography variant="body2" color="text.secondary">
	          No data available for this date range. Try widening the range and click Apply.
	        </Typography>
	      ) : (
	        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
	          <Paper sx={{ p: 2 }}>
	            <Typography variant="h6" gutterBottom>
	              Reality check (broker snapshots)
	            </Typography>
		            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
		              <Chip size="small" label={`Range: ${startDate || '—'} → ${endDate || '—'}`} />
		              <Chip size="small" label={`Broker: ${selectedBroker}`} />
		              <Chip size="small" label={`Rows: ${positions.length}`} />
		              <Chip size="small" label={`Turnover: ${formatInr(realityTotals.total)}`} />
		              <Chip size="small" label={`Open value: ${formatInr(realityTotals.openValue)}`} />
		              <Chip size="small" label="Realised" variant="outlined" />
		              <PnlChip value={realityTotals.realised} />
		              <Chip size="small" label="Unrealised" variant="outlined" />
		              <PnlChip value={realityTotals.unrealised} />
		              <Chip size="small" label="Net" variant="outlined" />
		              <PnlChip value={realityTotals.net} />
		            </Box>
	            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
	              These numbers are aggregated from the broker positions snapshots (realised/unrealised/pnl fields).
	              Charges/fees are not included in the snapshots; we’ll add a contract-note based charges view separately.
	            </Typography>
		          </Paper>

		          <Paper sx={{ p: 2 }}>
		            <Typography variant="h6" gutterBottom>
		              P&L curve (Net vs Realised/Unrealised)
		            </Typography>
		            <PriceChart
		              candles={netPnlCandles}
		              chartType="line"
		              overlays={pnlOverlays}
		              height={260}
		              showLegend
		              baseSeriesName="Net P&L"
		            />
		          </Paper>
	
		          <Paper sx={{ p: 2 }}>
		            <Typography variant="h6" gutterBottom>
		              Day-by-day P&L (click a day to drill down)
	            </Typography>
	            <Box sx={{ height: 340 }}>
	              <DataGrid
	                rows={dailyReality}
	                columns={dailyRealityColumns}
	                getRowId={(r) => r.id}
	                density="compact"
	                disableRowSelectionOnClick
	                onRowClick={(params) => setAnalysisSelectedDate(String(params.id))}
	                getRowClassName={(params) =>
	                  analysisSelectedDate && String(params.id) === analysisSelectedDate ? 'reality-selected' : ''
	                }
	                sx={{
	                  '& .reality-selected': {
	                    outline: '1px solid',
	                    outlineColor: 'primary.main',
	                    backgroundColor: 'rgba(25, 118, 210, 0.08)',
	                  },
	                }}
	                initialState={{ pagination: { paginationModel: { pageSize: 15 } } }}
	                pageSizeOptions={[15, 30, 100]}
	              />
	            </Box>
	          </Paper>

	          <Paper sx={{ p: 2 }}>
	            <Typography variant="h6" gutterBottom>
	              Drilldown: {analysisSelectedDate || '—'}
	            </Typography>
	            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center', mb: 1 }}>
	              <Chip size="small" label={`# traded: ${dayDrillTotals.traded}`} />
	              <Chip size="small" label={`# open pos: ${dayDrillTotals.openPositions}`} />
	              <Chip size="small" label={`Turnover: ${formatInr(dayDrillTotals.total)}`} />
	              <Chip size="small" label={`Open value: ${formatInr(dayDrillTotals.openValue)}`} />
	              <Chip size="small" label="Realised" variant="outlined" />
	              <PnlChip value={dayDrillTotals.realised} />
	              <Chip size="small" label="Unrealised" variant="outlined" />
	              <PnlChip value={dayDrillTotals.unrealised} />
	              <Chip size="small" label="Net" variant="outlined" />
	              <PnlChip value={dayDrillTotals.net} />
	            </Box>
	            <Box sx={{ height: 420 }}>
	              <DataGrid
	                rows={dayDrillRows}
	                columns={dayDrillColumns}
	                getRowId={(r) => r.id}
	                density="compact"
	                disableRowSelectionOnClick
	                slots={{ toolbar: GridToolbar }}
	                slotProps={{
	                  toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 300 } },
	                }}
	                initialState={{ pagination: { paginationModel: { pageSize: 25 } } }}
	                pageSizeOptions={[25, 50, 100]}
	              />
	            </Box>
	          </Paper>

		          <Accordion defaultExpanded={false}>
		            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
		              <Stack direction="row" spacing={1} alignItems="center" sx={{ width: '100%', flexWrap: 'wrap' }}>
		                <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 260 }}>
		                  Order analytics (SigmaTrader)
		                </Typography>
		                {orderInsights ? (
		                  <Chip
		                    size="small"
		                    label={`Orders: ${orderInsights.summary.orders_total} • Exec: ${orderInsights.summary.orders_executed}`}
		                  />
		                ) : (
		                  <Chip size="small" label="Not loaded" variant="outlined" />
		                )}
		              </Stack>
		            </AccordionSummary>
		            <AccordionDetails>
		              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
		                Shows alerts received, risk decisions (placed/blocked), and orders created/executed by SigmaTrader. This does not include broker-side manual trades.
		              </Typography>
		              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center" sx={{ mb: 1 }}>
		                <Button
		                  size="small"
		                  variant="outlined"
		                  onClick={() => void loadOrderInsights({ startDateOverride: startDate, endDateOverride: endDate })}
		                  disabled={orderInsightsLoading}
		                >
		                  {orderInsightsLoading ? 'Loading…' : 'Load'}
		                </Button>
		                {orderInsightsError ? (
		                  <Typography variant="caption" color="error">
		                    {orderInsightsError}
		                  </Typography>
		                ) : null}
		              </Stack>
		              {orderInsights ? (
		                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
		                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
		                    <Chip size="small" label={`TV alerts: ${orderInsights.summary.tv_alerts}`} />
		                    <Chip
		                      size="small"
		                      label={`Decisions: ${orderInsights.summary.decisions_placed} placed • ${orderInsights.summary.decisions_blocked} blocked`}
		                    />
		                    <Chip
		                      size="small"
		                      label={`TV share: ${
		                        orderInsights.summary.decisions_total
		                          ? Math.round((orderInsights.summary.decisions_from_tv * 100) / orderInsights.summary.decisions_total)
		                          : 0
		                      }%`}
		                    />
		                    <Chip
		                      size="small"
		                      label={`Orders: ${orderInsights.summary.orders_total} • Exec: ${orderInsights.summary.orders_executed}`}
		                    />
		                    <Chip
		                      size="small"
		                      label={`Exec rate: ${
		                        orderInsights.summary.orders_total
		                          ? Math.round((orderInsights.summary.orders_executed * 100) / orderInsights.summary.orders_total)
		                          : 0
		                      }%`}
		                    />
		                    <Chip size="small" label={`MIS: ${orderInsights.summary.order_products?.MIS ?? 0}`} />
		                    <Chip size="small" label={`CNC: ${orderInsights.summary.order_products?.CNC ?? 0}`} />
		                    <Chip size="small" label={`BUY: ${orderInsights.summary.order_sides?.BUY ?? 0}`} />
		                    <Chip size="small" label={`SELL: ${orderInsights.summary.order_sides?.SELL ?? 0}`} />
		                  </Box>

		                  <Box sx={{ height: 320 }}>
		                    <DataGrid
		                      rows={orderInsights.daily.map((r) => ({ id: r.day, ...r }))}
		                      columns={[
		                        { field: 'day', headerName: 'Date', width: 110 },
		                        { field: 'tv_alerts', headerName: 'TV', width: 70, type: 'number' },
		                        { field: 'decisions_placed', headerName: 'Placed', width: 80, type: 'number' },
		                        { field: 'decisions_blocked', headerName: 'Blocked', width: 90, type: 'number' },
		                        { field: 'orders_total', headerName: 'Orders', width: 85, type: 'number' },
		                        { field: 'orders_executed', headerName: 'Exec', width: 75, type: 'number' },
		                        { field: 'orders_rejected_risk', headerName: 'Risk rej', width: 90, type: 'number' },
		                        { field: 'orders_failed', headerName: 'Failed', width: 80, type: 'number' },
		                        {
		                          field: 'mix_product',
		                          headerName: 'MIS/CNC',
		                          width: 120,
		                          valueGetter: (_v, row) =>
		                            `MIS:${row.order_products?.MIS ?? 0} CNC:${row.order_products?.CNC ?? 0}`,
		                        },
		                        {
		                          field: 'mix_side',
		                          headerName: 'BUY/SELL',
		                          width: 120,
		                          valueGetter: (_v, row) =>
		                            `B:${row.order_sides?.BUY ?? 0} S:${row.order_sides?.SELL ?? 0}`,
		                        },
		                      ]}
		                      density="compact"
		                      disableRowSelectionOnClick
		                      initialState={{ pagination: { paginationModel: { pageSize: 15 } } }}
		                      pageSizeOptions={[15, 30, 100]}
		                    />
		                  </Box>

		                  <Box sx={{ height: 340 }}>
		                    <DataGrid
		                      rows={orderInsights.top_symbols.map((r) => ({ id: r.symbol, ...r }))}
		                      columns={[
		                        { field: 'symbol', headerName: 'Symbol', width: 140 },
		                        { field: 'buys', headerName: 'Buy', width: 80, type: 'number' },
		                        { field: 'sells', headerName: 'Sell', width: 80, type: 'number' },
		                        { field: 'orders_total', headerName: 'Orders', width: 90, type: 'number' },
		                        { field: 'orders_executed', headerName: 'Exec', width: 80, type: 'number' },
		                        { field: 'decisions_blocked', headerName: 'Blocked', width: 90, type: 'number' },
		                      ]}
		                      density="compact"
		                      disableRowSelectionOnClick
		                      slots={{ toolbar: GridToolbar }}
		                      slotProps={{
		                        toolbar: { showQuickFilter: true, quickFilterProps: { debounceMs: 300 } },
		                      }}
		                      initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
		                      pageSizeOptions={[10, 20, 50]}
		                    />
		                  </Box>

		                  {orderInsights.top_block_reasons?.length ? (
		                    <Box>
		                      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
		                        Top block reasons
		                      </Typography>
		                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
		                        {orderInsights.top_block_reasons.map((r) => (
		                          <Chip key={r.reason} size="small" label={`${r.reason} (${r.count})`} variant="outlined" />
		                        ))}
		                      </Stack>
		                    </Box>
		                  ) : null}
		                </Box>
		              ) : null}
		            </AccordionDetails>
		          </Accordion>
	        </Box>
	      )}
    </Box>
  )
}
