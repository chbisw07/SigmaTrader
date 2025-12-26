import SearchIcon from '@mui/icons-material/Search'
import Box from '@mui/material/Box'
import InputAdornment from '@mui/material/InputAdornment'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMemo, useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'

import { Page } from '../components/Page'
import { DOCS } from '../content/docs'

function scoreMatch(haystack: string, query: string): number {
  const h = haystack.toLowerCase()
  const q = query.toLowerCase().trim()
  if (!q) return 0
  if (h === q) return 100
  if (h.includes(q)) return 50
  const tokens = q.split(/\s+/).filter(Boolean)
  let score = 0
  for (const t of tokens) {
    if (h.includes(t)) score += 10
  }
  return score
}

export function HelpPage() {
  const [q, setQ] = useState('')
  const results = useMemo(() => {
    const query = q.trim()
    if (!query) return []
    const ranked = DOCS.map((d) => {
      const base = `${d.title}\n${d.description}\n${d.tags.join(' ')}\n${d.content}`
      const s = scoreMatch(base, query)
      return { doc: d, score: s }
    })
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 10)
    return ranked
  }, [q])

  return (
    <Page
      title="Help"
      subtitle="Search SigmaTrader’s documentation and design notes. This is a simple local search (no external services)."
    >
      <Stack spacing={2}>
        <TextField
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Try: rebalance, drift band, screener, RSI, alerts, universe, risk parity…"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />

        {q.trim() ? (
          results.length ? (
            <Stack spacing={1}>
              {results.map((r) => (
                <Paper
                  key={r.doc.id}
                  variant="outlined"
                  component={RouterLink}
                  to={`/docs/${r.doc.id}`}
                  sx={{
                    p: 2,
                    textDecoration: 'none',
                    color: 'inherit',
                    '&:hover': { borderColor: 'rgba(45,212,191,0.5)' },
                  }}
                >
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2 }}>
                    <Box>
                      <Typography variant="subtitle1" sx={{ fontWeight: 900 }}>
                        {r.doc.title}
                      </Typography>
                      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                        {r.doc.description}
                      </Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                      score {r.score}
                    </Typography>
                  </Box>
                </Paper>
              ))}
            </Stack>
          ) : (
            <Typography color="text.secondary">
              No matches. Try fewer words or different terms.
            </Typography>
          )
        ) : (
          <Typography color="text.secondary">
            Start typing to search across docs. For deep rebalancing help, open the
            “Rebalance help” doc.
          </Typography>
        )}
      </Stack>
    </Page>
  )
}

