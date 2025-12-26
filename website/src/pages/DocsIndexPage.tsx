import Chip from '@mui/material/Chip'
import Grid from '@mui/material/Grid'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'
import { DOCS } from '../content/docs'

export function DocsIndexPage() {
  return (
    <Page
      title="Docs"
      subtitle="Curated docs from the SigmaTrader repository: concepts, design notes, and how-to guides."
    >
      <Grid container spacing={2}>
        {DOCS.map((d) => (
          <Grid key={d.id} size={{ xs: 12, md: 6 }}>
            <Paper
              variant="outlined"
              component={RouterLink}
              to={`/docs/${d.id}`}
              sx={{
                p: 3,
                display: 'block',
                textDecoration: 'none',
                color: 'inherit',
                height: '100%',
                '&:hover': { borderColor: 'rgba(34,197,94,0.5)' },
              }}
            >
              <Stack spacing={1}>
                <Typography variant="h6" sx={{ fontWeight: 900 }}>
                  {d.title}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {d.description}
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  {d.tags.slice(0, 6).map((t) => (
                    <Chip key={t} size="small" label={t} sx={{ mt: 1 }} />
                  ))}
                </Stack>
              </Stack>
            </Paper>
          </Grid>
        ))}
      </Grid>
    </Page>
  )
}
