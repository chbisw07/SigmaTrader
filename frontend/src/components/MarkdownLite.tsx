import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import { Fragment, type ReactNode, useMemo } from 'react'

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = []

  const codeSplit = text.split('`')
  for (let i = 0; i < codeSplit.length; i++) {
    const seg = codeSplit[i] ?? ''
    const isCode = i % 2 === 1
    if (!seg) continue

    if (isCode) {
      out.push(
        <Box
          key={`${keyPrefix}-code-${i}`}
          component="code"
          sx={{
            fontFamily:
              'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: '0.95em',
            px: 0.5,
            py: 0.1,
            borderRadius: 0.5,
            bgcolor: 'action.hover',
          }}
        >
          {seg}
        </Box>,
      )
      continue
    }

    const boldSplit = seg.split('**')
    if (boldSplit.length === 1) {
      out.push(<Fragment key={`${keyPrefix}-t-${i}`}>{seg}</Fragment>)
      continue
    }
    for (let j = 0; j < boldSplit.length; j++) {
      const chunk = boldSplit[j] ?? ''
      if (!chunk) continue
      const isBold = j % 2 === 1
      out.push(
        <Fragment key={`${keyPrefix}-b-${i}-${j}`}>
          {isBold ? <strong>{chunk}</strong> : chunk}
        </Fragment>,
      )
    }
  }

  return out
}

type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'ul'; items: string[] }
  | { kind: 'ol'; items: string[] }
  | { kind: 'code'; text: string }

function parseMarkdownLite(markdown: string): Block[] {
  const lines = (markdown || '').replace(/\r\n/g, '\n').split('\n')

  const blocks: Block[] = []
  let paragraph: string[] = []
  let listKind: 'ul' | 'ol' | null = null
  let listItems: string[] = []
  let inCode = false
  let codeLines: string[] = []

  const flushParagraph = () => {
    const cleaned = paragraph.map((l) => l.trim()).filter(Boolean)
    if (cleaned.length) blocks.push({ kind: 'paragraph', lines: cleaned })
    paragraph = []
  }

  const flushList = () => {
    if (!listKind || !listItems.length) return
    blocks.push({ kind: listKind, items: listItems })
    listKind = null
    listItems = []
  }

  const flushCode = () => {
    if (!codeLines.length) return
    blocks.push({ kind: 'code', text: codeLines.join('\n') })
    codeLines = []
  }

  for (const rawLine of lines) {
    const line = rawLine ?? ''

    if (line.trim().startsWith('```')) {
      if (inCode) {
        inCode = false
        flushCode()
      } else {
        flushList()
        flushParagraph()
        inCode = true
      }
      continue
    }

    if (inCode) {
      codeLines.push(line)
      continue
    }

    const headingMatch = /^(#{1,6})\s+(.*)$/.exec(line)
    if (headingMatch) {
      flushList()
      flushParagraph()
      const level = headingMatch[1]?.length ?? 1
      const text = (headingMatch[2] ?? '').trim()
      blocks.push({ kind: 'heading', level, text })
      continue
    }

    const ulMatch = /^\s*-\s+(.*)$/.exec(line)
    if (ulMatch) {
      flushParagraph()
      if (listKind && listKind !== 'ul') flushList()
      listKind = 'ul'
      listItems.push((ulMatch[1] ?? '').trim())
      continue
    }

    const olMatch = /^\s*\d+\.\s+(.*)$/.exec(line)
    if (olMatch) {
      flushParagraph()
      if (listKind && listKind !== 'ol') flushList()
      listKind = 'ol'
      listItems.push((olMatch[1] ?? '').trim())
      continue
    }

    if (!line.trim()) {
      flushList()
      flushParagraph()
      continue
    }

    if (listKind) flushList()
    paragraph.push(line)
  }

  flushList()
  flushParagraph()
  flushCode()
  return blocks
}

export function MarkdownLite({ text }: { text: string }) {
  const blocks = useMemo(() => parseMarkdownLite(text), [text])

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
      {blocks.map((b, idx) => {
        if (b.kind === 'heading') {
          const level = Math.min(Math.max(b.level, 1), 6)
          const variant =
            level === 1
              ? 'h6'
              : level === 2
                ? 'subtitle1'
                : 'subtitle2'
          return (
            <Typography
              key={`h-${idx}`}
              variant={variant}
              sx={{ mt: level <= 2 ? 1 : 0.5 }}
            >
              {renderInline(b.text, `h-${idx}`)}
            </Typography>
          )
        }

        if (b.kind === 'paragraph') {
          const joined = b.lines.join(' ')
          return (
            <Typography key={`p-${idx}`} variant="body2">
              {renderInline(joined, `p-${idx}`)}
            </Typography>
          )
        }

        if (b.kind === 'ul') {
          return (
            <Box key={`ul-${idx}`} component="ul" sx={{ m: 0, pl: 3 }}>
              {b.items.map((item, j) => (
                <Box key={`ul-${idx}-${j}`} component="li" sx={{ mb: 0.5 }}>
                  <Typography variant="body2">
                    {renderInline(item, `ul-${idx}-${j}`)}
                  </Typography>
                </Box>
              ))}
            </Box>
          )
        }

        if (b.kind === 'ol') {
          return (
            <Box key={`ol-${idx}`} component="ol" sx={{ m: 0, pl: 3 }}>
              {b.items.map((item, j) => (
                <Box key={`ol-${idx}-${j}`} component="li" sx={{ mb: 0.5 }}>
                  <Typography variant="body2">
                    {renderInline(item, `ol-${idx}-${j}`)}
                  </Typography>
                </Box>
              ))}
            </Box>
          )
        }

        if (b.kind === 'code') {
          return (
            <Box
              key={`c-${idx}`}
              component="pre"
              sx={{
                m: 0,
                p: 1,
                borderRadius: 1,
                bgcolor: 'action.hover',
                overflow: 'auto',
                fontFamily:
                  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                fontSize: 12,
              }}
            >
              {b.text}
            </Box>
          )
        }

        return null
      })}
    </Box>
  )
}

