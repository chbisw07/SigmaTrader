import AutoGraphIcon from '@mui/icons-material/AutoGraph'
import BoltIcon from '@mui/icons-material/Bolt'
import FactCheckIcon from '@mui/icons-material/FactCheck'
import SearchIcon from '@mui/icons-material/Search'
import ShieldIcon from '@mui/icons-material/Shield'
import SwapHorizIcon from '@mui/icons-material/SwapHoriz'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import Grid from '@mui/material/Grid'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { FeatureCard } from '../components/FeatureCard'
import { Screenshot } from '../components/Screenshot'

function Hero() {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: { xs: 3, md: 5 },
        background:
          'radial-gradient(800px circle at 20% 10%, rgba(45,212,191,0.25), transparent 55%), radial-gradient(900px circle at 80% 40%, rgba(34,197,94,0.18), transparent 55%)',
      }}
    >
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} flexWrap="wrap">
          <Chip size="small" label="Local-first" />
          <Chip size="small" label="Explainability-first" />
          <Chip size="small" label="Indian markets" />
          <Chip size="small" label="Zerodha today • Multi-broker ready" />
        </Stack>

        <Typography
          variant="h2"
          sx={{ fontWeight: 900, letterSpacing: -1, lineHeight: 1.05 }}
        >
          A disciplined workflow for trading and portfolio management.
        </Typography>

        <Typography variant="h6" sx={{ color: 'text.secondary', maxWidth: 920 }}>
          SigmaTrader unifies universes (holdings, watchlists, portfolios), a
          deterministic screener + DSL, explainable alerts, safe execution, and
          technical portfolio rebalancing—so you can make decisions you
          understand and stick to.
        </Typography>

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <Button
            component="a"
            href="http://localhost:5173/"
            target="_blank"
            rel="noreferrer"
            variant="contained"
            color="secondary"
            size="large"
            sx={{ textTransform: 'none' }}
          >
            Open the app
          </Button>
          <Button
            component={RouterLink}
            to="/docs"
            variant="outlined"
            size="large"
            sx={{ textTransform: 'none' }}
          >
            Read the docs
          </Button>
          <Button
            component={RouterLink}
            to="/product"
            variant="text"
            size="large"
            color="secondary"
            sx={{ textTransform: 'none' }}
          >
            See the product →
          </Button>
        </Stack>

        <Typography variant="caption" sx={{ color: 'text.secondary' }}>
          Disclaimer: SigmaTrader is a personal tool. Nothing here is investment
          advice.
        </Typography>
      </Stack>
    </Paper>
  )
}

function HowItWorks() {
  const steps = [
    {
      title: 'Build your universe',
      desc: 'Holdings, watchlists, baskets, portfolios, holdings-views.',
    },
    {
      title: 'Find & define',
      desc: 'Screen symbols using DSL and reusable signal strategies.',
    },
    {
      title: 'Monitor & trigger',
      desc: 'Alerts over universes, with explainable snapshots and history.',
    },
    {
      title: 'Execute safely',
      desc: 'Manual queue + risk guardrails, or automation when you trust it.',
    },
  ]
  return (
    <Box>
      <Typography variant="h4" sx={{ fontWeight: 900 }}>
        How it works
      </Typography>
      <Typography variant="body1" sx={{ color: 'text.secondary', mt: 1 }}>
        SigmaTrader is built around a simple loop: universe → signals → actions.
      </Typography>
      <Grid container spacing={2} sx={{ mt: 1 }}>
        {steps.map((s, idx) => (
          <Grid key={s.title} size={{ xs: 12, md: 6 }}>
            <Paper variant="outlined" sx={{ p: 2.5 }}>
              <Stack spacing={0.75}>
                <Typography variant="overline" sx={{ color: 'text.secondary' }}>
                  Step {idx + 1}
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 800 }}>
                  {s.title}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {s.desc}
                </Typography>
              </Stack>
            </Paper>
          </Grid>
        ))}
      </Grid>
    </Box>
  )
}

