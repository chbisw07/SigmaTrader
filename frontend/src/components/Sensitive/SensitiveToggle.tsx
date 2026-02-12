import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import Typography from '@mui/material/Typography'
import VisibilityIcon from '@mui/icons-material/Visibility'
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff'
import type { ReactNode } from 'react'

export function SensitiveToggle({
  label,
  visible,
  onToggle,
  ariaLabel,
}: {
  label: ReactNode
  visible: boolean
  onToggle: () => void
  ariaLabel: string
}) {
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, minWidth: 0 }}>
      <Typography component="span" sx={{ minWidth: 0 }}>
        {label}
      </Typography>
      <IconButton size="small" onClick={onToggle} aria-label={ariaLabel}>
        {visible ? <VisibilityIcon fontSize="small" /> : <VisibilityOffIcon fontSize="small" />}
      </IconButton>
    </Box>
  )
}

