import { Routes, Route } from 'react-router-dom'

import { DashboardPage } from '../views/DashboardPage'
import { QueuePage } from '../views/QueuePage'
import { OrdersPage } from '../views/OrdersPage'
import { AnalyticsPage } from '../views/AnalyticsPage'
import { SettingsPage } from '../views/SettingsPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/queue" element={<QueuePage />} />
      <Route path="/orders" element={<OrdersPage />} />
      <Route path="/analytics" element={<AnalyticsPage />} />
      <Route path="/settings" element={<SettingsPage />} />
    </Routes>
  )
}
