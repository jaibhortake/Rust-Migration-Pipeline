import type { PipelineEvent } from '../api'
import { pct } from '../hooks'
import { cx, Icon, Pre, Spinner } from './ui'

const STAGES: { id: string; label: string; help: string }[] = [
  { id: 'prepare', label: 'Prepare', help: 'Re-analyse the project; wrap function-only input in a driver' },
  { id: 'build_original', label: 'Build original', help: 'Compile the original twice: optimised and coverage-instrumented' },
  { id: 'tests', label: 'Generate tests', help: 'LLM seeds, mutation fuzzing and coverage-targeted inputs; outputs recorded from the real original' },
  { id: 'translate', label: 'Translate modules', help: 'Leaves first, following the contract; each group must compile before the next' },
  { id: 'compile', label: 'Build crate', help: 'cargo build of the whole crate, with compiler-guided repair' },
  { id: 'verify', label: 'Differential testing', help: 'Run Rust and original on every input and compare; minimise failures and repair' },
  { id: 'unit', label: 'Function-level checks', help: 'Call individual functions in the original and in Rust with generated arguments (optional)' },
  { id: 'quality', label: 'Quality', help: 'clippy + rustfmt; clippy fixes are kept only if every test still passes' },
]

type State = 'pending' | 'running' | 'ok' | 'failed'

export function stageStates(events: PipelineEvent[]) {
  const st: Record<string, { state: State; last?: PipelineEvent; log: PipelineEvent[] }> = {}
  for (const s of STAGES) st[s.id] = { state: 'pending', log: [] }
  for (const e of events) {
    const s = st[e.stage]
    if (!s) continue
    s.log.push(e)
    s.last = e
    s.state = e.status === 'running' ? 'running' : e.status === 'ok' ? 'ok' : 'failed'
  }
  const done = events.find(e => e.stage === 'done')
  if (done) for (const s of Object.values(st)) if (s.state === 'running') s.state = done.status === 'equivalent' ? 'ok' : 'failed'
  return st
}

function detail(id: string, e?: PipelineEvent): string {
  if (!e) return ''
  if (id === 'tests' && e.count != null) return `${e.count} inputs · ${pct(e.line_coverage as number)} lines · ${pct(e.branch_coverage as number)} branches`
  if (id === 'tests' && e.phase) return `${e.phase}${e.line_coverage != null ? ` · ${pct(e.line_coverage as number)} lines` : ''}`
  if (id === 'translate' && e.module) return `${e.fix_attempt ? `repairing ${e.module} (attempt ${e.fix_attempt})` : `${e.status === 'ok' ? 'compiled' : 'module'} ${e.module}`}`
  if (id === 'verify' && e.total != null) return `${e.passed}/${e.total} match · round ${e.round}`
  if (id === 'verify' && e.phase) return String(e.phase)
  if (id === 'compile' && e.fix_attempt) return `repairing compile errors (attempt ${e.fix_attempt})`
  if (id === 'compile' && e.round) return `round ${e.round}`
  if (id === 'unit' && e.total != null) return `${e.passed}/${e.total} call sequences match`
  if (id === 'unit' && e.phase) return String(e.phase)
  if (id === 'quality' && e.score != null) return `score ${e.score}/100 · ${e.clippy} clippy warnings`
  if (id === 'prepare' && e.note) return String(e.note)
  if (id === 'prepare' && e.units) return `${e.units} modules`
  return ''
}

export default function Timeline({ events }: { events: PipelineEvent[] }) {
  const st = stageStates(events)
  return (
    <ol className="relative space-y-1">
      {STAGES.map((s, i) => {
        const { state, last, log } = st[s.id]
        const errors = [...log].reverse().find(e => e.errors)?.errors
        return (
          <li key={s.id} className="relative flex gap-3 pb-3 animate-fade-in">
            {i < STAGES.length - 1 && <span className={cx('absolute top-7 left-[13px] h-[calc(100%-20px)] w-px', state === 'ok' ? 'bg-emerald-300 dark:bg-emerald-800' : 'bg-zinc-200 dark:bg-zinc-800')} />}
            <span className={cx('z-10 grid h-7 w-7 shrink-0 place-items-center rounded-full ring-4 ring-white transition-colors dark:ring-zinc-900',
              state === 'ok' && 'bg-emerald-500 text-white', state === 'failed' && 'bg-red-500 text-white',
              state === 'running' && 'bg-sky-500 text-white', state === 'pending' && 'bg-zinc-100 text-zinc-400 dark:bg-zinc-800')}>
              {state === 'ok' ? Icon.check : state === 'failed' ? Icon.x : state === 'running' ? <Spinner className="h-3.5 w-3.5" /> : <span className="text-xs">{i + 1}</span>}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex items-baseline gap-2">
                <span className={cx('text-sm font-medium', state === 'pending' && 'text-zinc-400')}>{s.label}</span>
                <span className="truncate text-xs text-zinc-500">{detail(s.id, last)}</span>
              </div>
              {state === 'pending' && <div className="text-xs text-zinc-400">{s.help}</div>}
              {Boolean(errors) && state !== 'ok' && <details className="mt-1"><summary className="cursor-pointer text-xs text-red-600 dark:text-red-400">compiler / error output</summary><Pre className="mt-1">{String(errors)}</Pre></details>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
