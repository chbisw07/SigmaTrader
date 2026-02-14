import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState } from 'react'

async function writeToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const el = document.createElement('textarea')
  el.value = text
  el.style.position = 'fixed'
  el.style.left = '-1000px'
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  document.body.removeChild(el)
}

export function TradingViewAlertPayloadBuilder({
  webhookSecret,
}: {
  webhookSecret: string
}) {
  const [copied, setCopied] = useState(false)
  const recommendedAlertMessage = '{{strategy.order.alert_message}}'

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6" sx={{ mb: 0.5 }}>
        Alert setup (recommended)
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        SigmaTrader Strategy v6 sends a full JSON payload via TradingView’s Strategy alerts. You
        only need to forward it to SigmaTrader.
      </Typography>

      <Alert severity="info" sx={{ mb: 1.5 }}>
        <Typography variant="body2" sx={{ mb: 1 }}>
          Create one TradingView alert:
        </Typography>
        <Typography variant="body2">
          - Condition: Strategy → Order fills
          <br />- Webhook URL: <code>/webhook/tradingview</code>
          <br />- Message:
        </Typography>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', mt: 1 }}>
          <TextField
            size="small"
            value={recommendedAlertMessage}
            label="TradingView alert message"
            fullWidth
            sx={{ maxWidth: 520 }}
            InputProps={{ readOnly: true }}
          />
          <Button
            size="small"
            variant="outlined"
            startIcon={<ContentCopyIcon />}
            onClick={() => {
              void (async () => {
                await writeToClipboard(recommendedAlertMessage)
                setCopied(true)
                window.setTimeout(() => setCopied(false), 1200)
              })()
            }}
          >
            {copied ? 'Copied' : 'Copy'}
          </Button>
        </Box>
      </Alert>

      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
        Secret auth is validated via <code>meta.secret</code> (recommended) or <code>secret</code>{' '}
        (legacy), or header <code>X-SIGMATRADER-SECRET</code>. Current configured secret length:{' '}
        {webhookSecret?.trim() ? webhookSecret.trim().length : 0}.
      </Typography>
    </Paper>
  )
}

