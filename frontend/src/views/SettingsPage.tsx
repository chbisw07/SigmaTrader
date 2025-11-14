import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'

export function SettingsPage() {
  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Settings
      </Typography>
      <Typography color="text.secondary">
        Execution modes, risk limits, and broker connection settings will live here.
      </Typography>
    </Box>
  )
}
