import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Divider from '@mui/material/Divider'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import { useMemo, useState } from 'react'

import {
  ALERT_V3_METRICS,
  ALERT_V3_SOURCES,
  ALERT_V3_TIMEFRAMES,
} from '../services/alertsV3Constants'

export type DslHelpContext = 'alerts' | 'screener' | 'dashboard'

export function DslHelpDialog({
  open,
  onClose,
  context,
}: {
  open: boolean
  onClose: () => void
  context: DslHelpContext
}) {
  const [tab, setTab] = useState(0)

  const title = useMemo(() => {
    if (context === 'alerts') return 'Alert DSL help'
    if (context === 'screener') return 'Screener DSL help'
    return 'Dashboard DSL help'
  }, [context])

  const contextNotes = useMemo(() => {
    if (context === 'alerts') {
      return [
        'Evaluation: the condition is checked on the latest bar at trigger time.',
        'Tip: for holdings day-change style filters, prefer TODAY_PNL_PCT over RET(close,"1d").',
      ]
    }
    if (context === 'screener') {
      return [
        'Evaluation: “latest-only” per symbol (fast filtering).',
        'Tip: enable “Show variable values” to add columns for variables (including inline NAME = expr definitions).',
        'Shortcut: Ctrl+Enter runs the screener in the DSL editor.',
      ]
    }
    return [
      'Evaluation: “full-series” for chart overlays/markers; signals are rendered as markers.',
      'Shortcut: Ctrl+Enter runs DSL signals.',
    ]
  }, [context])

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label="Syntax" />
          <Tab label="Functions" />
          <Tab label="Metrics" />
          <Tab label="Examples" />
        </Tabs>

        {tab === 0 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Keywords and function names are case-insensitive. Parentheses are supported.
            </Typography>

            <Box>
              <Typography variant="subtitle2">Basics</Typography>
              <Typography variant="body2" component="div">
                - Logical: <code>AND</code>, <code>OR</code>, <code>NOT</code>
                <br />
                - Comparisons: <code>&gt;</code>, <code>&gt;=</code>, <code>&lt;</code>,{' '}
                <code>&lt;=</code>, <code>==</code>, <code>!=</code>
                <br />
                - Arithmetic: <code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle2">Event operators</Typography>
              <Typography variant="body2" component="div">
                - <code>A CROSSES_ABOVE B</code> / <code>A CROSSES_BELOW B</code>
                <br />
                - Aliases: <code>CROSSING_ABOVE</code>, <code>CROSSING_BELOW</code>
                <br />
                - <code>A MOVING_UP N</code> / <code>A MOVING_DOWN N</code> (N is numeric-only)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                CROSSES_* uses previous bar vs current bar. MOVING_* checks percent change from
                previous bar to current bar against N.
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle2">Inline variables</Typography>
              <Typography variant="body2" component="div">
                - Define reusable expressions with <code>NAME = expr</code>
                <br />
                - Variable names must be valid identifiers (example: <code>RSI_1D_14</code>)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                In multi-line DSL, put assignments at the top and write the condition below.
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle2">Comments</Typography>
              <Typography variant="body2" component="div">
                - Line comments: <code>// comment</code> or <code># comment</code>
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle2">BETWEEN</Typography>
              <Typography variant="body2" component="div">
                - <code>X BETWEEN A AND B</code> is equivalent to{' '}
                <code>(X &gt;= A AND X &lt;= B)</code>
              </Typography>
            </Box>

            <Divider />

            <Box>
              <Typography variant="subtitle2">Context notes</Typography>
              <Typography variant="body2" component="div" color="text.secondary">
                {contextNotes.map((line) => (
                  <div key={line}>- {line}</div>
                ))}
              </Typography>
            </Box>

            <Typography variant="body2" color="text.secondary">
              Missing data (no candle history / metric not available) evaluates to “no match”.
            </Typography>
          </Box>
        )}

        {tab === 1 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Sources: use{' '}
              {ALERT_V3_SOURCES.map((s) => (
                <span key={s}>
                  <code>{s}</code>{' '}
                </span>
              ))}
              and <code>hlc3</code>. Timeframes can be written as <code>1d</code> or quoted (
              <code>&quot;1d&quot;</code>).
            </Typography>

            <Box>
              <Typography variant="subtitle2">OHLCV / price</Typography>
              <Typography variant="body2" component="div">
                - <code>OPEN(tf)</code>, <code>HIGH(tf)</code>, <code>LOW(tf)</code>,{' '}
                <code>CLOSE(tf)</code>, <code>VOLUME(tf)</code>
                <br />
                - <code>PRICE(tf)</code> (same as <code>CLOSE(tf)</code>)
                <br />
                - <code>PRICE(source, tf)</code> where source is open/high/low/close
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle2">Indicators</Typography>
              <Typography variant="body2" component="div">
                - <code>SMA(series, len, tf?)</code> (tf defaults to 1d)
                <br />
                - <code>EMA(series, len, tf?)</code> (tf defaults to 1d)
                <br />
                - <code>RSI(series, len, tf?)</code> (tf defaults to 1d)
                <br />
                - <code>STDDEV(series, len, tf?)</code> (tf defaults to 1d)
                <br />
                - <code>ATR(len, tf)</code>
                <br />
                - <code>RET(series, tf)</code> (percent return over the latest completed bar)
                <br />
                - <code>ROC(series, len)</code> (percent change over N bars)
                <br />
                - <code>OBV(price, volume, tf?)</code>
                <br />
                - <code>VWAP(price, volume, tf?)</code> (use <code>hlc3</code> as a common price input)
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Multi-period returns: prefer <code>ROC(close, 14)</code> (14 trading days) or{' '}
                <code>ROC(close, 126)</code> (~6 months). Common lengths: 5 (1W), 21 (1M), 63 (3M),
                126 (6M), 252 (1Y).
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle2">Custom indicators</Typography>
              <Typography variant="body2" color="text.secondary">
                Any enabled custom indicator can be called like a function: <code>MY_IND(arg1, arg2)</code>.
                Argument count must match the indicator’s parameter list.
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle2">Supported timeframes</Typography>
              <Typography variant="body2" color="text.secondary">
                {ALERT_V3_TIMEFRAMES.join(', ')} (weekly candles are resampled from daily data).
              </Typography>
            </Box>

            <Box>
              <Typography variant="subtitle2">Boundary</Typography>
              <Typography variant="body2" color="text.secondary">
                The DSL is intentionally limited (no loops, no recursion, no indexing, no if/else).
              </Typography>
            </Box>
          </Box>
        )}

        {tab === 2 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Metrics are per-symbol values derived from holdings + daily candles. They can be used
              directly in conditions or assigned to variables.
            </Typography>
            <Typography variant="body2">
              {ALERT_V3_METRICS.map((m) => (
                <span key={m}>
                  <code>{m}</code>{' '}
                </span>
              ))}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Example: <code>TODAY_PNL_PCT &gt; 5</code>
            </Typography>
          </Box>
        )}

        {tab === 3 && (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Typography variant="subtitle2">Common</Typography>
            <Typography variant="body2" component="div">
              <code>TODAY_PNL_PCT &gt; 5</code>
              <br />
              <code>RSI(close, 14, 1h) &lt; 30 AND TODAY_PNL_PCT &gt; 5</code>
            </Typography>

            <Typography variant="subtitle2">Crossing / moving</Typography>
            <Typography variant="body2" component="div">
              <code>SMA(close, 20, 1d) CROSSES_ABOVE SMA(close, 50, 1d)</code>
              <br />
              <code>PRICE(1d) MOVING_UP 2</code>
            </Typography>

            <Typography variant="subtitle2">Inline variables + BETWEEN + comments</Typography>
            <Typography variant="body2" component="pre" sx={{ m: 0, whiteSpace: 'pre-wrap' }}>
{`RET_1D = RET(close, "1d")
VOL_1D = VOLUME("1d")
VOL_20D = SMA(VOLUME("1d"), 20, "1d")
RSI_14 = RSI(close, 14, "1d")
SMA_20 = SMA(close, 20, "1d")
SMA_50 = SMA(close, 50, "1d")

// Momentum + volume + trend filter
RET_1D > 5
AND VOL_1D > 2 * VOL_20D
AND SMA_20 > SMA_50
AND RSI_14 BETWEEN 50 AND 80`}
            </Typography>

            <Typography variant="body2" color="text.secondary">
              Note: <code>RET(close,&quot;1d&quot;)</code> uses candle closes (latest completed daily bar).
              Broker “day change” can differ during market hours; use <code>TODAY_PNL_PCT</code> for holdings-style day change filters.
            </Typography>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}

