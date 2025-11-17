import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Link from '@mui/material/Link'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { FormEvent, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { login, register, type CurrentUser } from '../services/auth'
import { recordAppLog } from '../services/logs'

type Mode = 'login' | 'register'

type AuthPageProps = {
  onAuthSuccess: (user: CurrentUser) => void
  mode?: Mode
}

export function AuthPage({ onAuthSuccess, mode: modeProp }: AuthPageProps) {
  const location = useLocation()
  const navigate = useNavigate()

  const params = new URLSearchParams(location.search)
  const initialModeFromQuery: Mode =
    params.get('mode') === 'register' ? 'register' : 'login'
  const initialMode: Mode = modeProp ?? initialModeFromQuery

  const [mode, setMode] = useState<Mode>(initialMode)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggleMode = () => {
    const next: Mode = mode === 'login' ? 'register' : 'login'
    setMode(next)
    setError(null)
    const search = next === 'register' ? '?mode=register' : ''
    navigate({ pathname: '/auth', search }, { replace: true })
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!username || !password) {
      setError('Please enter both username and password.')
      return
    }

    setIsSubmitting(true)
    try {
      let user: CurrentUser
      if (mode === 'login') {
        user = await login(username, password)
      } else {
        user = await register(username, password, displayName || username)
      }
      onAuthSuccess(user)
      setError(null)
      navigate('/', { replace: true })
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Authentication failed.'
      setError(message)
      recordAppLog('ERROR', message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        bgcolor: 'background.default',
      }}
    >
      {/* Hero / marketing column */}
      <Box
        sx={{
          flex: { xs: '0 0 auto', md: 7 },
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          py: { xs: 6, md: 0 },
          px: { xs: 3, md: 6 },
          position: 'relative',
          overflow: 'hidden',
          bgcolor: 'background.default',
          borderRight: { xs: 'none', md: '1px solid' },
          borderColor: { xs: 'transparent', md: 'divider' },
        }}
      >
        <Box
          sx={{
            position: 'relative',
            maxWidth: 760,
            display: 'flex',
            flexDirection: 'column',
            gap: 3.5,
          }}
        >
          <Typography variant="overline" color="primary.main" sx={{ letterSpacing: 1.2 }}>
            TradingView · Zerodha · Risk engine
          </Typography>
          <Typography variant="h3" fontWeight={700}>
            Trade smarter with SigmaTrader
          </Typography>
          <Typography variant="h6" color="text.secondary">
            Turn clean, validated TradingView alerts into disciplined Zerodha
            orders – with a review queue for manual trades, AUTO execution
            modes, and risk controls that always put capital protection first.
          </Typography>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: 'repeat(3, 1fr)' },
              gap: 2,
            }}
          >
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                borderRadius: 3,
                bgcolor: 'background.paper',
                borderColor: 'divider',
              }}
            >
              <Typography variant="subtitle2" color="primary.main">
                TradingView → Zerodha bridge
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                Capture alerts from your strategies and convert them into
                precise, structured orders for NSE / BSE using your own Zerodha
                account.
              </Typography>
            </Paper>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                borderRadius: 3,
                bgcolor: 'background.paper',
                borderColor: 'divider',
              }}
            >
              <Typography variant="subtitle2" color="primary.main">
                Queue &amp; risk engine
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                Review orders in a manual queue, apply per-strategy limits, and
                let AUTO strategies run within your defined risk.
              </Typography>
            </Paper>
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                borderRadius: 3,
                bgcolor: 'background.paper',
                borderColor: 'divider',
              }}
            >
              <Typography variant="subtitle2" color="primary.main">
                Analytics &amp; audit trail
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                Track P&amp;L, positions, and key system events in one place so
                you always know what fired, when, and why.
              </Typography>
            </Paper>
          </Box>

          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' },
              gap: 2,
            }}
          >
            <Paper
              sx={{
                p: 2,
                minWidth: 220,
                borderRadius: 3,
                bgcolor: 'background.paper',
              }}
              variant="outlined"
            >
              <Typography variant="subtitle2" color="primary.main">
                Basic – Free
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                For individual traders who want full control without ongoing
                platform fees.
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                • Local, self-hosted setup
                <br />
                • Manual queue + AUTO modes
                <br />
                • Core analytics, logs &amp; risk limits
              </Typography>
            </Paper>
            <Paper
              sx={{
                p: 2,
                minWidth: 220,
                borderRadius: 3,
                border: '1px solid',
                borderColor: 'primary.main',
                bgcolor: 'background.paper',
              }}
              variant="outlined"
            >
              <Typography variant="subtitle2" color="primary.main">
                Premium – Coming Soon
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                For active Indian traders who need deeper automation, insights,
                and support.
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                • Multi-strategy &amp; multi-account workflows
                <br />
                • Advanced analytics, reporting &amp; alert tooling
                <br />
                • Priority onboarding &amp; support
              </Typography>
            </Paper>
          </Box>

          <Typography variant="caption" color="text.secondary">
            Local, developer-friendly tool – you stay in control of your keys,
            risk, and infrastructure.
          </Typography>
        </Box>
      </Box>

      {/* Auth card column */}
      <Box
        sx={{
          flex: { xs: '1 0 auto', md: 3 },
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          px: { xs: 2, md: 4 },
          py: { xs: 6, md: 0 },
        }}
      >
        <Paper
          component="form"
          onSubmit={handleSubmit}
          elevation={6}
          sx={{
            width: '100%',
            maxWidth: 420,
            p: { xs: 3, md: 4 },
            borderRadius: 3,
            bgcolor: 'background.paper',
          }}
        >
          <Typography variant="h5" gutterBottom>
            {mode === 'login' ? 'Sign in to SigmaTrader' : 'Create a SigmaTrader account'}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {mode === 'login'
              ? 'Use your SigmaTrader account to access your queue, orders, and analytics.'
              : 'Register a local user account. Broker credentials and secrets stay under your control in Settings.'}
          </Typography>

          <TextField
            label="Username"
            fullWidth
            size="small"
            margin="dense"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          {mode === 'register' && (
            <TextField
              label="Display name (optional)"
              fullWidth
              size="small"
              margin="dense"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="name"
            />
          )}
          <TextField
            label="Password"
            type="password"
            fullWidth
            size="small"
            margin="dense"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
          />

          {error && (
            <Typography
              variant="body2"
              color="error"
              sx={{ mt: 1, mb: 1 }}
            >
              {error}
            </Typography>
          )}

          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 2, mb: 1 }}
            disabled={isSubmitting}
          >
            {isSubmitting
              ? mode === 'login'
                ? 'Signing in...'
                : 'Creating account...'
              : mode === 'login'
                ? 'Sign in'
                : 'Sign up'}
          </Button>

          <Typography variant="body2" align="center">
            {mode === 'login' ? (
              <>
                New here?{' '}
                <Link
                  component="button"
                  type="button"
                  onClick={toggleMode}
                  sx={{ fontSize: '0.875rem' }}
                >
                  Create an account
                </Link>
              </>
            ) : (
              <>
                Already have an account?{' '}
                <Link
                  component="button"
                  type="button"
                  onClick={toggleMode}
                  sx={{ fontSize: '0.875rem' }}
                >
                  Sign in
                </Link>
              </>
            )}
          </Typography>
        </Paper>
      </Box>
    </Box>
  )
}
