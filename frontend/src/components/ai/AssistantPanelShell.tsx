import { useMemo, useState } from 'react'
import Drawer from '@mui/material/Drawer'
import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import Typography from '@mui/material/Typography'
import Tooltip from '@mui/material/Tooltip'
import Divider from '@mui/material/Divider'
import ChatIcon from '@mui/icons-material/Chat'

import { AssistantPanel } from './AssistantPanel'

export function AssistantPanelShell() {
  const [open, setOpen] = useState(true)
  const width = useMemo(() => 380, [])

  return (
    <>
      <Tooltip title={open ? 'Hide assistant' : 'Show assistant'}>
        <IconButton
          onClick={() => setOpen((p) => !p)}
          size="small"
          sx={{
            position: 'fixed',
            right: 12,
            bottom: 12,
            zIndex: (theme) => theme.zIndex.drawer + 2,
            bgcolor: 'background.paper',
            border: 1,
            borderColor: 'divider',
            '&:hover': { bgcolor: 'action.hover' },
          }}
          aria-label="Toggle assistant panel"
        >
          <ChatIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Drawer
        anchor="right"
        variant="persistent"
        open={open}
        sx={{
          '& .MuiDrawer-paper': {
            width,
            boxSizing: 'border-box',
            top: { xs: 56, sm: 64 },
            height: { xs: 'calc(100% - 56px)', sm: 'calc(100% - 64px)' },
          },
        }}
      >
        <Box sx={{ px: 2, py: 1.5 }}>
          <Typography variant="subtitle1">AI Trading Manager</Typography>
          <Typography variant="caption" color="text.secondary">
            Phase 0 (stub)
          </Typography>
        </Box>
        <Divider />
        <AssistantPanel />
      </Drawer>
    </>
  )
}

