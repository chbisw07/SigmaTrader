# SigmaTrader website (local)

This folder contains a standalone, local-first marketing website for **SigmaTrader**.

## Prerequisites
- Node.js 18+ (recommended)

## Run locally
```bash
npm -C website install
npm -C website run roadmap:generate
npm -C website run dev
```

Then open `http://localhost:5174/`.

## “Open the app” button
The primary CTA links to the app at `http://localhost:5173/` (run the existing frontend separately).

## Screenshots
Place screenshots in:
- `website/public/assets/screenshots/`

Expected filenames (used across pages):
- `holdings-page.png`
- `screener.png`
- `alerts.png`
- `rebalance-preview.png`
- `queue.png`
- `brokers.png`

If a screenshot is missing, the site renders `website/public/assets/placeholder.svg` instead.

## Roadmap
`/roadmap` reads `docs/website/roadmap.json`.

Generate it from `docs/sprint_tasks_codex.xlsx`:
```bash
npm -C website run roadmap:generate
```

