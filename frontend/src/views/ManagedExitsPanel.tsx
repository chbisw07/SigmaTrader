import Box from '@mui/material/Box'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'

import { useMemo, useState } from 'react'

import { HoldingsExitPanel } from './HoldingsExitPanel'
import { ManagedRiskPanel } from './ManagedRiskPage'

type ManagedExitsTab = 'positions' | 'holdings'

export function ManagedExitsPanel({
  embedded = false,
  active = true,
}: {
  embedded?: boolean
  active?: boolean
}) {
  const initialTab = useMemo<ManagedExitsTab>(() => 'positions', [])
  const [tab, setTab] = useState<ManagedExitsTab>(initialTab)

  if (!active) return null

  return (
    <Box>
      <Tabs
        value={tab}
        onChange={(_e, v) => setTab(v as ManagedExitsTab)}
        sx={{ mb: 2 }}
      >
        <Tab value="positions" label="Position exits" />
        <Tab value="holdings" label="Holdings exits" />
      </Tabs>
      <Box sx={{ display: tab === 'positions' ? 'block' : 'none' }}>
        <ManagedRiskPanel embedded={embedded} active={active && tab === 'positions'} />
      </Box>
      <Box sx={{ display: tab === 'holdings' ? 'block' : 'none' }}>
        <HoldingsExitPanel embedded={embedded} active={active && tab === 'holdings'} />
      </Box>
    </Box>
  )
}
