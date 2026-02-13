import Box from '@mui/material/Box'
import Tab from '@mui/material/Tab'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { AlertDecisionLogPanel } from '../components/AlertDecisionLogPanel'
import { ManagedExitsPanel } from './ManagedExitsPanel'
import { OrdersPanel } from './OrdersPage'
import { WaitingQueuePanel } from './QueuePage'
import { TvAlertsPanel } from './TvAlertsPanel'

type QueueTab = 'tv_alerts' | 'waiting' | 'risk_mgmt' | 'orders' | 'managed_exits'

function parseTab(value: string | null | undefined): QueueTab | null {
  const v = (value ?? '').trim().toLowerCase()
  if (v === 'tv' || v === 'tv_alerts' || v === 'tv-alerts' || v === 'alerts') {
    return 'tv_alerts'
  }
  if (v === 'waiting' || v === 'queue') return 'waiting'
  if (
    v === 'risk_mgmt' ||
    v === 'risk-mgmt' ||
    v === 'risk-management' ||
    v === 'riskmanagement' ||
    v === 'decision-log' ||
    v === 'audit' ||
    v === 'rm'
  ) {
    return 'risk_mgmt'
  }
  if (v === 'orders') return 'orders'
  if (
    v === 'managed' ||
    v === 'managed_exits' ||
    v === 'managed-exits' ||
    v === 'exits' ||
    v === 'managed-risk' ||
    v === 'risk'
  ) {
    // `risk` kept for backward compatibility (historically mapped to "Managed exits")
    return 'managed_exits'
  }
  return null
}

export function QueueManagementPage() {
  const location = useLocation()
  const navigate = useNavigate()

  const initialTab = useMemo<QueueTab>(() => {
    const qp = new URLSearchParams(location.search)
    return (
      parseTab(qp.get('tab')) ??
      (location.pathname.startsWith('/orders') ? 'orders' : 'waiting')
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [tab, setTab] = useState<QueueTab>(initialTab)

  useEffect(() => {
    const qp = new URLSearchParams(location.search)
    const next = parseTab(qp.get('tab'))
    if (next && next !== tab) setTab(next)
  }, [location.search, tab])

  const setActiveTab = (next: QueueTab) => {
    setTab(next)
    const qp = new URLSearchParams(location.search)
    qp.set('tab', next)
    navigate({ pathname: '/queue', search: `?${qp.toString()}` }, { replace: true })
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Queue Management
      </Typography>
      <Tabs
        value={tab}
        onChange={(_e, v) => setActiveTab(v as QueueTab)}
        sx={{ mb: 2 }}
      >
        <Tab value="tv_alerts" label="TV Alerts" />
        <Tab value="waiting" label="Waiting Queue" />
        <Tab value="risk_mgmt" label="Risk management" />
        <Tab value="orders" label="Orders" />
        <Tab value="managed_exits" label="Managed exits" />
      </Tabs>

      <Box sx={{ display: tab === 'tv_alerts' ? 'block' : 'none' }}>
        <TvAlertsPanel embedded active={tab === 'tv_alerts'} />
      </Box>
      <Box sx={{ display: tab === 'waiting' ? 'block' : 'none' }}>
        <WaitingQueuePanel embedded active={tab === 'waiting'} />
      </Box>
      <Box sx={{ display: tab === 'risk_mgmt' ? 'block' : 'none' }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <AlertDecisionLogPanel
            title="Alert decision log (execution layer)"
            helpHash="alert-decision-log"
            limit={200}
            active={tab === 'risk_mgmt'}
          />
        </Box>
      </Box>
      <Box sx={{ display: tab === 'orders' ? 'block' : 'none' }}>
        <OrdersPanel embedded active={tab === 'orders'} />
      </Box>
      <Box sx={{ display: tab === 'managed_exits' ? 'block' : 'none' }}>
        <ManagedExitsPanel embedded active={tab === 'managed_exits'} />
      </Box>
    </Box>
  )
}
