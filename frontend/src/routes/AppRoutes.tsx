import { Routes, Route, Navigate } from 'react-router-dom'

import { DashboardPage } from '../views/DashboardPage'
import { QueueManagementPage } from '../views/QueueManagementPage'
import { AnalyticsPage } from '../views/AnalyticsPage'
import { SettingsPage } from '../views/SettingsPage'
import { PositionsPage } from '../views/PositionsPage'
import { HoldingsPage } from '../views/HoldingsPage'
import { SystemEventsPage } from '../views/SystemEventsPage'
import { AppearancePage } from '../views/AppearancePage'
import { AlertsPage } from '../views/AlertsPage'
import { GroupsPage } from '../views/GroupsPage'
import { ScreenerPage } from '../views/ScreenerPage'
import { BacktestingPage } from '../views/BacktestingPage'
import { DeploymentsPage } from '../views/DeploymentsPage'
import { DeploymentDetailsPage } from '../views/DeploymentDetailsPage'
import { RiskManagementGuidePage } from '../views/RiskManagementGuidePage'
import { ExceptionsCenterPage } from '../views/ExceptionsCenterPage'
import { DecisionTracePage } from '../views/DecisionTracePage'
import { PlaybooksPage } from '../views/PlaybooksPage'
import { AiTradingManagerPage } from '../views/AiTradingManagerPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<DashboardPage />} />
      <Route path="/queue" element={<QueueManagementPage />} />
      <Route
        path="/orders"
        element={<Navigate to="/queue?tab=orders" replace />}
      />
      <Route path="/positions" element={<PositionsPage />} />
      <Route path="/holdings" element={<HoldingsPage />} />
      <Route path="/screener" element={<ScreenerPage />} />
      <Route path="/groups" element={<GroupsPage />} />
      <Route path="/alerts" element={<AlertsPage />} />
      <Route path="/backtesting" element={<BacktestingPage />} />
      <Route path="/deployments" element={<DeploymentsPage />} />
      <Route path="/deployments/:id" element={<DeploymentDetailsPage />} />
      <Route path="/analytics" element={<AnalyticsPage />} />
      <Route path="/system-events" element={<SystemEventsPage />} />
      <Route path="/appearance" element={<AppearancePage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/risk-guide" element={<RiskManagementGuidePage />} />
      <Route path="/ai" element={<AiTradingManagerPage />} />
      <Route path="/ai/exceptions" element={<ExceptionsCenterPage />} />
      <Route path="/ai/decision-traces/:decisionId" element={<DecisionTracePage />} />
      <Route path="/ai/playbooks" element={<PlaybooksPage />} />
      {/* /auth is handled at the App.tsx level */}
    </Routes>
  )
}
