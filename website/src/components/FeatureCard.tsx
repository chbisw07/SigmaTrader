import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { Link as RouterLink } from 'react-router-dom'

export function FeatureCard({
  title,
  description,
  to,
  bullets,
  icon,
}: {
  title: string
  description: string
  to: string
  bullets: string[]
  icon?: React.ReactNode
}) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 3,
        height: '100%',
        background:
          'linear-gradient(180deg, rgba(45,212,191,0.08), rgba(34,197,94,0.02))',
      }}
    >
      <Stack spacing={1.5}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {icon}
          <Typography variant="h6" sx={{ fontWeight: 800 }}>
            {title}
          </Typography>
        </Box>
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {description}
        </Typography>
        <Box component="ul" sx={{ m: 0, pl: 3 }}>
          {bullets.slice(0, 4).map((b) => (
            <li key={b}>
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {b}
              </Typography>
            </li>
          ))}
        </Box>
        <Box>
          <Button
            component={RouterLink}
            to={to}
            variant="text"
            color="secondary"
            sx={{ textTransform: 'none', px: 0 }}
          >
            Learn more →
          </Button>
        </Box>
      </Stack>
    </Paper>
  )
}

