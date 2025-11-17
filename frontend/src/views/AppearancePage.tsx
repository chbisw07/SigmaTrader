import Box from '@mui/material/Box'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import FormLabel from '@mui/material/FormLabel'
import Paper from '@mui/material/Paper'
import Radio from '@mui/material/Radio'
import RadioGroup from '@mui/material/RadioGroup'
import Typography from '@mui/material/Typography'
import { useState } from 'react'

import { updateTheme } from '../services/auth'
import { type ThemeId, THEME_IDS } from '../theme'
import { useAppTheme } from '../themeContext'

const THEME_LABELS: Record<ThemeId, string> = {
  dark: 'Dark (default)',
  light: 'Light',
  amber: 'Dark (amber accent)',
}

export function AppearancePage() {
  const { themeId, setThemeId } = useAppTheme()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleChange = async (value: ThemeId) => {
    setThemeId(value)
    setSaving(true)
    setError(null)
    try {
      await updateTheme(value)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to save theme preference',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Appearance
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Choose your preferred theme for SigmaTrader. This setting is saved per
        user and also remembered on this device.
      </Typography>

      <Paper sx={{ p: 2, maxWidth: 480 }}>
        <FormControl component="fieldset" fullWidth>
          <FormLabel component="legend">Theme</FormLabel>
          <RadioGroup
            value={themeId}
            onChange={(e) => handleChange(e.target.value as ThemeId)}
          >
            {THEME_IDS.map((id) => (
              <FormControlLabel
                key={id}
                value={id}
                control={<Radio />}
                label={THEME_LABELS[id]}
              />
            ))}
          </RadioGroup>
        </FormControl>
        {saving && (
          <Typography variant="caption" color="text.secondary">
            Saving theme preference...
          </Typography>
        )}
        {error && (
          <Typography variant="caption" color="error" display="block">
            {error}
          </Typography>
        )}
      </Paper>
    </Box>
  )
}

