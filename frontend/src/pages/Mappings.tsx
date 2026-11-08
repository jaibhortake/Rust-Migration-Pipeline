import { useEffect, useState } from 'react'
import { api, type Mappings as M, type Project } from '../api'
import { Badge, Button, Card, Empty, Spinner, Tabs } from '../components/ui'

const kindTone = { std: 'green', crate: 'blue', manual: 'amber', unsupported: 'red' } as const
const strategyHelp: Record<string, string> = {
  struct: 'struct + impl', data: 'derived data struct', trait: 'trait (+ base struct)', implementor: 'struct implementing a trait',
  enum: 'enum, one variant per subclass', composition: 'struct embedding its base', error: 'error enum variant',
}
const input = 'w-full rounded-md border border-transparent bg-transparent px-2 py-1 font-mono text-xs outline-none transition hover:border-zinc-200 focus:border-brand-500 focus:bg-white dark:hover:border-zinc-700 dark:focus:bg-zinc-950'

export default function Mappings({ project, onSaved, onError }: { project: Project; onSaved: (m: M) => void; onError: (e: unknown) => void }) {
  const [m, setM] = useState<M>(project.mappings)
  const [tab, setTab] = useState<'classes' | 'libraries' | 'types'>(project.mappings.classes.length ? 'classes' : 'libraries')
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(true)
  useEffect(() => { setM(project.mappings); setSaved(true) }, [project.mappings])

  const edit = (fn: (d: M) => void) => { setM(prev => { const d = structuredClone(prev); fn(d); return d }); setSaved(false) }
  const save = async () => {
    setBusy(true)
    try { await api.saveMappings(project.id, m); setSaved(true); onSaved(m) } catch (e) { onError(e) } finally { setBusy(false) }
  }
  const reset = async () => {
    setBusy(true)
    try { const fresh = await api.resetMappings(project.id); setM(fresh); setSaved(true); onSaved(fresh) } catch (e) { onError(e) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={tab} onChange={setTab} items={[
          { id: 'classes', label: `Classes (${m.classes.length})` },
          { id: 'libraries', label: `Libraries (${m.libraries.length})` },
          { id: 'types', label: `Types (${m.types.length})` },
        ]} />
        <p className="text-sm text-zinc-500 dark:text-zinc-400">This contract goes to the translator for every module, so all files make the same decisions. Edit it to change those decisions.</p>
        <div className="ml-auto flex gap-2">
          <Button variant="ghost" onClick={reset} disabled={busy}>Reset to suggested</Button>
          <Button variant="primary" onClick={save} disabled={busy || saved}>{busy && <Spinner />}{saved ? 'Saved' : 'Save changes'}</Button>
        </div>
      </div>

      {tab === 'classes' && (m.classes.length === 0 ? <Empty title="No classes">The project is procedural; only type and library mappings apply.</Empty> : (
        <div className="grid gap-3 lg:grid-cols-2">
          {m.classes.map((c, i) => (
            <Card key={c.name + c.file} title={<span className="flex items-center gap-2"><span className="font-mono">{c.name}</span><Badge>{c.source_kind}</Badge></span>}
              action={<span className="font-mono text-xs text-zinc-500">{c.file}:{c.line}</span>}>
              <div className="space-y-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <label className="text-xs font-medium text-zinc-500">Strategy</label>
                  <select value={c.strategy} onChange={e => edit(d => { d.classes[i].strategy = e.target.value })}
                    className="h-8 rounded-md border border-zinc-200 bg-transparent px-2 text-sm dark:border-zinc-700">
                    {project.strategies.map(s => <option key={s} value={s}>{s}: {strategyHelp[s]}</option>)}
                  </select>
                </div>
                <div><div className="text-xs font-medium text-zinc-500">Rust target</div>
                  <input className={input + ' text-brand-700 dark:text-brand-300'} value={c.target} onChange={e => edit(d => { d.classes[i].target = e.target.value })} /></div>
                <p className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{c.rationale}</p>
                {c.trait_impls.length > 0 && <div className="flex flex-wrap gap-1">{c.trait_impls.map(t => <Badge key={t} tone="blue">impl {t}</Badge>)}</div>}
                {c.members.length > 0 && <details><summary className="cursor-pointer text-xs text-zinc-500">{c.members.length} members</summary>
                  <ul className="mt-1 space-y-0.5 font-mono text-xs text-zinc-600 dark:text-zinc-400">{c.members.map(x => <li key={x}>{x}</li>)}</ul></details>}
                <textarea value={c.notes} onChange={e => edit(d => { d.classes[i].notes = e.target.value })} rows={2} maxLength={500}
                  placeholder="Reviewer note for the translator, e.g. 'store children in a Vec<Box<dyn Shape>>'"
                  className="w-full resize-y rounded-lg border border-zinc-200 bg-transparent px-2.5 py-1.5 text-xs outline-none focus:border-brand-500 dark:border-zinc-700" />
              </div>
            </Card>
          ))}
        </div>
      ))}

      {tab === 'libraries' && (m.libraries.length === 0 ? <Empty title="No external libraries">Only language built-ins are used.</Empty> : (
        <Card pad={false}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-zinc-500"><tr><th className="px-4 py-2 font-medium">Source</th><th className="font-medium">Rust equivalent</th><th className="font-medium">Kind</th><th className="font-medium">Confidence</th><th className="px-4 font-medium">Note</th></tr></thead>
              <tbody>
                {m.libraries.map((l, i) => (
                  <tr key={l.source} className="border-t border-zinc-100 align-top dark:border-zinc-800">
                    <td className="px-4 py-2 font-mono text-xs">{l.source}<div className="text-zinc-400">{l.used_in.join(', ')}</div></td>
                    <td className="min-w-64 py-1"><input className={input} value={l.target} onChange={e => edit(d => { d.libraries[i].target = e.target.value })} /></td>
                    <td className="py-2"><select value={l.kind} onChange={e => edit(d => { d.libraries[i].kind = e.target.value as typeof l.kind })} className="rounded border-0 bg-transparent p-0 text-xs">
                      {(['std', 'crate', 'manual', 'unsupported'] as const).map(k => <option key={k}>{k}</option>)}</select>
                      <div><Badge tone={kindTone[l.kind]}>{l.kind}{l.crates.length ? `: ${l.crates.join(', ')}` : ''}</Badge></div></td>
                    <td className="py-2 text-xs">{l.confidence}</td>
                    <td className="px-4 py-2 text-xs text-zinc-600 dark:text-zinc-400">{l.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}

      {tab === 'types' && (
        <Card pad={false}>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-zinc-500"><tr><th className="px-4 py-2 font-medium">Source type</th><th className="font-medium">Uses</th><th className="font-medium">Rust type</th><th className="px-4 font-medium">Note</th></tr></thead>
            <tbody>
              {m.types.map((t, i) => (
                <tr key={t.source} className="border-t border-zinc-100 dark:border-zinc-800">
                  <td className="px-4 py-2 font-mono text-xs">{t.source}</td>
                  <td className="text-xs tabular-nums text-zinc-500">{t.count}</td>
                  <td className="min-w-56 py-1"><input className={input} value={t.target} onChange={e => edit(d => { d.types[i].target = e.target.value })} /></td>
                  <td className="px-4 py-2 text-xs text-zinc-600 dark:text-zinc-400">{t.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
