import MenuIcon from '@mui/icons-material/Menu'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import AppBar from '@mui/material/AppBar'
import { useMemo, useState } from 'react'
import { Link as RouterLink, Outlet, useLocation } from 'react-router-dom'

import { Logo } from './Logo'

type NavItem = { label: string; to: string }

function useNavItems(): NavItem[] {
  return useMemo(
    () => [
      { label: 'Product', to: '/product' },
      { label: 'Platform', to: '/platform' },
      { label: 'Universe', to: '/features/universe' },
      { label: 'Screener', to: '/features/screener' },
      { label: 'Alerts', to: '/features/alerts' },
      { label: 'Execution', to: '/features/execution' },
      { label: 'Rebalance', to: '/features/rebalance' },
      { label: 'Brokers', to: '/features/brokers' },
      { label: 'Docs', to: '/docs' },
      { label: 'Help', to: '/help' },
      { label: 'Roadmap', to: '/roadmap' },
    ],
    [],
  )
}

function TopNav() {
  const items = useNavItems()
  const loc = useLocation()
  return (
    <Stack direction="row" spacing={1} sx={{ display: { xs: 'none', md: 'flex' } }}>
      {items.map((it) => {
        const active = loc.pathname === it.to || loc.pathname.startsWith(`${it.to}/`)
        return (
          <Button
            key={it.to}
            component={RouterLink}
            to={it.to}
            color={active ? 'secondary' : 'inherit'}
            size="small"
            sx={{ textTransform: 'none' }}
          >
            {it.label}
          </Button>
        )
      })}
    </Stack>
  )
}

function MobileDrawer({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const items = useNavItems()
  const loc = useLocation()
  return (
    <Drawer anchor="left" open={open} onClose={onClose}>
      <Box sx={{ width: 280, p: 2 }}>
        <Box sx={{ mb: 2 }}>
          <Logo />
        </Box>
        <Divider sx={{ mb: 1 }} />
        <Stack spacing={0.5}>
          {items.map((it) => {
            const active =
              loc.pathname === it.to || loc.pathname.startsWith(`${it.to}/`)
            return (
              <Button
                key={it.to}
                component={RouterLink}
                to={it.to}
                onClick={onClose}
                color={active ? 'secondary' : 'inherit'}
                sx={{ justifyContent: 'flex-start', textTransform: 'none' }}
              >
                {it.label}
              </Button>
            )
          })}
        </Stack>
        <Divider sx={{ my: 2 }} />
        <Button
          component="a"
          href="http://localhost:5173/"
          target="_blank"
          rel="noreferrer"
          variant="contained"
          color="secondary"
          sx={{ textTransform: 'none' }}
          fullWidth
        >
          Open the app
        </Button>
      </Box>
    </Drawer>
  )
}

function Footer() {
  return (
    <Box sx={{ borderTop: 1, borderColor: 'divider', mt: 8 }}>
      <Container sx={{ py: 4 }}>
        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={2}
          alignItems={{ xs: 'flex-start', md: 'center' }}
          justifyContent="space-between"
        >
          <Stack spacing={0.5}>
            <Logo />
            <Typography variant="caption" color="text.secondary">
              Personal trading & portfolio operating system (local-first).
            </Typography>
          </Stack>
          <Stack direction="row" spacing={2} flexWrap="wrap">
            <Link component={RouterLink} to="/docs" underline="hover" color="inherit">
              Docs
            </Link>
            <Link component={RouterLink} to="/help" underline="hover" color="inherit">
              Help
            </Link>
            <Link component={RouterLink} to="/roadmap" underline="hover" color="inherit">
              Roadmap
            </Link>
            <Link component={RouterLink} to="/changelog" underline="hover" color="inherit">
              Changelog
            </Link>
            <Link component={RouterLink} to="/about" underline="hover" color="inherit">
              About
            </Link>
          </Stack>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
          Disclaimer: SigmaTrader is a personal tool. Nothing on this site is investment advice.
        </Typography>
      </Container>
    </Box>
  )
}

export function SiteLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  return (
    <>
      <AppBar position="sticky" color="transparent" elevation={0} sx={{ backdropFilter: 'blur(10px)' }}>
        <Toolbar>
          <IconButton
            edge="start"
            color="inherit"
            onClick={() => setMobileOpen(true)}
            sx={{ display: { xs: 'inline-flex', md: 'none' }, mr: 1 }}
          >
            <MenuIcon />
          </IconButton>
          <Link component={RouterLink} to="/" underline="none" color="inherit" sx={{ mr: 2 }}>
            <Logo />
          </Link>
          <Box sx={{ flexGrow: 1 }}>
            <TopNav />
          </Box>
          <Button
            component="a"
            href="http://localhost:5173/"
            target="_blank"
            rel="noreferrer"
            variant="contained"
            color="secondary"
            sx={{ textTransform: 'none', display: { xs: 'none', md: 'inline-flex' } }}
          >
            Open the app
          </Button>
        </Toolbar>
      </AppBar>

      <MobileDrawer open={mobileOpen} onClose={() => setMobileOpen(false)} />

      <Container sx={{ py: 6 }}>
        <Outlet />
      </Container>
      <Footer />
    </>
  )
}

