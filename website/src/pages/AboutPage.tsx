import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import { Page } from '../components/Page'

export function AboutPage() {
  return (
    <Page
      title="About"
      subtitle="SigmaTrader is built for personal discipline: clarity, guardrails, and explainable decisions."
    >
      <Stack spacing={2}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Why SigmaTrader exists
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            SigmaTrader started as a personal tool: a way to unify the daily workflow
            of an Indian-market trader/investor—holdings, universes, screeners, alerts,
            orders, and portfolio controls—in a single system that is explainable and
            safe by default.
          </Typography>
        </Paper>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Design principles
          </Typography>
          <Stack component="ul" sx={{ m: 0, pl: 3, mt: 1 }} spacing={0.5}>
            {[
              'Explainability first: always show “why” before “do”.',
              'Guardrails by default: budgets, bands, risk settings, idempotency.',
              'One mental model across surfaces: universe → signals → actions.',
              'Local-first: your environment, your data, your control.',
            ].map((b) => (
              <li key={b}>
                <Typography variant="body2" color="text.secondary">
                  {b}
                </Typography>
              </li>
            ))}
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}

