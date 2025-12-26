import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'
import { Screenshot } from '../components/Screenshot'

export function FeatureAlertsPage() {
  return (
    <Page
      title="Explainable alerts"
      subtitle="Universe-scoped alerts with readable conditions, event history, and optional actions."
    >
      <Stack spacing={2}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            What makes SigmaTrader alerts different
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            The direction is “alert as actor”: one alert runs over a universe of symbols.
            When it triggers, it emits an event with a snapshot so you can answer:
            “Why did this fire?”
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Common workflows
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 3, mt: 1 }}>
            {[
              'Attach an alert to holdings or a group',
              'Define variables (indicators/metrics) and a condition expression',
              'Choose trigger semantics (once, once per bar, every time)',
              'Review events and optionally route to an action template',
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
          <Typography variant="subtitle1" sx={{ fontWeight: 900 }}>
            Screenshot
          </Typography>
          <Screenshot src="/assets/screenshots/alerts.png" alt="Alerts UI" sx={{ mt: 1.5 }} />
          <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
            Replace file: `/assets/screenshots/alerts.png`
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Docs
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
            <Button
              component={RouterLink}
              to="/docs/alerts-v3"
              variant="contained"
              color="secondary"
              sx={{ textTransform: 'none' }}
            >
              Alerts V3 reference
            </Button>
            <Button
              component={RouterLink}
              to="/docs/alert-system-design"
              variant="outlined"
              sx={{ textTransform: 'none' }}
            >
              Expression design
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}
