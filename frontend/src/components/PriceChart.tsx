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

function toBusinessDay(dateIso: string): BusinessDay {
  const [y, m, d] = dateIso.split('-').map((v) => Number(v))
  return { year: y!, month: m!, day: d! }
}

export function PriceChart({
  candles,
  chartType,
  height = 320,
}: {
  candles: PriceCandle[]
  chartType: PriceChartType
  height?: number
}) {
  const theme = useTheme()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<IChartApi | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null)

  const upColor = theme.palette.mode === 'dark' ? '#22c55e' : '#16a34a'
  const downColor = theme.palette.mode === 'dark' ? '#ef4444' : '#dc2626'
  const lineColor = theme.palette.primary.main

  const seriesData = useMemo(() => {
    if (candles.length === 0) return []
    if (chartType === 'line') {
      return candles.map(
        (c) =>
          ({
            time: toBusinessDay(c.ts) as unknown as Time,
            value: c.close,
          }) satisfies LineData,
      )
    }
    return candles.map((c) => ({
      time: toBusinessDay(c.ts) as unknown as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))
  }, [candles, chartType])

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
    }
  }, [theme])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

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