function FeatureGrid() {
  return (
    <Box>
      <Typography variant="h4" sx={{ fontWeight: 900 }}>
        What you get
      </Typography>
      <Typography variant="body1" sx={{ color: 'text.secondary', mt: 1 }}>
        A set of connected tools that share one mental model and one source of
        truth.
      </Typography>
      <Grid container spacing={2} sx={{ mt: 1 }}>
        <Grid size={{ xs: 12, md: 6 }}>
          <FeatureCard
            title="Unified universe viewer"
            description="One rich grid for holdings, portfolios, watchlists, baskets, and overlays."
            to="/features/universe"
            icon={<SwapHorizIcon />}
            bullets={[
              'Universe picker (holdings/groups/portfolios)',
              'Bulk actions and exports',
              'Overlays: holdings metrics on group members',
              'Consistent UX everywhere',
            ]}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <FeatureCard
            title="Screener + DSL strategies"
            description="Find symbols using a deterministic DSL and reuse the same strategy logic across the app."
            to="/features/screener"
            icon={<SearchIcon />}
            bullets={[
              'Targets: holdings + groups union',
              'Variables + DSL condition',
              'Create group from screener run',
              'Saved Signal Strategies (signals + overlays)',
            ]}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <FeatureCard
            title="Explainable alerts"
            description="Universe-scoped alert definitions with event history and clear “why it fired” reasoning."
            to="/features/alerts"
            icon={<FactCheckIcon />}
            bullets={[
              'Alerts run over universes',
              'Multi-timeframe indicator logic',
              'Audit trail of trigger events',
              'Optional action templates (order intents)',
            ]}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <FeatureCard
            title="Safe execution pipeline"
            description="Manual queue, idempotency, and risk controls before orders touch your broker."
            to="/features/execution"
            icon={<ShieldIcon />}
            bullets={[
              'TradingView webhook ingest',
              'Manual queue (review/edit/execute)',
              'Risk settings (clamp/reject)',
              'Optional bracket + GTT workflows',
            ]}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <FeatureCard
            title="Portfolio rebalancing"
            description="Target weights, signal rotation, and risk parity with previews and guardrails."
            to="/features/rebalance"
            icon={<AutoGraphIcon />}
            bullets={[
              'Budget + drift bands',
              'Signal-driven top‑N rotation',
              'Risk parity targets (ERC)',
              'History + schedule for portfolios',
            ]}
          />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <FeatureCard
            title="Multi-broker readiness"
            description="Broker-aware execution, broker-agnostic groups, and capability-driven UX."
            to="/features/brokers"
            icon={<BoltIcon />}
            bullets={[
              'Holdings/positions broker-scoped',
              'Groups are broker-agnostic',
              'Execution is always broker-bound',
              'AngelOne prework documented',
            ]}
          />
        </Grid>
      </Grid>
    </Box>
  )
}

function ScreenshotsTeaser() {
  const tiles = [
    { title: 'Universe grid', file: '/assets/screenshots/holdings-page.png' },
    { title: 'Screener', file: '/assets/screenshots/screener.png' },
    { title: 'Rebalance', file: '/assets/screenshots/rebalance-preview.png' },
    { title: 'Queue', file: '/assets/screenshots/queue.png' },
  ]
  return (
    <Box>
      <Typography variant="h4" sx={{ fontWeight: 900 }}>
        Product tour (screenshots)
      </Typography>
      <Typography variant="body1" sx={{ color: 'text.secondary', mt: 1 }}>
        Replace these placeholders with real screenshots from your running app.
      </Typography>
      <Grid container spacing={2} sx={{ mt: 1 }}>
        {tiles.map((t) => (
          <Grid key={t.title} size={{ xs: 12, md: 6 }}>
            <Paper variant="outlined" sx={{ p: 2 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 800, mb: 1 }}>
                {t.title}
              </Typography>
              <Screenshot src={t.file} alt={t.title} />
              <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
                File: {t.file}
              </Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>
    </Box>
  )
}

function TrustBlock() {
  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ fontWeight: 900 }}>
        Built for trust: explainability + guardrails
      </Typography>
      <Divider sx={{ my: 2 }} />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Stack spacing={1}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
              Explainability-first
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              SigmaTrader aims to show “why” before “do”: previews, derived targets,
              audit events, and history snapshots.
            </Typography>
          </Stack>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Stack spacing={1}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800 }}>
              Safety by default
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Budgets, drift bands, trade caps, idempotency keys, and risk settings
              reduce accidental over-trading and mistakes.
            </Typography>
          </Stack>
        </Grid>
      </Grid>
    </Paper>
  )
}

export function HomePage() {
  return (
    <Stack spacing={6}>
      <Hero />
      <HowItWorks />
      <FeatureGrid />
      <TrustBlock />
      <ScreenshotsTeaser />
    </Stack>
  )
}
