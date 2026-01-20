import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import CloseIcon from '@mui/icons-material/Close'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

import { HelpBlockView } from './HelpBlocks'
import type { HelpContext } from '../help/risk/types'

type TocItem = { id: string; label: string }

export function RiskHelpDrawer({
  open,
  onClose,
  context,
  showFullGuideLink = true,
}: {
  open: boolean
  onClose: () => void
  context: HelpContext
  showFullGuideLink?: boolean
}) {
  const navigate = useNavigate()
  const mdUp = useMediaQuery('(min-width:900px)')
  const containerRef = useRef<HTMLDivElement | null>(null)

  const toc = useMemo<TocItem[]>(() => {
    return [
      { id: 'overview', label: 'Overview' },
      ...context.sections.map((s) => ({ id: s.id, label: s.title })),
      { id: 'getting-started', label: 'Defaults / getting started' },
      { id: 'troubleshooting', label: 'Troubleshooting' },
    ]
  }, [context.sections])

  const scrollToId = (id: string) => {
    const root = containerRef.current
    if (!root) return
    const node = root.querySelector<HTMLElement>(`#${CSS.escape(id)}`)
    if (!node) return
    node.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: {
          width: mdUp ? 560 : '100vw',
          maxWidth: '100vw',
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', p: 2, gap: 1 }}>
        <Typography variant="h6" sx={{ flex: 1 }}>
          {context.title}
        </Typography>
        {showFullGuideLink && (
          <Button
            size="small"
            variant="outlined"
            endIcon={<OpenInNewIcon fontSize="small" />}
            onClick={() => {
              onClose()
              navigate('/risk-guide')
            }}
          >
            Full guide
          </Button>
        )}
        <IconButton onClick={onClose} aria-label="close help">
          <CloseIcon />
        </IconButton>
      </Box>
      <Divider />

      <Box sx={{ display: 'flex', height: '100%', minHeight: 0 }}>
        <Box
          sx={{
            width: 210,
            borderRight: 1,
            borderColor: 'divider',
            display: mdUp ? 'block' : 'none',
            overflowY: 'auto',
          }}
        >
          <List dense sx={{ py: 1 }}>
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
            p: 2,
          }}
        >
          {!mdUp && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                Jump to
              </Typography>
              <Box component="ul" sx={{ pl: 2.25, my: 0, display: 'grid', gap: 0.25 }}>
                {toc.map((item) => (
                  <li key={item.id}>
                    <Button
                      size="small"
                      variant="text"
                      onClick={() => scrollToId(item.id)}
                      sx={{ px: 0, justifyContent: 'flex-start' }}
                    >
                      {item.label}
                    </Button>
                  </li>
                ))}
              </Box>
            </Box>
          )}
          <Box id="overview" sx={{ scrollMarginTop: 80 }}>
            {context.overview.map((line) => (
              <Typography key={line} variant="body2" color="text.secondary" sx={{ mb: 0.75 }}>
                {line}
              </Typography>
            ))}
          </Box>

          {context.sections.map((section) => (
            <Box key={section.id} id={section.id} sx={{ mt: 2.5, scrollMarginTop: 80 }}>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>
                {section.title}
              </Typography>
              {section.qas.map((qa) => (
                <Accordion key={qa.id} disableGutters>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography variant="body2">{qa.question}</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    {qa.answer.map((block, idx) => (
                      <HelpBlockView key={`${qa.id}-${idx}`} block={block} />
                    ))}
                  </AccordionDetails>
                </Accordion>
              ))}
            </Box>
          ))}

          <Box id="getting-started" sx={{ mt: 2.5, scrollMarginTop: 80 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Defaults / getting started
            </Typography>
            <Box component="ul" sx={{ pl: 2.25, my: 0, display: 'grid', gap: 0.5 }}>
              {context.gettingStarted.map((item) => (
                <li key={item}>
                  <Typography variant="body2" color="text.secondary">
                    {item}
                  </Typography>
                </li>
              ))}
            </Box>
          </Box>

          <Box id="troubleshooting" sx={{ mt: 2.5, scrollMarginTop: 80 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Troubleshooting
            </Typography>
            {context.troubleshooting.map((qa) => (
              <Accordion key={qa.id} disableGutters>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="body2">{qa.question}</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  {qa.answer.map((block, idx) => (
                    <HelpBlockView key={`${qa.id}-${idx}`} block={block} />
                  ))}
                </AccordionDetails>
              </Accordion>
            ))}
          </Box>
        </Box>
      </Box>
    </Drawer>
  )
}
