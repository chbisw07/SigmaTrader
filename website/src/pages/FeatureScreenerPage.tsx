import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'
import { Screenshot } from '../components/Screenshot'

export function FeatureScreenerPage() {
  return (
    <Page
      title="Screener + DSL strategies"
      subtitle="Screen symbols using a deterministic DSL, reuse signals across Screener, Alerts, and Dashboard."
    >
      <Stack spacing={2}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            The mental model
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            A screener is a query over a universe. In SigmaTrader, you pick targets
            (holdings and/or groups), define variables and a DSL condition, run it,
            and get results you can act on (save the run, create a group, attach alerts).
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Why the DSL matters
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            The same DSL compiler/evaluator is intended to power screener conditions,
            alert conditions, and dashboard signal visualization. This reduces duplicated
            logic and makes results consistent across surfaces.
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 900 }}>
            Screenshot
          </Typography>
          <Screenshot src="/assets/screenshots/screener.png" alt="Screener page" sx={{ mt: 1.5 }} />
          <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
            Replace file: `/assets/screenshots/screener.png`
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Docs
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
            <Button
              component={RouterLink}
              to="/docs/screener"
              variant="contained"
              color="secondary"
              sx={{ textTransform: 'none' }}
            >
              Screener docs
            </Button>
            <Button
              component={RouterLink}
              to="/docs/dsl-improvement"
              variant="outlined"
              sx={{ textTransform: 'none' }}
            >
              DSL mental model
            </Button>
            <Button
              component={RouterLink}
              to="/docs/strategy-saving"
              variant="outlined"
              sx={{ textTransform: 'none' }}
            >
              Strategy saving
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}
