import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import { useEffect, useMemo, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { HelpBlockView } from '../components/HelpBlocks'
import { RISK_REASON_CODES } from '../help/risk/reasonCodes'
import { riskManagementGuide } from '../help/risk/contexts'

export function RiskManagementGuidePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const containerRef = useRef<HTMLDivElement | null>(null)

  const toc = useMemo(
    () => [
      { id: 'overview', label: 'Overview' },
      ...riskManagementGuide.sections.map((s) => ({ id: s.id, label: s.title })),
      { id: 'getting-started', label: 'Defaults / getting started' },
      { id: 'troubleshooting', label: 'Troubleshooting' },
    ],
    [],
  )

  const scrollToId = (id: string) => {
    const root = containerRef.current
    if (!root) return
    const node = root.querySelector<HTMLElement>(`#${CSS.escape(id)}`)
    if (!node) return
    node.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  useEffect(() => {
    const raw = String(location.hash || '')
    const id = raw.startsWith('#') ? raw.slice(1) : raw
    if (!id) return
    const t = window.setTimeout(() => scrollToId(id), 0)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.hash])

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          flexWrap: 'wrap',
          mb: 2,
        }}
      >
        <Typography variant="h4">Risk Management Guide</Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate('/settings?tab=risk')}
        >
          Back to Settings
        </Button>
      </Box>

      <Typography color="text.secondary" sx={{ mb: 3 }}>
        User-facing documentation for SigmaTrader risk controls. This page describes what is enforced
        today and what happens when an execution is blocked.
      </Typography>

      <Paper sx={{ display: 'flex', minHeight: 600, overflow: 'hidden' }}>
        <Box
          sx={{
            width: 280,
            borderRight: 1,
            borderColor: 'divider',
            overflowY: 'auto',
            p: 1,
          }}
        >
          <List dense>
            {toc.map((item) => (
              <ListItemButton key={item.id} onClick={() => scrollToId(item.id)}>
                <ListItemText
                  primary={item.label}
                  primaryTypographyProps={{ variant: 'body2' }}
                />
              </ListItemButton>
            ))}
          </List>
        </Box>

        <Box
          ref={containerRef}
          sx={{
            flex: 1,
            overflowY: 'auto',
            p: 2.5,
          }}
        >
          <Box id="overview" sx={{ scrollMarginTop: 80 }}>
            {riskManagementGuide.overview.map((line) => (
              <Typography key={line} variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>
                {line}
              </Typography>
            ))}
          </Box>

          {riskManagementGuide.sections.map((section) => (
            <Box key={section.id} id={section.id} sx={{ mt: 3, scrollMarginTop: 80 }}>
              <Typography variant="h6" sx={{ mb: 1 }}>
                {section.title}
              </Typography>
              {section.qas.map((qa) => (
                <Box key={qa.id} sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                    Q: {qa.question}
                  </Typography>
                  {qa.answer.map((block, idx) => (
                    <HelpBlockView key={`${qa.id}-${idx}`} block={block} />
                  ))}
                  <Divider sx={{ mt: 1.5 }} />
                </Box>
              ))}

              {section.id === 'reason-codes' && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Detailed glossary
                  </Typography>
                  <Box sx={{ display: 'grid', gap: 1.5 }}>
                    {RISK_REASON_CODES.map((rc) => (
                      <Paper key={rc.code} variant="outlined" sx={{ p: 1.5 }}>
                        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                          {rc.code} — {rc.title}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>
                          {rc.whenItHappens}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Where you see it:
                        </Typography>
                        <Box component="ul" sx={{ pl: 2.25, my: 0, mb: 1, display: 'grid', gap: 0.25 }}>
                          {rc.whereYouSeeIt.map((item) => (
                            <li key={item}>
                              <Typography variant="body2" color="text.secondary">
                                {item}
                              </Typography>
                            </li>
                          ))}
                        </Box>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          What to do:
                        </Typography>
                        <Box component="ul" sx={{ pl: 2.25, my: 0, display: 'grid', gap: 0.25 }}>
                          {rc.whatToDo.map((item) => (
                            <li key={item}>
                              <Typography variant="body2" color="text.secondary">
                                {item}
                              </Typography>
                            </li>
                          ))}
                        </Box>
                      </Paper>
                    ))}
                  </Box>
                </Box>
              )}
            </Box>
          ))}

          <Box id="getting-started" sx={{ mt: 3, scrollMarginTop: 80 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Defaults / getting started
            </Typography>
            <Box component="ul" sx={{ pl: 2.25, my: 0, display: 'grid', gap: 0.5 }}>
              {riskManagementGuide.gettingStarted.map((item) => (
                <li key={item}>
                  <Typography variant="body2" color="text.secondary">
                    {item}
                  </Typography>
                </li>
              ))}
            </Box>
          </Box>

          <Box id="troubleshooting" sx={{ mt: 3, scrollMarginTop: 80 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Troubleshooting
            </Typography>
            {riskManagementGuide.troubleshooting.map((qa) => (
              <Box key={qa.id} sx={{ mb: 2 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
                  Q: {qa.question}
                </Typography>
                {qa.answer.map((block, idx) => (
                  <HelpBlockView key={`${qa.id}-${idx}`} block={block} />
                ))}
                <Divider sx={{ mt: 1.5 }} />
              </Box>
            ))}
          </Box>
        </Box>
      </Paper>
    </Box>
  )
}
