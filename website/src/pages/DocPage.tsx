import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink, useParams } from 'react-router-dom'

import { MarkdownLite } from '../components/MarkdownLite'
import { Page } from '../components/Page'
import { getDocById } from '../content/docs'

export function DocPage() {
  const { docId } = useParams()
  const doc = docId ? getDocById(docId) : undefined

  if (!doc) {
    return (
      <Page title="Doc not found">
        <Button
          component={RouterLink}
          to="/docs"
          variant="outlined"
          sx={{ textTransform: 'none' }}
          startIcon={<ArrowBackIcon />}
        >
          Back to docs
        </Button>
      </Page>
    )
  }

  return (
    <Page title={doc.title} subtitle={doc.description}>
      <Stack spacing={2}>
        <Button
          component={RouterLink}
          to="/docs"
          variant="text"
          color="secondary"
          sx={{ textTransform: 'none', px: 0 }}
          startIcon={<ArrowBackIcon />}
        >
          Back to docs
        </Button>
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography variant="caption" color="text.secondary">
            This page is rendered from repository docs and is meant for reading and
            understanding (not a polished marketing page).
          </Typography>
          <Stack sx={{ mt: 2 }}>
            <MarkdownLite text={doc.content} />
          </Stack>
        </Paper>
      </Stack>
    </Page>
  )
}

