import aboutDsl from '../../../docs/DSL_improvement.md?raw'
import alertsV3 from '../../../docs/alerts_refactor_v3.md?raw'
import alertSystemDesign from '../../../docs/alert_system_design.md?raw'
import brokerAngelone from '../../../docs/angelone_support_prework.md?raw'
import dashboard from '../../../docs/dashboard.md?raw'
import groupsUniverse from '../../../docs/groups_and_universe_design.md?raw'
import holdingsRefactor from '../../../docs/holdings_refactoring.md?raw'
import rebalanceHelp from '../../../docs/rebalance_dialog_help.md?raw'
import screener from '../../../docs/stock_screener.md?raw'
import strategySaving from '../../../docs/strategy_saving.md?raw'

export type DocMeta = {
  id: string
  title: string
  description: string
  content: string
  tags: string[]
}

export const DOCS: DocMeta[] = [
  {
    id: 'universe',
    title: 'Universe model (Holdings + Groups)',
    description:
      'How SigmaTrader unifies holdings, watchlists, baskets, portfolios, and overlays into one grid experience.',
    content: holdingsRefactor,
    tags: ['universe', 'holdings', 'groups', 'portfolio'],
  },
  {
    id: 'groups-universe',
    title: 'Groups & universe design',
    description:
      'Phase‑1 groups (watchlists/baskets/holdings views) and how they integrate into trading flows.',
    content: groupsUniverse,
    tags: ['groups', 'universe'],
  },
  {
    id: 'screener',
    title: 'Stock screener',
    description:
      'Dedicated screener page backed by Alerts V3 compiler/evaluator: targets, variables, runs, results.',
    content: screener,
    tags: ['screener', 'dsl'],
  },
  {
    id: 'alerts-v3',
    title: 'Alerts V3 (universe-scoped)',
    description:
      'Indicator-first alerts over universes, with explainability and event history.',
    content: alertsV3,
    tags: ['alerts', 'dsl', 'universe'],
  },
  {
    id: 'alert-system-design',
    title: 'Alert system design (expressions)',
    description:
      'Design of complex indicator expressions: AST, comparisons, AND/OR/NOT, multi-timeframe.',
    content: alertSystemDesign,
    tags: ['alerts', 'dsl'],
  },
  {
    id: 'dsl-improvement',
    title: 'DSL improvement',
    description:
      'Unifying the DSL mental model across Screener, Alerts, and Dashboard.',
    content: aboutDsl,
    tags: ['dsl'],
  },
  {
    id: 'strategy-saving',
    title: 'Strategy saving & reuse',
    description:
      'Saved Signal Strategies (DSL V3): reuse signals/overlays across Screener, Alerts, Dashboard.',
    content: strategySaving,
    tags: ['strategy', 'dsl'],
  },
  {
    id: 'rebalance-help',
    title: 'Rebalance help',
    description:
      'How to use target weights, signal rotation, and risk parity rebalancing safely.',
    content: rebalanceHelp,
    tags: ['rebalance', 'portfolio'],
  },
  {
    id: 'dashboard',
    title: 'Dashboard direction',
    description:
      'Basket indices + Symbol Explorer plan: explainability-first charts and DSL signals.',
    content: dashboard,
    tags: ['dashboard', 'analytics'],
  },
  {
    id: 'multi-broker',
    title: 'Multi-broker support prework',
    description:
      'How SigmaTrader becomes broker-aware while keeping groups/universes broker-agnostic.',
    content: brokerAngelone,
    tags: ['brokers', 'zerodha', 'angelone'],
  },
]

export function getDocById(id: string): DocMeta | undefined {
  return DOCS.find((d) => d.id === id)
}

