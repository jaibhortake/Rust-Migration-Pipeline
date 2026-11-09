import Editor from '@monaco-editor/react'
import { useMemo, useState } from 'react'
import type { Project, Severity } from '../api'
import DepGraph from '../components/DepGraph'
import { Alert, Badge, Bar, Card, cx, Stat } from '../components/ui'
import type { Theme } from '../hooks'

const sevTone = { high: 'red', medium: 'amber', low: 'zinc' } as const
const readinessTone = { easy: 'green', moderate: 'blue', hard: 'amber', blocked: 'red' } as const

export default function Assessment({ project, theme }: { project: Project; theme: Theme }) {
  const a = project.assessment
  const s = a.summary
  const [sev, setSev] = useState<Severity | 'all'>('all')
  const [file, setFile] = useState(Object.keys(project.files)[0])
  const [line, setLine] = useState<number | undefined>()
  const risks = useMemo(() => a.risks.filter(r => sev === 'all' || r.severity === sev), [a.risks, sev])
  const unitsInOrder = a.graph.order.flat().map(id => a.units.find(u => u.id === id)!).filter(Boolean)

  return (
    <div className="space-y-6">
      <div className={cx('flex flex-wrap items-center gap-3 rounded-xl border p-4 animate-slide-up',
        s.readiness === 'blocked' ? 'border-red-200 bg-red-50 dark:border-red-900/50 dark:bg-red-950/30' : 'border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/60')}>
        <Badge tone={readinessTone[s.readiness]} className="text-sm">{s.readiness}</Badge>
        <span className="text-sm">{s.verdict}</span>
        {s.single_function && <Badge tone="blue">function-only input: a driver will be generated</Badge>}
      </div>
      {s.blockers.map(b => <Alert key={b}>{b}</Alert>)}
      {s.unsupported.length > 0 && <Alert tone="amber">Unsupported for verified migration: {s.unsupported.join(', ')} (see Library mapping).</Alert>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Source files" value={s.files} hint={`${s.units} Rust modules`} />
        <Stat label="Lines of code" value={s.loc.toLocaleString()} hint={`${s.functions} functions`} />
        <Stat label="Classes" value={s.classes} hint="see Class mapping" />
        <Stat label="High-risk constructs" value={s.risks.high} tone={s.risks.high ? 'bad' : 'good'} hint={`${s.risks.medium} medium · ${s.risks.low} low`} />
        <Stat label="Library coverage" value={`${Math.round(s.library_coverage * 100)}%`} tone={s.library_coverage >= 0.9 ? 'good' : 'warn'} hint="mapped to std / allowed crates" />
        <Stat label="Manual effort" value={`${s.manual_hours}h`} hint="heuristic: 30 LOC/h × risk" />
      </div>

      {(s.manifest?.requirements || s.manifest?.cmake || s.reads_stdin === false) && (
        <Card title="Project manifest">
          <div className="space-y-2 text-sm">
            {s.manifest?.cmake && <p><b>CMakeLists.txt</b>: C++{s.manifest.cmake.std ?? 'default'}{s.manifest.cmake.selected_target ? <>, migrating target <code className="font-mono">{s.manifest.cmake.selected_target}</code> of {s.manifest.cmake.targets.length}</> : null}{s.manifest.cmake.include_dirs.length ? <>, include dirs: {s.manifest.cmake.include_dirs.join(', ')}</> : null}</p>}
            {s.manifest?.requirements && <p><b>requirements.txt</b>: {s.manifest.requirements.join(', ') || 'none'}</p>}
            {s.reads_stdin === false && <p><b>No input:</b> the program never reads stdin, so its behaviour is one deterministic run. Test generation is skipped and the output is compared once.</p>}
          </div>
        </Card>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card title="Dependency graph" action={<span className="text-xs text-zinc-500">migrated left → right · hover to trace</span>}>
          <DepGraph units={a.units} order={a.graph.order} />
          {a.graph.cycles.length > 0 && <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">Cycles: {a.graph.cycles.map(c => c.join(' ↔ ')).join('; ')} (translated together).</p>}
        </Card>
        <Card title="Migration order" pad={false}>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-zinc-500"><tr><th className="px-4 py-2 font-medium">#</th><th className="font-medium">Module</th><th className="font-medium">LOC</th><th className="w-28 pr-4 font-medium">Difficulty</th></tr></thead>
            <tbody>
              {unitsInOrder.map((u, i) => (
                <tr key={u.id} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="px-4 py-2 text-zinc-400 tabular-nums">{i + 1}</td>
                  <td className="py-2"><div className="font-medium">{u.is_entry ? 'main.rs' : `${u.id}.rs`}</div><div className="font-mono text-xs text-zinc-500">{u.files.join(', ')}</div></td>
                  <td className="tabular-nums">{u.loc}</td>
                  <td className="pr-4"><div className="flex items-center gap-2"><Bar value={u.difficulty / 100} tone={u.difficulty < 30 ? 'green' : u.difficulty < 60 ? 'amber' : 'red'} /><span className="w-6 text-xs tabular-nums">{u.difficulty}</span></div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_1.1fr]">
        <Card title={`Risks & semantic hazards (${a.risks.length})`}
          action={<select value={sev} onChange={e => setSev(e.target.value as Severity | 'all')} className="h-8 rounded-md border border-zinc-200 bg-transparent px-2 text-xs dark:border-zinc-700">
            <option value="all">All</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>}>
          {risks.length === 0 ? <p className="text-sm text-zinc-500">No risky constructs found.</p> : (
            <ul className="max-h-[32rem] space-y-2 overflow-auto pr-1">
              {risks.map((r, i) => (
                <li key={i}>
                  <button onClick={() => { setFile(r.file); setLine(r.line) }} className="w-full rounded-lg border border-zinc-100 p-3 text-left transition-colors hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:border-zinc-700 dark:hover:bg-zinc-800/50">
                    <div className="flex items-center gap-2"><Badge tone={sevTone[r.severity]}>{r.severity}</Badge><span className="text-sm font-medium">{r.title}</span>
                      <span className="ml-auto font-mono text-xs text-zinc-500">{r.file}:{r.line}</span></div>
                    <p className="mt-1.5 text-xs text-zinc-600 dark:text-zinc-400">{r.why}</p>
                    <p className="mt-1 text-xs"><span className="font-medium text-brand-700 dark:text-brand-400">Rust strategy: </span>{r.strategy}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Source" pad={false} action={
          <select value={file} onChange={e => { setFile(e.target.value); setLine(undefined) }} className="h-8 max-w-56 rounded-md border border-zinc-200 bg-transparent px-2 font-mono text-xs dark:border-zinc-700">
            {Object.keys(project.files).map(f => <option key={f}>{f}</option>)}
          </select>}>
          <div className="h-[32rem]">
            <Editor key={file} path={file} language={project.language === 'cpp' ? 'cpp' : 'python'} value={project.files[file]} theme={theme === 'dark' ? 'vs-dark' : 'light'} line={line}
              options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12.5, scrollBeyondLastLine: false, automaticLayout: true }} />
          </div>
        </Card>
      </div>
    </div>
  )
}
