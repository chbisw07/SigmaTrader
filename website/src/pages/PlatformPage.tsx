import Box from '@mui/material/Box'
import Divider from '@mui/material/Divider'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import { Page } from '../components/Page'

export function PlatformPage() {
  return (
    <Page
      title="Platform"
      subtitle="How SigmaTrader is built: local-first, deterministic, explainable, and broker-aware."
    >
      <Stack spacing={2}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Local-first by default
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            SigmaTrader is designed to run on your machine. It stores its state
            locally (database, configurations, history), and talks to brokers from
            your environment. This makes behavior debuggable and reduces hidden
            “cloud magic”.
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Deterministic DSL (no arbitrary code)
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            SigmaTrader’s DSL is intentionally restricted to a safe, deterministic
            set of functions (OHLCV primitives + indicators + helpers). This keeps
            screening and alerting behavior consistent and explainable.
          </Typography>
          <Divider sx={{ my: 2 }} />
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Recommendation: treat DSL strategies as reusable “recipes” and keep
            them versioned/pinned for auditability.
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Explainability and auditability
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            A trading system is only useful if you can trust it. SigmaTrader
            prioritizes:
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 3, mt: 1 }}>
            {[
              'Preview-first workflows (before orders are created)',
              'Run history (rebalance) and event history (alerts)',
              'Explicit guardrails: budgets, bands, max trades, min trade value',
              'Idempotency keys to prevent accidental duplicates',
            ].map((b) => (
              <li key={b}>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {b}
                </Typography>
              </li>
            ))}
          </Box>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Broker-aware, capability-driven
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            SigmaTrader treats execution as broker-bound, but keeps universes
            broker-agnostic. That means:
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 3, mt: 1 }}>
            {[
              'Holdings/positions/orders are broker-scoped views',
              'Groups/watchlists/portfolios are your universe model (symbol+exchange)',
              'Features like GTT and margin preview are modeled as broker capabilities',
            ].map((b) => (
              <li key={b}>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {b}
                </Typography>
              </li>
            ))}
          </Box>
        </Paper>
      </Stack>
    </Page>
  )
}

