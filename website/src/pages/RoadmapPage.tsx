import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useMemo } from 'react'

import { Page } from '../components/Page'

import roadmapRaw from '../../../docs/website/roadmap.json?raw'

type RoadmapTask = {
  sprint: string
  group: string
  groupDesc: string
  taskId: string
  taskDesc: string
  status: string
  remarks: string
}

type Roadmap = {
  generated_at: string
  source: string
  sprints: Array<{ sprint: string; tasks: RoadmapTask[] }>
}

function normalizeStatus(raw: string): string {
  const s = (raw || '').trim().toLowerCase()
  if (!s) return 'unknown'
  if (s.includes('implement')) return 'implemented'
  if (s.includes('plan')) return 'planned'
  if (s.includes('in progress')) return 'in_progress'
  if (s.includes('blocked')) return 'blocked'
  return s.replace(/\s+/g, '_')
}

function statusColor(s: string): 'success' | 'warning' | 'info' | 'default' {
  if (s === 'implemented') return 'success'
  if (s === 'planned') return 'info'
  if (s === 'in_progress') return 'warning'
  return 'default'
}

export function RoadmapPage() {
  const data = useMemo(() => {
    try {
      return JSON.parse(roadmapRaw) as Roadmap
    } catch {
      return null
    }
  }, [])

  if (!data) {
    return (
      <Page
        title="Roadmap"
        subtitle="Generate `docs/website/roadmap.json` from `docs/sprint_tasks_codex.xlsx` and reload."
      >
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Typography color="text.secondary">
            Missing or invalid `docs/website/roadmap.json`.
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Run: <Box component="code">npm -C website run roadmap:generate</Box>
          </Typography>
        </Paper>
      </Page>
    )
  }

  const sprints = data.sprints ?? []
  return (
    <Page
      title="Roadmap"
      subtitle={`Derived from ${data.source} (generated ${new Date(data.generated_at).toLocaleString()}).`}
    >
      <Stack spacing={2}>
        {sprints.map((s) => {
          const tasks = s.tasks ?? []
          const counts = tasks.reduce(
            (acc, t) => {
              const st = normalizeStatus(t.status)
              acc[st] = (acc[st] ?? 0) + 1
              return acc
            },
            {} as Record<string, number>,
          )
          return (
            <Paper key={s.sprint} variant="outlined" sx={{ p: 3 }}>
              <Stack spacing={1}>
                <Typography variant="h6" sx={{ fontWeight: 900 }}>
                  {s.sprint}
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  {Object.entries(counts).map(([k, v]) => (
                    <Chip key={k} size="small" label={`${k}: ${v}`} />
                  ))}
                </Stack>
                <Box sx={{ mt: 1 }}>
                  <Stack spacing={1}>
                    {tasks.slice(0, 24).map((t) => {
                      const st = normalizeStatus(t.status)
                      return (
                        <Paper key={t.taskId} variant="outlined" sx={{ p: 2 }}>
                          <Box
                            sx={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              gap: 2,
                              flexWrap: 'wrap',
                            }}
                          >
                            <Box>
                              <Typography variant="subtitle1" sx={{ fontWeight: 900 }}>
                                {t.taskId}: {t.taskDesc}
                              </Typography>
                              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                                {t.group} — {t.groupDesc}
                              </Typography>
                              {t.remarks ? (
                                <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
                                  Notes: {t.remarks}
                                </Typography>
                              ) : null}
                            </Box>
                            <Chip
                              size="small"
                              label={st}
                              color={statusColor(st)}
                              variant={st === 'implemented' ? 'filled' : 'outlined'}
                            />
                          </Box>
                        </Paper>
                      )
                    })}
                    {tasks.length > 24 ? (
                      <Typography variant="caption" color="text.secondary">
                        Showing first 24 tasks for this sprint.
                      </Typography>
                    ) : null}
                  </Stack>
                </Box>
              </Stack>
            </Paper>
          )
        })}
      </Stack>
    </Page>
  )
}

