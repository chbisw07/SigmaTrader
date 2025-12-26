import CheckIcon from '@mui/icons-material/Check'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import Grid from '@mui/material/Grid'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'

function Pillar({
  title,
  desc,
  bullets,
  to,
}: {
  title: string
  desc: string
  bullets: string[]
  to: string
}) {
  return (
    <Paper variant="outlined" sx={{ p: 3, height: '100%' }}>
      <Stack spacing={1.5}>
        <Typography variant="h6" sx={{ fontWeight: 900 }}>
          {title}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {desc}
        </Typography>
        <Box>
          {bullets.map((b) => (
            <Box
              key={b}
              sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', mb: 0.75 }}
            >
              <CheckIcon fontSize="small" color="secondary" />
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {b}
              </Typography>
            </Box>
          ))}
        </Box>
        <Box>
          <Button
            component={RouterLink}
            to={to}
            variant="text"
            color="secondary"
            sx={{ textTransform: 'none', px: 0 }}
          >
            Learn more →
          </Button>
        </Box>
      </Stack>
    </Paper>
  )
}

export function ProductPage() {
  return (
    <Page
      title="Product"
      subtitle="SigmaTrader is a connected set of tools that share one mental model: universe → signals → actions → audit."
    >
      <Stack spacing={4}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h5" sx={{ fontWeight: 900 }}>
            The workflow
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            SigmaTrader is most useful when you treat it as a repeatable pipeline,
            not a collection of screens.
          </Typography>
          <Divider sx={{ my: 2 }} />
          <Grid container spacing={2}>
            {[
              ['Universe', 'Holdings, portfolios, watchlists, baskets'],
              ['Screener + DSL', 'Find candidates, define reusable signals'],
              ['Alerts', 'Monitor universes; produce explainable events'],
              ['Execution', 'Queue + risk guardrails + broker execution'],
            ].map(([k, v]) => (
              <Grid key={k} size={{ xs: 12, md: 6 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 900 }}>
                  {k}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {v}
                </Typography>
              </Grid>
            ))}
          </Grid>
        </Paper>

        <Box>
          <Typography variant="h5" sx={{ fontWeight: 900 }}>
            Core pillars
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            Each pillar is useful on its own; together they form a disciplined
            system.
          </Typography>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid size={{ xs: 12, md: 6 }}>
              <Pillar
                title="Unified universe viewer"
                desc="One grid experience across holdings and groups, with overlays and consistent bulk actions."
                to="/features/universe"
                bullets={[
                  'Holdings (broker-scoped) and groups (broker-agnostic)',
                  'Overlays: holdings metrics on group members',
                  'Bulk actions: buy/sell, group creation, exports',
                ]}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Pillar
                title="Screener + DSL strategies"
                desc="A deterministic indicator-first DSL with reusable strategy outputs."
                to="/features/screener"
                bullets={[
                  'Targets: holdings + groups union',
                  'Variables + condition DSL',
                  'Saved Signal Strategies (signals + overlays)',
                ]}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Pillar
                title="Alerts (universe-scoped)"
                desc="Alerts over universes with explainable event history and optional action templates."
                to="/features/alerts"
                bullets={[
                  'Multi-timeframe indicators, events, boolean logic',
                  'Explainable “why it triggered” snapshot',
                  'Audit trail for trust and debugging',
                ]}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Pillar
                title="Execution + risk"
                desc="Manual queue and risk guardrails that keep execution under your control."
                to="/features/execution"
                bullets={[
                  'TradingView webhook ingest',
                  'Manual queue review/edit/execute',
                  'Risk settings (clamp/reject, short selling policy)',
                ]}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Pillar
                title="Portfolio rebalancing"
                desc="Technical portfolio tools: target weights, rotation, and risk parity, with guardrails."
                to="/features/rebalance"
                bullets={[
                  'Preview trades with drift and budgets',
                  'Signal rotation (Top-N) and filters',
                  'Risk parity (equal risk contribution)',
                ]}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <Pillar
                title="Multi-broker direction"
                desc="Broker-aware execution while keeping the universe model broker-agnostic."
                to="/features/brokers"
                bullets={[
                  'Holdings/positions/orders are broker-scoped',
                  'Groups remain broker-agnostic',
                  'Capabilities-driven UI (GTT, previews, etc.)',
                ]}
              />
            </Grid>
          </Grid>
        </Box>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Next step
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            If you are using SigmaTrader locally, the best way to evaluate it is
            to start with the docs and then validate each module on your own data.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
            <Button
              component={RouterLink}
              to="/docs"
              variant="contained"
              color="secondary"
              sx={{ textTransform: 'none' }}
            >
              Open docs
            </Button>
            <Button
              component={RouterLink}
              to="/help"
              variant="outlined"
              sx={{ textTransform: 'none' }}
            >
              Ask the help search
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}
