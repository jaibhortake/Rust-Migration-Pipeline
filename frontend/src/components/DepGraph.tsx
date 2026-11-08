import { useMemo, useState } from 'react'
import type { Unit } from '../api'

/** Layered dependency graph: leaves on the left, the entry module on the right. Colour = difficulty. */
export default function DepGraph({ units, order, status }: { units: Unit[]; order: string[][]; status?: Record<string, string> }) {
  const [hover, setHover] = useState<string | null>(null)
  const layout = useMemo(() => {
    const byId = Object.fromEntries(units.map(u => [u.id, u]))
    const depth: Record<string, number> = {}
    for (const grp of order) {
      for (const id of grp) {
        const ds = (byId[id]?.deps ?? []).filter(d => d in depth && !grp.includes(d)).map(d => depth[d] + 1)
        depth[id] = Math.max(0, ...ds)
      }
    }
    const cols: string[][] = []
    for (const grp of order) for (const id of grp) (cols[depth[id]] ??= []).push(id)
    const W = 156, H = 46, GX = 64, GY = 18
    const pos: Record<string, { x: number; y: number }> = {}
    const maxRows = Math.max(1, ...cols.map(c => c.length))
    cols.forEach((c, i) => c.forEach((id, j) => {
      const offset = ((maxRows - c.length) * (H + GY)) / 2
      pos[id] = { x: 12 + i * (W + GX), y: 12 + offset + j * (H + GY) }
    }))
    return { pos, W, H, width: 24 + cols.length * (W + GX) - GX, height: 24 + maxRows * (H + GY) - GY, byId }
  }, [units, order])

  const { pos, W, H, byId } = layout
  const color = (d: number) => (d < 30 ? '#10b981' : d < 60 ? '#f59e0b' : '#ef4444')
  const stateColor = (s?: string) => s === 'compiles' ? '#10b981' : s === 'failed' ? '#ef4444' : s === 'working' ? '#0ea5e9' : undefined
  const related = (id: string) => !hover || id === hover || byId[hover]?.deps.includes(id) || byId[id]?.deps.includes(hover)

  return (
    <div className="overflow-x-auto">
      <svg width={layout.width} height={layout.height} className="mx-auto block" role="img" aria-label="Module dependency graph">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" className="fill-zinc-400 dark:fill-zinc-500" />
          </marker>
        </defs>
        {units.flatMap(u => u.deps.filter(d => pos[d]).map(d => {
          const a = pos[d], b = pos[u.id]
          const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x - 2, y2 = b.y + H / 2
          const mx = (x1 + x2) / 2
          const on = !hover || hover === u.id || hover === d
          return <path key={u.id + d} d={`M${x1} ${y1} C${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`} fill="none" markerEnd="url(#arrow)"
            className="stroke-zinc-300 transition-opacity dark:stroke-zinc-600" strokeWidth="1.5" opacity={on ? 1 : 0.15} />
        }))}
        {units.map(u => {
          const p = pos[u.id]
          if (!p) return null
          const sc = stateColor(status?.[u.id])
          return (
            <g key={u.id} transform={`translate(${p.x},${p.y})`} onMouseEnter={() => setHover(u.id)} onMouseLeave={() => setHover(null)}
              className="cursor-default transition-opacity" opacity={related(u.id) ? 1 : 0.3}>
              <title>{`${u.files.join(', ')}\n${u.loc} lines · difficulty ${u.difficulty}/100`}</title>
              <rect width={W} height={H} rx="10" className="fill-white stroke-zinc-200 dark:fill-zinc-900 dark:stroke-zinc-700" strokeWidth="1.5" />
              <rect width="4" height={H - 16} x="8" y="8" rx="2" fill={sc ?? color(u.difficulty)} />
              <text x="20" y="20" className="fill-zinc-900 text-[12px] font-semibold dark:fill-zinc-100">{u.is_entry ? 'main' : u.id.length > 17 ? u.id.slice(0, 16) + '…' : u.id}</text>
              <text x="20" y="35" className="fill-zinc-500 text-[10.5px]">{u.loc} loc · diff {u.difficulty}{u.is_entry ? ' · entry' : ''}</text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
