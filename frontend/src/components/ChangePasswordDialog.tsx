import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useState } from 'react'

import { changePassword } from '../services/auth'

export function ChangePasswordDialog({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const [showCurrent, setShowCurrent] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  useEffect(() => {
    if (!open) return
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setError(null)
    setSuccess(false)
    setShowCurrent(false)
    setShowNew(false)
    setShowConfirm(false)
  }, [open])

  const validationError = useMemo(() => {
    if (!currentPassword.trim()) return 'Current password is required.'
    if (newPassword.length < 6) return 'New password must be at least 6 characters.'
    if (newPassword !== confirmPassword) return 'New passwords do not match.'
    if (newPassword === currentPassword) return 'New password must be different.'
    return null
  }, [confirmPassword, currentPassword, newPassword])

  const canSubmit = open && !submitting && !success && !validationError

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      await changePassword(currentPassword, newPassword)
      setSuccess(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setSuccess(false)
    } finally {
      setSubmitting(false)
    }
  }

  const handleClose = () => {
    if (submitting) return
    onClose()
  }

  const adornment = (shown: boolean, onToggle: () => void) => (
    <InputAdornment position="end">
      <IconButton
        aria-label={shown ? 'Hide password' : 'Show password'}
        onClick={onToggle}
        edge="end"
        size="small"
        tabIndex={-1}
      >
        {shown ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
      </IconButton>
    </InputAdornment>
  )

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="xs" fullWidth>
      <DialogTitle>Change password</DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Box
          component="form"
          onSubmit={(e) => {
            e.preventDefault()
            void handleSubmit()
          }}
          sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}
        >
          <Typography variant="body2" color="text.secondary">
            Choose a new password (minimum 6 characters).
          </Typography>

          {error && <Alert severity="error">{error}</Alert>}
          {success && <Alert severity="success">Password updated.</Alert>}

          <TextField
            autoFocus
            label="Current password"
            type={showCurrent ? 'text' : 'password'}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            autoComplete="current-password"
            disabled={submitting || success}
            InputProps={{
              endAdornment: adornment(showCurrent, () => setShowCurrent((v) => !v)),
            }}
          />

          <TextField
            label="New password"
            type={showNew ? 'text' : 'password'}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
            disabled={submitting || success}
            error={Boolean(newPassword) && newPassword.length < 6}
            helperText={
              Boolean(newPassword) && newPassword.length < 6
                ? 'Minimum 6 characters.'
                : ' '
            }
            InputProps={{
              endAdornment: adornment(showNew, () => setShowNew((v) => !v)),
            }}
          />

          <TextField
            label="Confirm new password"
            type={showConfirm ? 'text' : 'password'}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            autoComplete="new-password"
            disabled={submitting || success}
            error={Boolean(confirmPassword) && confirmPassword !== newPassword}
            helperText={
              Boolean(confirmPassword) && confirmPassword !== newPassword
                ? 'Does not match.'
                : ' '
            }
            InputProps={{
              endAdornment: adornment(showConfirm, () => setShowConfirm((v) => !v)),
            }}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={submitting}>
          {success ? 'Close' : 'Cancel'}
        </Button>
        <Button
          variant="contained"
          onClick={() => void handleSubmit()}
          disabled={!canSubmit}
        >
          {submitting ? 'Saving…' : 'Save'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
