import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import type { ReactNode } from 'react'

export function Page({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: ReactNode
}) {
  return (
    <Box>
      <Typography variant="h3" sx={{ fontWeight: 800, letterSpacing: -0.5 }}>
        {title}
      </Typography>
      {subtitle ? (
        <Typography variant="body1" sx={{ mt: 1, color: 'text.secondary', maxWidth: 860 }}>
          {subtitle}
        </Typography>
      ) : null}
      <Box sx={{ mt: 4 }}>{children}</Box>
    </Box>
  )
}

