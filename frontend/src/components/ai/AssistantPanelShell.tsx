import { useMemo, useState } from 'react'
import Drawer from '@mui/material/Drawer'
import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import Typography from '@mui/material/Typography'
import Tooltip from '@mui/material/Tooltip'
import Divider from '@mui/material/Divider'
import ChatIcon from '@mui/icons-material/Chat'
import CloseIcon from '@mui/icons-material/Close'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import { useNavigate } from 'react-router-dom'

import { AssistantPanel } from './AssistantPanel'

export function AssistantPanelShell() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(true)
  const [minimized, setMinimized] = useState(false)
  const width = useMemo(() => 440, [])

  const height = useMemo(
    () =>
      minimized
        ? (72 as const)
        : ({
            // top offset (app bar + padding) + bottom padding
            xs: 'calc(100vh - 80px)', // (56 + 12) + 12
            sm: 'calc(100vh - 88px)', // (64 + 12) + 12
          } as const),
    [minimized],
  )

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
            // slightly shorter than full height to avoid a cramped look
            top: { xs: 56 + 12, sm: 64 + 12 },
            bottom: minimized ? 'auto' : 12,
            height,
            right: 12,
            borderRadius: 2,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          },
        }}
      >
        <Box sx={{ px: 2, py: 1.25, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" noWrap>
              AI Trading Manager
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              Phase 3 (proto)
            </Typography>
          </Box>
          <Stack direction="row" spacing={0.5} alignItems="center">
            <Button
              size="small"
              variant="text"
              onClick={() => navigate('/ai')}
              startIcon={<OpenInNewIcon fontSize="small" />}
              sx={{ textTransform: 'none', minWidth: 0, px: 1 }}
            >
              Open
            </Button>
          </Stack>
          <Tooltip title={minimized ? 'Restore' : 'Minimize'}>
            <IconButton
              size="small"
              onClick={() => setMinimized((p) => !p)}
              aria-label={minimized ? 'Restore assistant panel' : 'Minimize assistant panel'}
            >
              {minimized ? (
                <ExpandMoreIcon fontSize="small" />
              ) : (
                <ExpandLessIcon fontSize="small" />
              )}
            </IconButton>
          </Tooltip>
          <Tooltip title="Close">
            <IconButton
              size="small"
              onClick={() => setOpen(false)}
              aria-label="Close assistant panel"
            >
              <CloseIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        {!minimized && (
          <>
            <Divider />
            <Box sx={{ flex: 1, minHeight: 0 }}>
              <AssistantPanel />
            </Box>
          </>
        )}
      </Drawer>
    </>
  )
}
