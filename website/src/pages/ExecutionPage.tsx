import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'
import { Screenshot } from '../components/Screenshot'

export function ExecutionPage() {
  return (
    <Page
      title="Execution pipeline"
      subtitle="TradingView webhook ingest, manual queue, risk guardrails, and broker execution."
    >
      <Stack spacing={2}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            The idea
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            SigmaTrader is designed so you can choose how much automation you want:
            start in MANUAL mode (queue), and switch to AUTO only when you trust the
            strategy and guardrails.
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Safety guardrails
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 3, mt: 1 }}>
            {[
              'Risk settings (max order value, max qty/order, short selling policy)',
              'Clamp vs reject behavior',
              'Idempotency keys to prevent duplicate submits',
              'Optional bracket / GTT workflows',
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
          <Screenshot src="/assets/screenshots/queue.png" alt="Orders queue" sx={{ mt: 1.5 }} />
          <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
            Replace file: `/assets/screenshots/queue.png`
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Where to read more
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
            <Button
              component={RouterLink}
              to="/docs"
              variant="contained"
              color="secondary"
              sx={{ textTransform: 'none' }}
            >
              Docs hub
            </Button>
            <Button
              component={RouterLink}
              to="/help"
              variant="outlined"
              sx={{ textTransform: 'none' }}
            >
              Help search
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}
