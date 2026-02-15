import CloseIcon from '@mui/icons-material/Close'
import SearchIcon from '@mui/icons-material/Search'
import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useMemo, useState } from 'react'

import { buildDslCatalog, type DslCatalogItem, type DslCatalogKind } from '../services/dslCatalog'

type CustomIndicator = {
  name: string
  params?: string[]
  description?: string | null
}

export function DslExprHelpDrawer({
  open,
  onClose,
  operands,
  customIndicators,
  onInsert,
  title = 'DSL expression help',
}: {
  open: boolean
  onClose: () => void
  operands?: string[]
  customIndicators?: CustomIndicator[]
  onInsert: (text: string) => void
  title?: string
}) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<DslCatalogKind | 'all'>('all')

  const items = useMemo(() => {
    const catalog = buildDslCatalog({ operands, customIndicators })
    const q = query.trim().toLowerCase()
    return catalog.filter((it) => {
      if (kind !== 'all' && it.kind !== kind) return false
      if (!q) return true
      return (
        it.expr.toLowerCase().includes(q) ||
        it.signature.toLowerCase().includes(q) ||
        it.details.toLowerCase().includes(q)
      )
    })
  }, [customIndicators, kind, operands, query])

  const kindChips: Array<{ label: string; value: DslCatalogKind | 'all' }> = [
    { label: 'All', value: 'all' },
    { label: 'Functions', value: 'function' },
    { label: 'Metrics', value: 'metric' },
    { label: 'Variables', value: 'variable' },
    { label: 'Custom', value: 'custom_indicator' },
    { label: 'Keywords', value: 'keyword' },
    { label: 'Sources', value: 'source' },
  ]

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: { xs: '100vw', sm: 560 },
          maxWidth: '100vw',
          p: 2,
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
          <Typography variant="h6">{title}</Typography>
          <Typography variant="caption" color="text.secondary">
            Click a row to insert into the editor.
          </Typography>
        </Box>
        <IconButton aria-label="Close" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </Box>

      <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
        {kindChips.map((c) => (
          <Chip
            key={c.value}
            size="small"
            label={c.label}
            color={kind === c.value ? 'primary' : 'default'}
            variant={kind === c.value ? 'filled' : 'outlined'}
            onClick={() => setKind(c.value)}
          />
        ))}
      </Box>

      <TextField
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search… (e.g. SMA, PNL_PCT, crosses)"
        size="small"
        fullWidth
        sx={{ mt: 2 }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" />
            </InputAdornment>
          ),
        }}
      />

      <Divider sx={{ my: 2 }} />

      <Box sx={{ flex: 1, overflow: 'auto' }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: 140 }}>Expr</TableCell>
              <TableCell sx={{ width: 240 }}>Signature</TableCell>
              <TableCell>Details</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3}>
                  <Typography variant="body2" color="text.secondary">
                    No matches.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              items.map((it) => (
                <DslRow
                  key={`${it.kind}:${it.expr}:${it.signature}`}
                  item={it}
                  onInsert={onInsert}
                />
              ))
            )}
          </TableBody>
        </Table>
      </Box>
    </Drawer>
  )
}

function DslRow({
  item,
  onInsert,
}: {
  item: DslCatalogItem
  onInsert: (text: string) => void
}) {
  return (
    <TableRow
      hover
      sx={{ cursor: 'pointer' }}
      onClick={() => onInsert(item.insertText ?? item.signature)}
    >
      <TableCell>
        <Typography variant="body2">
          <code>{item.expr}</code>
        </Typography>
      </TableCell>
      <TableCell>
        <Typography variant="body2" component="div" sx={{ whiteSpace: 'nowrap' }}>
          <code>{item.signature}</code>
        </Typography>
      </TableCell>
      <TableCell>
        <Tooltip title={item.details}>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              maxWidth: 280,
            }}
          >
            {item.details}
          </Typography>
        </Tooltip>
      </TableCell>
    </TableRow>
  )
}

