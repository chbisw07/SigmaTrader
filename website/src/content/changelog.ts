export type ChangelogEntry = {
  date: string
  title: string
  bullets: string[]
}

export const CHANGELOG: ChangelogEntry[] = [
  {
    date: '2025-12-25',
    title: 'Portfolio rebalancing suite',
    bullets: [
      'Target-weight rebalancing with budgets + drift bands + trade caps.',
      'Signal-driven rotation (Top-N) using saved strategy outputs and filters.',
      'Risk parity (equal risk contribution) targets with covariance caching.',
      'History + schedule support for portfolio groups.',
      'In-app help modal with properly rendered documentation.',
    ],
  },
]

