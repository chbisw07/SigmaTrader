import { ReactNode, useEffect, useState } from 'react'
import AppBar from '@mui/material/AppBar'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CssBaseline from '@mui/material/CssBaseline'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Stack from '@mui/material/Stack'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import AnalyticsIcon from '@mui/icons-material/Analytics'
import DashboardIcon from '@mui/icons-material/Dashboard'
import ListAltIcon from '@mui/icons-material/ListAlt'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import MenuIcon from '@mui/icons-material/Menu'
import SettingsIcon from '@mui/icons-material/Settings'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import WarningIcon from '@mui/icons-material/Warning'
import PaletteIcon from '@mui/icons-material/Palette'
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive'
import { NavLink } from 'react-router-dom'

import { useHealth } from '../services/health'
import { logout, type CurrentUser } from '../services/auth'

const drawerWidth = 220
const collapsedDrawerWidth = 64

type MainLayoutProps = {
  children: ReactNode
  currentUser: CurrentUser
  onAuthChange: (user: CurrentUser | null) => void
}

type NavItem = {
  label: string
  to: string
  icon: ReactNode
}

const navItems: NavItem[] = [
  { label: 'Dashboard', to: '/', icon: <DashboardIcon /> },
  { label: 'Queue', to: '/queue', icon: <ListAltIcon /> },
  { label: 'Orders', to: '/orders', icon: <ReceiptLongIcon /> },
  { label: 'Positions', to: '/positions', icon: <ShowChartIcon /> },
  { label: 'Holdings', to: '/holdings', icon: <AccountBalanceWalletIcon /> },
   { label: 'Alerts', to: '/alerts', icon: <NotificationsActiveIcon /> },
  { label: 'Analytics', to: '/analytics', icon: <AnalyticsIcon /> },
  { label: 'System Events', to: '/system-events', icon: <WarningIcon /> },
  { label: 'Appearance', to: '/appearance', icon: <PaletteIcon /> },
  { label: 'Settings', to: '/settings', icon: <SettingsIcon /> },
]

export function MainLayout({ children, currentUser, onAuthChange }: MainLayoutProps) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    try {
      return window.localStorage.getItem('st_sidebar_collapsed_v1') === '1'
    } catch {
      return false
    }
  })
  const { status, isLoading } = useHealth()
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)
  const open = Boolean(anchorEl)

  const handleDrawerToggle = () => {
    setMobileOpen((prev) => !prev)
  }

  const handleUserMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleUserMenuClose = () => {
    setAnchorEl(null)
  }

  const handleLogout = async () => {
    try {
      await logout()
    } finally {
      onAuthChange(null)
    }
  }

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(
        'st_sidebar_collapsed_v1',
        sidebarCollapsed ? '1' : '0',
      )
    } catch {
      // Ignore persistence errors.
    }
  }, [sidebarCollapsed])

  const effectiveDrawerWidth = sidebarCollapsed
    ? collapsedDrawerWidth
    : drawerWidth

  const drawer = (
    <div>
      <Toolbar>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
            width: '100%',
          }}
        >
          <Box
            component="img"
            src="/sigma_trader_logo.png"
            alt="SigmaTrader logo"
            sx={{ height: 32, width: 32, borderRadius: 1 }}
          />
          {!sidebarCollapsed && (
            <Typography variant="h6" noWrap component="div">
              SigmaTrader
            </Typography>
          )}
        </Box>
      </Toolbar>
      <Divider />
      <List>
        {navItems.map((item) => (
          <ListItem key={item.to} disablePadding>
            <ListItemButton
              component={NavLink}
              to={item.to}
              sx={{
                '&.active': {
                  bgcolor: 'action.selected',
                },
                justifyContent: sidebarCollapsed ? 'center' : 'flex-start',
                px: sidebarCollapsed ? 1 : 2,
              }}
            >
              <ListItemIcon
                sx={{
                  minWidth: sidebarCollapsed ? 0 : 40,
                  justifyContent: 'center',
                }}
              >
                {item.icon}
              </ListItemIcon>
              {!sidebarCollapsed && <ListItemText primary={item.label} />}
            </ListItemButton>
          </ListItem>
        ))}
      </List>
    </div>
  )

  const statusLabel =
    status === 'ok'
      ? 'API: Connected'
      : status === 'error'
        ? 'API: Error'
        : 'API: Checking'

  const statusColor: 'default' | 'success' | 'error' =
    status === 'ok' ? 'success' : status === 'error' ? 'error' : 'default'

  return (
    <Box sx={{ display: 'flex' }}>
      <CssBaseline />
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${effectiveDrawerWidth}px)` },
          ml: { sm: `${effectiveDrawerWidth}px` },
        }}
      >
        <Toolbar sx={{ justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <IconButton
              color="inherit"
              aria-label="open drawer"
              edge="start"
              onClick={handleDrawerToggle}
              sx={{ mr: 2, display: { sm: 'none' } }}
            >
              <MenuIcon />
            </IconButton>
            <IconButton
              color="inherit"
              aria-label="toggle sidebar"
              edge="start"
              onClick={() => setSidebarCollapsed((prev) => !prev)}
              sx={{ mr: 1, display: { xs: 'none', sm: 'inline-flex' } }}
            >
              <MenuIcon />
            </IconButton>
            <Box
              component="img"
              src="/sigma_trader_logo.png"
              alt="SigmaTrader logo"
              sx={{ height: 32, width: 32, borderRadius: 1, display: { xs: 'none', sm: 'block' } }}
            />
            <Typography variant="h6" noWrap component="div">
              SigmaTrader
            </Typography>
          </Box>
          <Stack direction="row" spacing={2} alignItems="center">
            <Chip
              size="small"
              label={statusLabel}
              color={statusColor}
              variant={statusColor === 'default' ? 'outlined' : 'filled'}
            />
            {!isLoading && (
              <Typography variant="body2" sx={{ display: { xs: 'none', md: 'block' } }}>
                Health: {status === 'ok' ? 'All systems nominal' : 'See backend logs'}
              </Typography>
            )}
            <Box>
              <Button
                color="inherit"
                size="small"
                onClick={handleUserMenuOpen}
              >
                {currentUser.display_name || currentUser.username}
              </Button>
              <Menu
                anchorEl={anchorEl}
                open={open}
                onClose={handleUserMenuClose}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
              >
                <MenuItem disabled>{currentUser.username}</MenuItem>
                <MenuItem onClick={handleUserMenuClose}>Profile (coming soon)</MenuItem>
                <MenuItem onClick={handleUserMenuClose}>
                  Change password (coming soon)
                </MenuItem>
                <MenuItem
                  onClick={() => {
                    handleUserMenuClose()
                    void handleLogout()
                  }}
                >
                  Logout
                </MenuItem>
              </Menu>
            </Box>
          </Stack>
        </Toolbar>
      </AppBar>
      <Box
        component="nav"
        sx={{ width: { sm: effectiveDrawerWidth }, flexShrink: { sm: 0 } }}
        aria-label="main navigation"
      >
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': {
              boxSizing: 'border-box',
              width: effectiveDrawerWidth,
            },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          width: { sm: `calc(100% - ${effectiveDrawerWidth}px)` },
          mt: 8,
        }}
      >
        {children}
      </Box>
    </Box>
  )
}

export default MainLayout
