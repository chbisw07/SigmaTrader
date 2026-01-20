import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'

import type { HelpBlock } from '../help/risk/types'

export function HelpBlockView({ block }: { block: HelpBlock }) {
  if (block.type === 'p') {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        {block.text}
      </Typography>
    )
  }
  if (block.type === 'bullets') {
    return (
      <Box component="ul" sx={{ pl: 2.25, my: 0, mb: 1, display: 'grid', gap: 0.5 }}>
        {block.items.map((item) => (
          <li key={item}>
            <Typography variant="body2" color="text.secondary">
              {item}
            </Typography>
          </li>
        ))}
      </Box>
    )
  }
  if (block.type === 'code') {
    return (
      <Box
        component="pre"
        sx={{
          bgcolor: 'action.hover',
          borderRadius: 1,
          p: 1.25,
          overflowX: 'auto',
          mb: 1,
          fontSize: 12,
        }}
      >
        <code>{block.code}</code>
      </Box>
    )
  }
  const toneColor =
    block.tone === 'error'
      ? 'error.main'
      : block.tone === 'warning'
        ? 'warning.main'
        : 'info.main'
  return (
    <Box
      sx={{
        borderLeft: 3,
        borderColor: toneColor,
        bgcolor: 'action.hover',
        borderRadius: 1,
        px: 1.25,
        py: 1,
        mb: 1,
      }}
    >
      <Typography variant="body2" color="text.secondary">
        {block.text}
      </Typography>
    </Box>
  )
}

