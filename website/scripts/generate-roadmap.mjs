import fs from 'node:fs'
import path from 'node:path'
import xlsx from 'xlsx'

const repoRoot = path.resolve(import.meta.dirname, '..', '..')
const xlsxPath = path.join(repoRoot, 'docs', 'sprint_tasks_codex.xlsx')
const outDir = path.join(repoRoot, 'docs', 'website')
const outPath = path.join(outDir, 'roadmap.json')

function main() {
  if (!fs.existsSync(xlsxPath)) {
    console.error(`Missing file: ${xlsxPath}`)
    process.exit(1)
  }

  const wb = xlsx.readFile(xlsxPath)
  const sheetName = wb.SheetNames[0]
  if (!sheetName) throw new Error('No sheets found in sprint_tasks_codex.xlsx')
  const ws = wb.Sheets[sheetName]
  const rows = xlsx.utils.sheet_to_json(ws, { header: 1, raw: false })

  // Expected columns (by current file shape):
  // 0 sprint#, 1 group#, 2 group task description., 3 task#, 4 task description,
  // 5 deviations, 6 status, 7 remarks, 8 pending work
  const items = []
  for (let i = 1; i < rows.length; i++) {
    const r = rows[i] ?? []
    const sprint = (r[0] ?? '').toString().trim()
    const group = (r[1] ?? '').toString().trim()
    const groupDesc = (r[2] ?? '').toString().trim()
    const taskId = (r[3] ?? '').toString().trim()
    const taskDesc = (r[4] ?? '').toString().trim()
    const status = (r[6] ?? '').toString().trim()
    const remarks = (r[7] ?? '').toString().trim()

    if (!taskId) continue
    items.push({
      sprint,
      group,
      groupDesc,
      taskId,
      taskDesc,
      status,
      remarks,
    })
  }

  const grouped = new Map()
  for (const it of items) {
    const key = it.sprint || 'UNKNOWN'
    if (!grouped.has(key)) grouped.set(key, [])
    grouped.get(key).push(it)
  }

  const result = {
    generated_at: new Date().toISOString(),
    source: 'docs/sprint_tasks_codex.xlsx',
    sprints: Array.from(grouped.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([sprint, tasks]) => ({
        sprint,
        tasks,
      })),
  }

  fs.mkdirSync(outDir, { recursive: true })
  fs.writeFileSync(outPath, JSON.stringify(result, null, 2))
  console.log(`Wrote ${outPath} (${items.length} tasks)`)
}

main()

