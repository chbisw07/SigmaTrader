import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'
import { Screenshot } from '../components/Screenshot'

export function FeatureUniversePage() {
  return (
    <Page
      title="Unified universe viewer"
      subtitle="One grid experience across holdings, watchlists, baskets, portfolios, and overlays."
    >
      <Stack spacing={2}>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            The problem
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
            Most tools split your view across “holdings”, “watchlists”, “model
            portfolio”, and “ideas”. SigmaTrader’s direction is to treat them all
            as a universe of symbols—then add overlays (holdings metrics, target
            weights, notes) consistently.
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            What you can do
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 3, mt: 1 }}>
            {[
              'Pick a universe: holdings, group, portfolio, holdings-view',
              'Use one grid with consistent columns, filters, and selection',
              'Apply bulk actions (buy/sell, create group, export)',
              'Use overlays: show holdings metrics on group members',
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
          <Screenshot
            src="/assets/screenshots/holdings-page.png"
            alt="Universe grid (holdings page)"
            sx={{ mt: 1.5 }}
          />
          <Typography variant="caption" sx={{ color: 'text.secondary', mt: 1, display: 'block' }}>
            Replace file: `/assets/screenshots/holdings-page.png`
          </Typography>
        </Paper>

        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 900 }}>
            Read the underlying design docs
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
            <Button
              component={RouterLink}
              to="/docs/universe"
              variant="contained"
              color="secondary"
              sx={{ textTransform: 'none' }}
            >
              Universe model docs
            </Button>
            <Button
              component={RouterLink}
              to="/docs/groups-universe"
              variant="outlined"
              sx={{ textTransform: 'none' }}
            >
              Groups & universe design
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}
