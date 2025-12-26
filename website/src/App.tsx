import Box from '@mui/material/Box'
import { Route, Routes } from 'react-router-dom'

import { SiteLayout } from './components/SiteLayout'
import { AboutPage } from './pages/AboutPage'
import { ChangelogPage } from './pages/ChangelogPage'
import { DocsIndexPage } from './pages/DocsIndexPage'
import { DocPage } from './pages/DocPage'
import { ExecutionPage } from './pages/ExecutionPage'
import { FeatureAlertsPage } from './pages/FeatureAlertsPage'
import { FeatureBrokersPage } from './pages/FeatureBrokersPage'
import { FeatureRebalancePage } from './pages/FeatureRebalancePage'
import { FeatureScreenerPage } from './pages/FeatureScreenerPage'
import { FeatureUniversePage } from './pages/FeatureUniversePage'
import { HelpPage } from './pages/HelpPage'
import { HomePage } from './pages/HomePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PlatformPage } from './pages/PlatformPage'
import { ProductPage } from './pages/ProductPage'
import { RoadmapPage } from './pages/RoadmapPage'

export function App() {
  return (
    <Box sx={{ minHeight: '100vh' }}>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route index element={<HomePage />} />
          <Route path="/product" element={<ProductPage />} />
          <Route path="/platform" element={<PlatformPage />} />
          <Route path="/features/universe" element={<FeatureUniversePage />} />
          <Route path="/features/screener" element={<FeatureScreenerPage />} />
          <Route path="/features/alerts" element={<FeatureAlertsPage />} />
          <Route path="/features/execution" element={<ExecutionPage />} />
          <Route path="/features/rebalance" element={<FeatureRebalancePage />} />
          <Route path="/features/brokers" element={<FeatureBrokersPage />} />
          <Route path="/docs" element={<DocsIndexPage />} />
          <Route path="/docs/:docId" element={<DocPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="/roadmap" element={<RoadmapPage />} />
          <Route path="/changelog" element={<ChangelogPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Box>
  )
}

