import Button from '@mui/material/Button'
import Tooltip from '@mui/material/Tooltip'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { Link as RouterLink } from 'react-router-dom'

export function RiskRejectedHelpLink({
  label = 'Why?',
  icon = false,
}: {
  label?: string
  icon?: boolean
}) {
  return (
    <Tooltip title="Why was this rejected?" arrow placement="top">
      <Button
        size="small"
        variant="text"
        component={RouterLink}
        to="/risk-guide#reason-codes"
        onClick={(e) => e.stopPropagation()}
        endIcon={icon ? <OpenInNewIcon fontSize="small" /> : undefined}
        sx={{ minWidth: 'auto', px: 0.75 }}
      >
        {label}
      </Button>
    </Tooltip>
  )
}

