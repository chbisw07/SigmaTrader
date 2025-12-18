import { useEffect, useMemo, useRef } from 'react'
import { useTheme } from '@mui/material/styles'
import Box from '@mui/material/Box'

import {
  ColorType,
  CrosshairMode,
  createChart,
  type BusinessDay,
  type IChartApi,
  type LineData,
  type LineSeriesPartialOptions,
  type LineWidth,
  type Time,
} from 'lightweight-charts'

export type PriceChartType = 'line' | 'candles'

export type PriceCandle = {
  ts: string // YYYY-MM-DD
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type PriceOverlayPoint = {
  ts: string // YYYY-MM-DD
  value: number | null
}

export type PriceOverlay = {
  name: string
  color?: string
  lineWidth?: number
  points: PriceOverlayPoint[]
}

export type PriceSignalMarker = {
  ts: string // YYYY-MM-DD
  kind: string
  text?: string | null
}

function toBusinessDay(dateIso: string): BusinessDay {
  const [y, m, d] = dateIso.split('-').map((v) => Number(v))
  return { year: y!, month: m!, day: d! }
}

export function PriceChart({
  candles,
  chartType,
  overlays = [],
  markers = [],
  height = 320,
}: {
  candles: PriceCandle[]
  chartType: PriceChartType
  overlays?: PriceOverlay[]
  markers?: PriceSignalMarker[]
  height?: number
}) {
  const theme = useTheme()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const overlaySeriesRefs = useRef<any[]>([])

  const normalizedCandles = useMemo(() => {
    if (!candles || candles.length === 0) return []
    const byDate = new Map<string, PriceCandle>()
    for (const c of candles) {
      if (!c?.ts) continue
      byDate.set(c.ts, c) // last write wins
    }
    return Array.from(byDate.values()).sort((a, b) => a.ts.localeCompare(b.ts))
  }, [candles])

  const upColor = theme.palette.mode === 'dark' ? '#22c55e' : '#16a34a'
  const downColor = theme.palette.mode === 'dark' ? '#ef4444' : '#dc2626'
  const lineColor = theme.palette.primary.main

  const seriesData = useMemo(() => {
    if (normalizedCandles.length === 0) return []
    if (chartType === 'line') {
      return normalizedCandles.map(
        (c) =>
          ({
            time: toBusinessDay(c.ts) as unknown as Time,
            value: c.close,
          }) satisfies LineData,
      )
    }
    return normalizedCandles.map((c) => ({
      time: toBusinessDay(c.ts) as unknown as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))
  }, [normalizedCandles, chartType])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: theme.palette.text.secondary,
        fontFamily: theme.typography.fontFamily,
      },
      grid: {
        vertLines: { color: 'transparent' },
        horzLines: {
          color:
            theme.palette.mode === 'dark'
              ? 'rgba(255,255,255,0.08)'
              : 'rgba(0,0,0,0.06)',
        },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: { borderColor: 'transparent' },
      timeScale: { borderColor: 'transparent', timeVisible: true },
    })

    chartRef.current = chart
    seriesRef.current = null

    const resizeObserver = new ResizeObserver(() => {
      chart.timeScale().fitContent()
    })
    resizeObserver.observe(el)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      overlaySeriesRefs.current = []
    }
  }, [theme])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    for (const s of overlaySeriesRefs.current) chart.removeSeries(s)
    overlaySeriesRefs.current = []

    if (seriesRef.current) {
      chart.removeSeries(seriesRef.current)
      seriesRef.current = null
    }

    if (chartType === 'line') {
      const series = chart.addLineSeries({
        color: lineColor,
        lineWidth: 2,
      })
      seriesRef.current = series
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      series.setData(seriesData as any)
    } else {
      const series = chart.addCandlestickSeries({
        upColor,
        downColor,
        borderVisible: false,
        wickUpColor: upColor,
        wickDownColor: downColor,
      })
      seriesRef.current = series
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      series.setData(seriesData as any)
    }

    chart.timeScale().fitContent()
  }, [chartType, seriesData, lineColor, upColor, downColor])

  const normalizedOverlays = useMemo(() => {
    return (overlays ?? [])
      .map((o) => {
        const byDate = new Map<string, number>()
        for (const p of o.points ?? []) {
          if (!p?.ts) continue
          if (p.value == null || !Number.isFinite(p.value)) continue
          byDate.set(p.ts, p.value)
        }
        const data = Array.from(byDate.entries())
          .sort((a, b) => a[0].localeCompare(b[0]))
          .map(([ts, value]) => ({
            time: toBusinessDay(ts) as unknown as Time,
            value,
          }))
        return { ...o, data }
      })
      .filter((o) => o.data.length > 0)
  }, [overlays])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    // Clear existing overlays.
    for (const s of overlaySeriesRefs.current) chart.removeSeries(s)
    overlaySeriesRefs.current = []

    const palette = [
      theme.palette.warning.main,
      theme.palette.success.main,
      theme.palette.info.main,
      theme.palette.secondary.main,
    ]

    normalizedOverlays.forEach((o, idx) => {
      const lineWidth = Math.min(4, Math.max(1, Math.round(o.lineWidth ?? 2))) as LineWidth
      const opts: LineSeriesPartialOptions = {
        color: o.color || palette[idx % palette.length]!,
        lineWidth,
        priceLineVisible: false,
        lastValueVisible: false,
      }
      const s = chart.addLineSeries(opts)
      overlaySeriesRefs.current.push(s)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      s.setData(o.data as any)
    })
  }, [normalizedOverlays, theme])

  useEffect(() => {
    if (!seriesRef.current) return
    const baseSeries = seriesRef.current

    const markerData = (markers ?? [])
      .filter((m) => m?.ts)
      .map((m) => {
        const kind = String(m.kind || '').toUpperCase()
        const isCrossUp = kind === 'CROSSOVER'
        const isCrossDown = kind === 'CROSSUNDER'
        const isTrue = kind === 'TRUE'
        return {
          time: toBusinessDay(m.ts) as unknown as Time,
          position: isCrossDown ? 'aboveBar' : 'belowBar',
          color: isCrossUp
            ? theme.palette.success.main
            : isCrossDown
              ? theme.palette.error.main
              : theme.palette.primary.main,
          shape: isCrossUp ? 'arrowUp' : isCrossDown ? 'arrowDown' : isTrue ? 'circle' : 'circle',
          text: m.text ? String(m.text) : undefined,
        }
      })
      .sort((a, b) => {
        // Sort by YYYY-MM-DD.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const ta = (a.time as any) as { year: number; month: number; day: number }
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const tb = (b.time as any) as { year: number; month: number; day: number }
        const sa = `${ta.year}-${String(ta.month).padStart(2, '0')}-${String(ta.day).padStart(2, '0')}`
        const sb = `${tb.year}-${String(tb.month).padStart(2, '0')}-${String(tb.day).padStart(2, '0')}`
        return sa.localeCompare(sb)
      })

    try {
      baseSeries.setMarkers(markerData)
    } catch {
      // ignore marker failures (e.g. series type not supporting markers)
    }
  }, [markers, theme])

  return (
    <Box
      ref={containerRef}
      sx={{
        height,
        width: '100%',
        '& canvas': { borderRadius: 1 },
      }}
    />
  )
}
