import { useEffect, useState } from 'react'
import { api, type Benchmark as B } from '../api'
import { Badge, Card, Empty, Stat, statusMeta } from '../components/ui'
import { pct } from '../hooks'

export default function Benchmark({ onError }: { onError: (e: unknown) => void }) {
  const [b, setB] = useState<B | null>(null)
  useEffect(() => { api.benchmark().then(setB).catch(onError) }, [onError])
  if (!b) return <div className="mx-auto max-w-6xl space-y-3 p-6"><div className="skeleton h-8 w-48" /><div className="skeleton h-64" /></div>
  if (!b.available || !b.rows) return (
    <div className="mx-auto max-w-3xl p-6">
      <Empty title="No benchmark results yet">Run <code className="font-mono">python -m scripts.benchmark</code> in <code>backend/</code>. It migrates every sample with the full pipeline and with a one-shot LLM baseline, and scores both on the same recorded tests.</Empty>
    </div>
  )
  const t = b.totals ?? {}
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <div className="animate-fade-in">
        <h1 className="text-2xl font-semibold tracking-tight">Benchmark</h1>
        <p className="mt-1 text-sm text-zinc-500">{b.rows.length} programs · model {b.model} · {b.generated}. Baseline = one LLM call, no analysis or repair, scored on the same recorded tests.</p>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Pipeline: equivalent" value={`${t.pipeline_equivalent ?? 0}/${b.rows.length}`} tone="good" hint={pct((t.pipeline_equivalent ?? 0) / b.rows.length)} />
        <Stat label="Baseline: equivalent" value={`${t.baseline_equivalent ?? 0}/${b.rows.length}`} hint={pct((t.baseline_equivalent ?? 0) / b.rows.length)} />
        <Stat label="Mean line coverage" value={pct(t.mean_line_coverage)} hint="of the originals, by the recorded tests" />
        <Stat label="Mean quality score" value={t.mean_quality != null ? Math.round(t.mean_quality) : '—'} hint="clippy / unsafe / unwrap density" />
      </div>
      {t.ablations && Object.keys(t.ablations).length > 0 && (
        <Card title="What each feature contributes" pad={false} action={<span className="text-xs text-zinc-500">same programs, one feature switched off at a time</span>}>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-zinc-500"><tr><th className="px-4 py-2 font-medium">Configuration</th><th className="font-medium">Equivalent</th><th className="font-medium">Mean coverage</th><th className="px-4 font-medium">Mean quality</th></tr></thead>
            <tbody>
              <tr className="border-t border-zinc-100 dark:border-zinc-800"><td className="px-4 py-2 font-medium">full pipeline</td><td className="tabular-nums">{t.pipeline_equivalent}/{b.rows.length}</td><td className="tabular-nums">{pct(t.mean_line_coverage)}</td><td className="px-4 tabular-nums">{t.mean_quality != null ? Math.round(t.mean_quality) : '—'}</td></tr>
              {Object.entries(t.ablations).map(([k, v]) => (
                <tr key={k} className="border-t border-zinc-100 dark:border-zinc-800"><td className="px-4 py-2 font-mono text-xs">{k}</td><td className="tabular-nums">{v.equivalent}/{t.programs ?? 0}</td><td className="tabular-nums">{pct(v.mean_line_coverage)}</td><td className="px-4 tabular-nums">{v.mean_quality != null ? Math.round(v.mean_quality) : '—'}</td></tr>
              ))}
              <tr className="border-t border-zinc-100 dark:border-zinc-800"><td className="px-4 py-2 font-medium">one-shot LLM baseline</td><td className="tabular-nums">{t.baseline_equivalent}/{b.rows.length}</td><td className="text-zinc-400">—</td><td className="px-4 text-zinc-400">—</td></tr>
            </tbody>
          </table>
        </Card>
      )}
      <Card pad={false}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-zinc-500"><tr>
              <th className="px-4 py-2 font-medium">Program</th><th className="font-medium">LOC</th><th className="font-medium">Pipeline</th><th className="font-medium">Tests</th>
              <th className="font-medium">Coverage</th><th className="font-medium">Quality</th><th className="font-medium">Baseline</th><th className="px-4 font-medium">Time</th></tr></thead>
            <tbody>
              {b.rows.map(r => (
                <tr key={r.name} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="px-4 py-2"><span className="font-medium">{r.name}</span> <Badge>{r.language === 'cpp' ? 'C++' : 'Py'}</Badge> {r.kind === 'project' && <Badge tone="brand">multi-file</Badge>}</td>
                  <td className="tabular-nums">{r.loc}</td>
                  <td><Badge tone={statusMeta[r.pipeline.status]?.tone}>{statusMeta[r.pipeline.status]?.label ?? r.pipeline.status}</Badge></td>
                  <td className="tabular-nums">{r.pipeline.tests_passed}/{r.pipeline.tests_total}</td>
                  <td className="tabular-nums">{pct(r.pipeline.line_coverage)}</td>
                  <td className="tabular-nums">{r.pipeline.quality ?? '—'}</td>
                  <td><Badge tone={r.baseline.status === 'equivalent' ? 'green' : r.baseline.status === 'partial' ? 'amber' : 'red'}>{r.baseline.tests_passed}/{r.baseline.tests_total}</Badge></td>
                  <td className="px-4 tabular-nums text-zinc-500">{Math.round(r.pipeline.seconds)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
