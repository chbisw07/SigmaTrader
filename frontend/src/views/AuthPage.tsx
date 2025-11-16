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
}

export function AuthPage({ onAuthSuccess }: AuthPageProps) {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)
  const initialMode: Mode = params.get('mode') === 'register' ? 'register' : 'login'

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
        flexDirection: 'row',
      }}
    >
      <Box
        sx={{
          flex: { xs: 0, md: 3 },
          display: { xs: 'none', md: 'flex' },
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'flex-start',
          px: 6,
          gap: 3,
          background:
            'radial-gradient(circle at top left, #ff9800 0, #121212 45%, #000000 100%)',
        }}
      >
        <Typography variant="h3" fontWeight={700}>
          Trade smarter with SigmaTrader
        </Typography>
        <Typography variant="h6" color="text.secondary">
          Turn TradingView alerts into risk-controlled Zerodha orders with a clear
          manual queue, AUTO modes, and rich analytics.
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Typography variant="body1">
            • Capture alerts reliably and see exactly what&apos;s queued.
          </Typography>
          <Typography variant="body1">
            • Apply global and per-strategy risk limits before placing orders.
          </Typography>
          <Typography variant="body1">
            • Connect to Zerodha once and track positions, holdings, and P&amp;L.
          </Typography>
        </Box>
        <Typography variant="caption" color="text.secondary">
          Local, developer-friendly tool – you stay in control of your keys and risk.
        </Typography>
      </Box>

      <Box
        sx={{
          flex: { xs: 1, md: 1 },
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          px: { xs: 2, md: 4 },
          py: { xs: 4, md: 0 },
        }}
      >
        <Paper
          component="form"
          onSubmit={handleSubmit}
          sx={{
            width: '100%',
            maxWidth: 420,
            p: 3,
          }}
        >
          <Typography variant="h5" gutterBottom>
            {mode === 'login' ? 'Sign in to SigmaTrader' : 'Create a SigmaTrader account'}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {mode === 'login'
              ? 'Use your SigmaTrader credentials to access your queue, orders, and analytics.'
              : 'Register a local user account; broker credentials stay in the Settings page.'}
          </Typography>

          <TextField
            label="Username"
            fullWidth
            size="small"
            margin="dense"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          {mode === 'register' && (
            <TextField
              label="Display name (optional)"
              fullWidth
              size="small"
              margin="dense"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
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

