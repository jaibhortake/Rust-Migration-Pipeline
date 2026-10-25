import { useState } from 'react'
import type { PipelineEvent } from './api'
export const STAGES = ['parse', 'analyze', 'tests', 'translate', 'compile', 'verify', 'report', 'done']
type St = 'pending' | 'running' | 'ok' | 'failed'
const dot: Record<St, string> = { pending: 'bg-slate-300 dark:bg-slate-700', running: 'bg-blue-500 animate-pulse', ok: 'bg-green-500', failed: 'bg-red-500' }

export default function Timeline({ events }: { events: PipelineEvent[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  return (
    <ol className="space-y-1">
      {STAGES.map(s => {
        const evs = events.filter(e => e.stage === s)
        const last = evs[evs.length - 1]
        const st: St = last ? last.status : 'pending'
        const attempts = Math.max(0, ...evs.map(e => Number(e.attempt ?? 0)))
        const v = [...evs].reverse().find(e => e.passed !== undefined && e.total !== undefined)
        const errs = evs.filter(e => e.errors)
        return (
          <li key={s} className="rounded-lg px-2 py-1.5">
            <div className="flex items-center gap-2 text-sm">
              <span className={`h-2.5 w-2.5 rounded-full ${dot[st]}`} />
              <span className={`capitalize ${st === 'pending' ? 'text-slate-400' : ''}`}>{s}</span>
              {attempts > 1 && <span className="text-xs rounded bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 px-1.5">attempt {attempts}</span>}
              {v && <span className="text-xs text-slate-500">{String(v.passed)}/{String(v.total)} tests</span>}
              {errs.length > 0 && <button className="ml-auto text-xs text-red-500 hover:underline" onClick={() => setOpen(o => ({ ...o, [s]: !o[s] }))}>{open[s] ? 'hide' : 'show'} errors</button>}
            </div>
            {open[s] && errs.map((e, i) => (
              <pre key={i} className="mt-1 max-h-48 overflow-auto rounded bg-slate-100 dark:bg-slate-900 p-2 text-xs text-red-600 dark:text-red-400 whitespace-pre-wrap">{e.attempt ? `# attempt ${e.attempt}\n` : ''}{e.errors}</pre>
            ))}
          </li>
        )
      })}
    </ol>
  )
}
