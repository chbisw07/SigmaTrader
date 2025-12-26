import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'

export function NotFoundPage() {
  return (
    <Page title="Not found" subtitle="This page does not exist.">
      <Stack spacing={2}>
        <Button
          component={RouterLink}
          to="/"
          variant="contained"
          color="secondary"
          sx={{ textTransform: 'none', width: 'fit-content' }}
        >
          Go home
        </Button>
        <Typography color="text.secondary">
          If you expected this page, add it to the website routes.
        </Typography>
      </Stack>
    </Page>
  )
}

