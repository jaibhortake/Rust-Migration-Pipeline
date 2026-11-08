import { DiffEditor } from '@monaco-editor/react'
import { useMemo, useState } from 'react'
import type { Job, Project } from '../api'
import { Alert, Badge, Bar, Button, Card, cx, Empty, Icon, Pre, Ring, Stat, statusMeta } from '../components/ui'
import { fmtSecs, pct, type Theme } from '../hooks'

const confText = {
  high: 'High: every recorded input matches and the inputs reach ≥ 90% of the original\'s lines.',
  medium: 'Medium: every recorded input matches; 70–90% of the original\'s lines were exercised.',
  low: 'Low: every recorded input matches, but much of the original was never executed by the tests.',
  none: 'Not equivalent on the recorded tests.',
}

export default function Report({ project, job, theme }: { project: Project; job: Job | null; theme: Theme }) {
  const r = job?.result
  const rustFiles = useMemo(() => Object.keys(r?.files ?? {}).filter(f => f.endsWith('.rs')).sort((a, b) => (a === 'src/main.rs' ? 1 : b === 'src/main.rs' ? -1 : a.localeCompare(b))), [r])
  const [file, setFile] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  if (!job || !r) return <Empty title="No report yet">Run a migration first.</Empty>
  const current = file && r.files[file] ? file : rustFiles[0]
  const mod = r.modules.find(m => m.rust === current)
  const original = (mod?.files ?? Object.keys(r.original_files)).map(f => (mod && mod.files.length > 1 ? `// ===== ${f}\n` : '') + (r.original_files[f] ?? '')).join('\n\n')
  const ev = r.evidence, q = r.quality
  const meta = statusMeta[r.status]

  return (
    <div className="space-y-6">
      <div className={cx('rounded-xl border p-5 animate-slide-up', r.status === 'equivalent' ? 'border-emerald-200 bg-gradient-to-br from-emerald-50 to-white dark:border-emerald-900/50 dark:from-emerald-950/40 dark:to-zinc-900' : 'border-amber-200 bg-gradient-to-br from-amber-50 to-white dark:border-amber-900/50 dark:from-amber-950/30 dark:to-zinc-900')}>
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={meta?.tone} className="text-sm">{meta?.label ?? r.status}</Badge>
          {r.status === 'equivalent' && <Badge tone={r.confidence === 'high' ? 'green' : r.confidence === 'medium' ? 'blue' : 'amber'}>confidence: {r.confidence}</Badge>}
          <span className="text-sm text-zinc-600 dark:text-zinc-400">{fmtSecs(r.seconds)} · sandbox: {r.sandbox} · {r.usage.calls} LLM calls{r.usage.cached ? ` (+${r.usage.cached} cached)` : ''}</span>
          <div className="ml-auto flex gap-2">
            <Button onClick={() => { navigator.clipboard.writeText(r.files[current] ?? ''); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>{copied ? 'Copied' : 'Copy file'}</Button>
            <Button variant="primary" onClick={() => { window.location.href = `/api/jobs/${job.id}/download` }}>{Icon.download}Download Cargo project</Button>
          </div>
        </div>
        <p className="mt-3 text-sm">{confText[r.confidence]}</p>
        {r.message && <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{r.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Tests matching original" value={`${ev.tests_passed}/${ev.tests_total}`} tone={ev.tests_passed === ev.tests_total && ev.tests_total ? 'good' : 'bad'}
          hint={Object.entries(ev.inputs_by_origin).map(([k, v]) => `${v} ${k}`).join(' · ') || '—'} />
        <Stat label="Line coverage of original" value={pct(ev.line_coverage)} tone={(ev.line_coverage ?? 0) >= 0.9 ? 'good' : 'warn'} hint="lines the tests executed" />
        <Stat label="Branch coverage" value={pct(ev.branch_coverage)} tone={(ev.branch_coverage ?? 0) >= 0.8 ? 'good' : 'warn'} hint={ev.flaky_dropped ? `${ev.flaky_dropped} nondeterministic inputs dropped` : 'decision outcomes exercised'} />
        <Stat label="Repairs" value={r.attempts.module_fixes + r.attempts.verify_rounds - 1} hint={`${r.attempts.module_fixes} compile · ${Math.max(0, r.attempts.verify_rounds - 1)} behavioural`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        {q && (
          <Card title="Idiom & safety">
            <div className="flex items-center gap-6">
              <Ring value={q.score / 100} label="score" />
              <dl className="grid flex-1 grid-cols-2 gap-x-6 gap-y-2 text-sm">
                <dt className="text-zinc-500">unsafe</dt><dd className={cx('tabular-nums', q.unsafe ? 'text-red-600' : 'text-emerald-600')}>{q.unsafe}</dd>
                <dt className="text-zinc-500">clippy warnings</dt><dd className="tabular-nums">{q.clippy_warnings}</dd>
                <dt className="text-zinc-500">unwrap / expect</dt><dd className="tabular-nums">{q.unwraps}</dd>
                <dt className="text-zinc-500">clone()</dt><dd className="tabular-nums">{q.clones}</dd>
                <dt className="text-zinc-500">Rc / RefCell</dt><dd className="tabular-nums">{q.shared_mutability}</dd>
                <dt className="text-zinc-500">Rust LOC</dt><dd className="tabular-nums">{q.loc}</dd>
              </dl>
            </div>
            {r.attempts.refine_accepted && <p className="mt-3 text-xs text-emerald-700 dark:text-emerald-400">A clippy clean-up was applied after re-running every test.</p>}
            {Object.keys(q.clippy_by_lint).length > 0 && <div className="mt-3 flex flex-wrap gap-1">{Object.entries(q.clippy_by_lint).map(([k, v]) => <Badge key={k}>{k.replace('clippy::', '')} ×{v}</Badge>)}</div>}
          </Card>
        )}
        <Card title="Modules">
          <ul className="space-y-2">
            {r.modules.map(m => (
              <li key={m.id} className="flex items-center gap-3 text-sm">
                <span className={cx('h-2 w-2 rounded-full', m.status === 'failed' ? 'bg-red-500' : 'bg-emerald-500')} />
                <button className="font-mono text-xs hover:text-brand-600" onClick={() => setFile(m.rust)}>{m.rust}</button>
                <span className="truncate text-xs text-zinc-500">← {m.files.join(', ')}</span>
                {m.fixes > 0 && <Badge tone="amber" className="ml-auto">{m.fixes} fix{m.fixes > 1 ? 'es' : ''}</Badge>}
              </li>
            ))}
          </ul>
          {r.performance.ratio && (
            <div className="mt-4 border-t border-zinc-100 pt-3 text-sm dark:border-zinc-800">
              <div className="flex justify-between"><span className="text-zinc-500">Total wall time on tests</span><span className="tabular-nums">original {r.performance.original_s}s · Rust {r.performance.rust_s}s</span></div>
              <p className="mt-1 text-xs text-zinc-500">{r.performance.note}</p>
            </div>
          )}
        </Card>
      </div>

      {r.failures.length > 0 && (
        <Card title={`Remaining differences (${r.failures.length})`}>
          <div className="space-y-4">
            {r.failures.map((f, i) => (
              <div key={i} className="grid gap-3 md:grid-cols-3">
                <div><div className="mb-1 text-xs font-medium text-zinc-500">Input{f.minimized ? ' (minimised)' : ''}</div><Pre>{f.minimized || f.stdin || '(empty)'}</Pre></div>
                <div><div className="mb-1 text-xs font-medium text-zinc-500">Original output</div><Pre>{f.expected || '(empty)'}</Pre></div>
                <div><div className="mb-1 text-xs font-medium text-zinc-500">Rust output</div><Pre>{f.actual || '(empty)'}</Pre></div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {Object.keys(ev.uncovered).length > 0 && (
        <Alert tone="amber">Never executed by any test (review these by hand): {Object.entries(ev.uncovered).map(([f, ls]) => `${f} lines ${ls.slice(0, 15).join(', ')}${ls.length > 15 ? '…' : ''}`).join('; ')}</Alert>
      )}

      {rustFiles.length > 0 && (
        <Card pad={false} title="Side-by-side" action={
          <div className="flex flex-wrap gap-1">
            {rustFiles.map(f => <button key={f} onClick={() => setFile(f)} className={cx('rounded-md px-2 py-1 font-mono text-xs transition-colors', f === current ? 'bg-brand-600 text-white' : 'hover:bg-zinc-100 dark:hover:bg-zinc-800')}>{f.replace('src/', '')}</button>)}
          </div>}>
          <div className="flex border-b border-zinc-100 text-xs text-zinc-500 dark:border-zinc-800">
            <span className="w-1/2 px-4 py-1.5">{mod ? mod.files.join(' + ') : 'original'}</span><span className="w-1/2 px-4 py-1.5">{current}</span>
          </div>
          <div className="h-[34rem]">
            <DiffEditor original={original} modified={r.files[current] ?? ''} originalLanguage={project.language === 'cpp' ? 'cpp' : 'python'} modifiedLanguage="rust"
              theme={theme === 'dark' ? 'vs-dark' : 'light'}
              options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false }, fontSize: 12.5, scrollBeyondLastLine: false, automaticLayout: true, renderOverviewRuler: false, ignoreTrimWhitespace: true }} />
          </div>
        </Card>
      )}

      {r.tests.length > 0 && (
        <Card title={`Recorded tests (${r.tests.length})`} action={<span className="text-xs text-zinc-500">included in the download as a cargo test suite</span>}>
          <div className="grid max-h-80 gap-2 overflow-auto sm:grid-cols-2 xl:grid-cols-3">
            {r.tests.map((t, i) => (
              <details key={i} className="rounded-lg border border-zinc-100 p-2 text-xs dark:border-zinc-800">
                <summary className="flex cursor-pointer items-center gap-2"><span className="tabular-nums text-zinc-400">#{i + 1}</span><Badge>{t.origin}</Badge><span className="truncate font-mono">{t.stdin.replace(/\n/g, ' ⏎ ').slice(0, 40)}</span></summary>
                <div className="mt-2 grid gap-2"><Pre>{t.stdin}</Pre><Pre>{t.expected}</Pre></div>
              </details>
            ))}
          </div>
          <div className="mt-3"><Bar value={ev.tests_total ? ev.tests_passed / ev.tests_total : 0} tone={ev.tests_passed === ev.tests_total ? 'green' : 'amber'} /></div>
        </Card>
      )}
    </div>
  )
}
