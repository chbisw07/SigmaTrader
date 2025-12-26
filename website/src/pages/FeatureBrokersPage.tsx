import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'
import { Screenshot } from '../components/Screenshot'

export function FeatureBrokersPage() {
  return (
    <Page
      title="Multi-broker (broker-aware)"
      subtitle="Broker-aware execution, broker-scoped holdings/positions, broker-agnostic groups/universes."
    >
      <Stack spacing={2}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Why this matters
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            In Indian retail workflows it’s common to have one broker, but being broker-aware
            helps you keep the model clean: universes are about symbols; execution is about a broker.
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            The capability model
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 3, mt: 1 }}>
            {[
              'Holdings are broker-scoped views (Zerodha, AngelOne, …)',
              'Groups/watchlists/portfolios are broker-agnostic universes',
              'Execution is always broker-bound (no “both brokers” ambiguity)',
              'UI shows/hides features per broker capabilities (GTT, preview, margins)',
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
          <Screenshot src="/assets/screenshots/brokers.png" alt="Broker settings" sx={{ mt: 1.5 }} />
          <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
            Replace file: `/assets/screenshots/brokers.png`
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Docs
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
            <Button
              component={RouterLink}
              to="/docs/multi-broker"
              variant="contained"
              color="secondary"
              sx={{ textTransform: 'none' }}
            >
              Multi-broker prework
            </Button>
            <Button
              component={RouterLink}
              to="/platform"
              variant="outlined"
              sx={{ textTransform: 'none' }}
            >
              Platform principles
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}
