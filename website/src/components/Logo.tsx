import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'

export function Logo({ variant = 'full' }: { variant?: 'full' | 'mark' }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box
        component="img"
        src="/sigma_trader_logo.png"
        alt="SigmaTrader"
        sx={{ width: 28, height: 28 }}
      />
      {variant === 'full' ? (
        <Typography
          variant="subtitle1"
          sx={{ fontWeight: 700, letterSpacing: 0.2 }}
        >
          SigmaTrader
        </Typography>
      ) : null}
    </Box>
  )
}

