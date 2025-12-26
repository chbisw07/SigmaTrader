import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'
import { Screenshot } from '../components/Screenshot'

export function FeatureRebalancePage() {
  return (
    <Page
      title="Portfolio rebalancing"
      subtitle="Target weights, signal-driven rotation, and risk parity with explainable previews and guardrails."
    >
      <Stack spacing={2}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Methods (3 modes)
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 3, mt: 1 }}>
            {[
              'Target weights: bring live weights back to your desired allocation',
              'Signal rotation: derive targets from Top‑N strategy scores',
              'Risk parity: derive targets from equal risk contribution weights',
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
            Guardrails
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            Rebalancing can overtrade if you’re not careful. SigmaTrader’s dialog is
            built around guardrails: budget caps, drift bands, max trades, min trade value,
            and a preview-first workflow.
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 900 }}>
            Screenshot
          </Typography>
          <Screenshot
            src="/assets/screenshots/rebalance-preview.png"
            alt="Rebalance dialog preview"
            sx={{ mt: 1.5 }}
          />
          <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
            Replace file: `/assets/screenshots/rebalance-preview.png`
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Deep help
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            The in-app help is intentionally detailed so users can take confident action.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
            <Button
              component={RouterLink}
              to="/docs/rebalance-help"
              variant="contained"
              color="secondary"
              sx={{ textTransform: 'none' }}
            >
              Rebalance help
            </Button>
            <Button
              component={RouterLink}
              to="/roadmap"
              variant="outlined"
              sx={{ textTransform: 'none' }}
            >
              See roadmap
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}
