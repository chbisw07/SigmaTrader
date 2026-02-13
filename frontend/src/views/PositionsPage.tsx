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

import {
  PriceChart,
  type PriceCandle,
  type PriceOverlay,
  type PriceSignalMarker,
} from '../components/PriceChart'
import {
  fetchDailyPositions,
  fetchPositionsAnalysis,
  syncPositions,
  type PositionsAnalysis,
  type PositionSnapshot,
} from '../services/positions'
import { fetchBrokers, type BrokerInfo } from '../services/brokers'
import {
  clearZerodhaPostbackFailures,
  fetchZerodhaPostbackEvents,
  fetchZerodhaStatus,
  type ZerodhaPostbackEvent,
  type ZerodhaStatus,
} from '../services/zerodha'
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

const formatPct = (n: number | null | undefined) => {
  if (n == null || !Number.isFinite(Number(n))) return '—'
  return `${(Number(n) * 100).toFixed(1)}%`
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
  const defaults = defaultDateRange()
  type PositionsTab = 'snapshots' | 'analysis' | 'transactions'
  const [activeTab, setActiveTab] = useState<PositionsTab>('snapshots')
  const [positions, setPositions] = useState<PositionSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [polling, setPolling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [live, setLive] = useState(true)
  const [analysis, setAnalysis] = useState<PositionsAnalysis | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisPolling, setAnalysisPolling] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [brokers, setBrokers] = useState<BrokerInfo[]>([])
  const [selectedBroker, setSelectedBroker] = useState<string>('zerodha')
  const loadSeqRef = useRef(0)
  const analysisSeqRef = useRef(0)
  const positionsKeyRef = useRef<string>('')
  const analysisKeyRef = useRef<string>('')
  const [lastLiveUpdateAt, setLastLiveUpdateAt] = useState<string | null>(null)
  const symbolApplyTimeoutRef = useRef<number | null>(null)
  const symbolAutoApplyMountedRef = useRef(false)

  const [startDate, setStartDate] = useState<string>(defaults.from)
  const [endDate, setEndDate] = useState<string>(defaults.to)
  const [symbolQuery, setSymbolQuery] = useState<string>('')
  const [includeZero, setIncludeZero] = useState(true)
  const [startingCash, setStartingCash] = useState(0)

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

  const loadAnalysis = async (opts?: { silent?: boolean; startDateOverride?: string; endDateOverride?: string }) => {
    const seq = (analysisSeqRef.current += 1)
    try {
      if (opts?.silent) setAnalysisPolling(true)
      else setAnalysisLoading(true)
      const startDateParam = opts?.startDateOverride ?? startDate
      const endDateParam = opts?.endDateOverride ?? endDate
      const data = await fetchPositionsAnalysis({
        broker_name: selectedBroker,
        start_date: startDateParam || undefined,
        end_date: endDateParam || undefined,
        symbol: symbolQuery || undefined,
        top_n: 10,
      })
      if (seq !== analysisSeqRef.current) return
      const key = JSON.stringify(data.summary ?? {})
      if (key !== analysisKeyRef.current) {
        analysisKeyRef.current = key
        setAnalysis(data)
        setLastLiveUpdateAt(new Date().toISOString())
      }
      if (!opts?.silent) setAnalysisError(null)
    } catch (err) {
      if (seq !== analysisSeqRef.current) return
      if (!opts?.silent) {
        setAnalysisError(err instanceof Error ? err.message : 'Failed to load analysis')
      }
    } finally {
      if (seq === analysisSeqRef.current) {
        if (opts?.silent) setAnalysisPolling(false)
        else setAnalysisLoading(false)
      }
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
    analysisKeyRef.current = ''
    setError(null)
    setZerodhaStatus(null)
    setPostbackEvents([])
    setPostbackError(null)
    setPostbackSelectedId(null)
    void loadSnapshots()
    if (activeTab === 'analysis') void loadAnalysis()
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
      } else if (activeTab === 'analysis') void loadAnalysis({ silent: true })
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
        await loadAnalysis()
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
      await loadAnalysis({ startDateOverride: opts?.startDate, endDateOverride: opts?.endDate })
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

  const monthlyColumns: GridColDef[] = [
    { field: 'month', headerName: 'Month', width: 110 },
    {
      field: 'trades_pnl',
      headerName: 'Closed trades P&L',
      width: 170,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    {
      field: 'trades_count',
      headerName: '# Trades',
      width: 95,
      type: 'number',
    },
    {
      field: 'win_rate',
      headerName: 'Win rate',
      width: 105,
      valueFormatter: (v) => formatPct(Number(v)),
    },
    {
      field: 'turnover_total',
      headerName: 'Turnover',
      width: 140,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
    },
  ]

  const symbolPnlColumns: GridColDef[] = [
    { field: 'symbol', headerName: 'Symbol', width: 130 },
    { field: 'product', headerName: 'Product', width: 90 },
    {
      field: 'pnl',
      headerName: 'P&L',
      width: 130,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
    { field: 'trades', headerName: 'Trades', width: 90, type: 'number' },
    {
      field: 'win_rate',
      headerName: 'Win rate',
      width: 110,
      valueFormatter: (v) => formatPct(Number(v)),
    },
  ]

  const openPositionsColumns: GridColDef[] = [
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    { field: 'exchange', headerName: 'Exch', width: 80 },
    { field: 'product', headerName: 'Product', width: 90 },
    { field: 'qty', headerName: 'Qty', width: 90, type: 'number' },
    {
      field: 'avg_price',
      headerName: 'Avg',
      width: 110,
      type: 'number',
      valueFormatter: (v) => (v != null ? Number(v).toFixed(2) : ''),
    },
    {
      field: 'pnl',
      headerName: 'P&L',
      width: 120,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
    },
  ]

  const closedTradesColumns: GridColDef[] = [
    { field: 'symbol', headerName: 'Symbol', width: 140 },
    { field: 'product', headerName: 'Product', width: 90 },
    {
      field: 'opened_at',
      headerName: 'Opened',
      width: 180,
      valueFormatter: (v) =>
        v ? formatInDisplayTimeZone(String(v), displayTimeZone) : '',
    },
    {
      field: 'closed_at',
      headerName: 'Closed',
      width: 180,
      valueFormatter: (v) =>
        v ? formatInDisplayTimeZone(String(v), displayTimeZone) : '',
    },
    {
      field: 'pnl',
      headerName: 'P&L',
      width: 120,
      type: 'number',
      valueFormatter: (v) => formatInr(Number(v), { fractionDigits: 0 }),
      cellClassName: (params: GridCellParams) =>
        params.value != null && Number(params.value) < 0 ? 'pnl-negative' : '',
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
              : 'Trading insights from executed orders (closed trades) + daily position snapshots (turnover).'}
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
                checked={activeTab === 'transactions' ? true : includeZero}
                onChange={(e) => setIncludeZero(e.target.checked)}
                disabled={activeTab === 'transactions'}
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
              {polling || analysisPolling ? <CircularProgress size={14} /> : null}
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
            if (v === 'analysis' && analysis == null && !analysisLoading) void loadAnalysis()
            if (v === 'transactions') void loadSnapshots({ includeZeroOverride: true })
          }}
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab value="snapshots" label="Daily snapshots" />
          <Tab value="analysis" label="Positions analysis" />
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
      ) : analysisLoading ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CircularProgress size={20} />
          <Typography variant="body2">Loading analysis…</Typography>
        </Box>
      ) : analysisError ? (
        <Typography variant="body2" color="error">
          {analysisError}
        </Typography>
      ) : !analysis ? (
        <Typography variant="body2" color="text.secondary">
          No analysis available yet. Try selecting a date range with executed trades, then click Apply.
        </Typography>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Overview
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center' }}>
              <Chip
                size="small"
                label={`Range: ${analysis.summary.date_from} → ${analysis.summary.date_to}`}
              />
              <Chip size="small" label={`Broker: ${analysis.summary.broker_name}`} />
              <Chip size="small" label={`Closed trades: ${analysis.summary.trades_count}`} />
              <Chip size="small" label={`Win rate: ${formatPct(analysis.summary.trades_win_rate)}`} />
              <Chip size="small" label={`Open positions: ${analysis.summary.open_positions_count}`} />
              <Chip size="small" label={`Turnover: ${formatInr(analysis.summary.turnover_total)}`} />
              <PnlChip value={analysis.summary.trades_pnl} />
            </Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              Turnover is estimated from daily position snapshots (day buy/sell fields). Closed trade P&L is from analytics trades.
            </Typography>
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Monthly performance
            </Typography>
            <Box sx={{ height: 340 }}>
              <DataGrid
                rows={analysis.monthly}
                columns={monthlyColumns}
                getRowId={(r) => r.month}
                density="compact"
                disableRowSelectionOnClick
                sx={{ '& .pnl-negative': { color: 'error.main' } }}
                initialState={{ pagination: { paginationModel: { pageSize: 12 } } }}
                pageSizeOptions={[12, 24, 60]}
              />
            </Box>
          </Paper>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
              gap: 2,
            }}
          >
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Winners (closed trades)
              </Typography>
              <Box sx={{ height: 320 }}>
                <DataGrid
                  rows={analysis.winners}
                  columns={symbolPnlColumns}
                  getRowId={(r) => `${r.symbol}:${r.product || ''}`}
                  density="compact"
                  disableRowSelectionOnClick
                  sx={{ '& .pnl-negative': { color: 'error.main' } }}
                  initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
                  pageSizeOptions={[10]}
                />
              </Box>
            </Paper>

            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Losers (closed trades)
              </Typography>
              <Box sx={{ height: 320 }}>
                <DataGrid
                  rows={analysis.losers}
                  columns={symbolPnlColumns}
                  getRowId={(r) => `${r.symbol}:${r.product || ''}`}
                  density="compact"
                  disableRowSelectionOnClick
                  sx={{ '& .pnl-negative': { color: 'error.main' } }}
                  initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
                  pageSizeOptions={[10]}
                />
              </Box>
            </Paper>
          </Box>

          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Open positions (current)
            </Typography>
            <Box sx={{ height: 360 }}>
              <DataGrid
                rows={analysis.open_positions}
                columns={openPositionsColumns}
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
              Recent closed trades
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <Box sx={{ height: 360 }}>
              <DataGrid
                rows={analysis.closed_trades.map((r, idx) => ({ id: idx, ...r }))}
                columns={closedTradesColumns}
                density="compact"
                disableRowSelectionOnClick
                sx={{ '& .pnl-negative': { color: 'error.main' } }}
                initialState={{ pagination: { paginationModel: { pageSize: 15 } } }}
                pageSizeOptions={[15, 30, 100]}
              />
            </Box>
          </Paper>
        </Box>
      )}
    </Box>
  )
}
