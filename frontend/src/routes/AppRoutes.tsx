import { Routes, Route } from 'react-router-dom'

import { DashboardPage } from '../views/DashboardPage'
import { QueuePage } from '../views/QueuePage'
import { OrdersPage } from '../views/OrdersPage'
import { AnalyticsPage } from '../views/AnalyticsPage'
import { SettingsPage } from '../views/SettingsPage'
import { PositionsPage } from '../views/PositionsPage'
import { HoldingsPage } from '../views/HoldingsPage'
import { SystemEventsPage } from '../views/SystemEventsPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/queue" element={<QueuePage />} />
      <Route path="/orders" element={<OrdersPage />} />
      <Route path="/positions" element={<PositionsPage />} />
      <Route path="/holdings" element={<HoldingsPage />} />
      <Route path="/analytics" element={<AnalyticsPage />} />
      <Route path="/system-events" element={<SystemEventsPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      {/* /auth is handled at the App.tsx level */}
    </Routes>
  )
}
