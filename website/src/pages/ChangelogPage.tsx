import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import { Page } from '../components/Page'
import { CHANGELOG } from '../content/changelog'

export function ChangelogPage() {
  return (
    <Page
      title="Changelog"
      subtitle="High-level releases and major milestones (curated)."
    >
      <Stack spacing={2}>
        {CHANGELOG.map((e) => (
          <Paper key={e.date} variant="outlined" sx={{ p: 3 }}>
            <Typography variant="overline" color="text.secondary">
              {e.date}
            </Typography>
            <Typography variant="h6" sx={{ fontWeight: 900 }}>
              {e.title}
            </Typography>
            <Stack component="ul" sx={{ m: 0, pl: 3, mt: 1 }} spacing={0.5}>
              {e.bullets.map((b) => (
                <li key={b}>
                  <Typography variant="body2" color="text.secondary">
                    {b}
                  </Typography>
                </li>
              ))}
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Page>
  )
}

