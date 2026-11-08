import { useCallback, useEffect, useRef, useState } from 'react'
import { api, openWs, type Job, type Project } from '../api'
import { Badge, Button, cx, Icon, Spinner, statusMeta } from '../components/ui'
import type { Theme } from '../hooks'
import Assessment from './Assessment'
import Mappings from './Mappings'
import Migrate from './Migrate'
import Report from './Report'

type Tab = 'assessment' | 'mappings' | 'migrate' | 'report'
const STEPS: { id: Tab; label: string; hint: string }[] = [
  { id: 'assessment', label: 'Assessment', hint: 'static analysis' },
  { id: 'mappings', label: 'Mappings', hint: 'review the contract' },
  { id: 'migrate', label: 'Migrate', hint: 'translate & verify' },
  { id: 'report', label: 'Report', hint: 'evidence & code' },
]

export default function ProjectView({ id, tab, theme, go, onError, onChanged }: {
  id: string; tab: string | undefined; theme: Theme; go: (p: string) => void; onError: (e: unknown) => void; onChanged: () => void
}) {
  const [project, setProject] = useState<Project | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [starting, setStarting] = useState(false)
  const ws = useRef<WebSocket | null>(null)
  const active: Tab = (STEPS.some(s => s.id === tab) ? tab : 'assessment') as Tab

  const watch = useCallback((jid: string) => {
    ws.current?.close()
    const w = openWs(jid); ws.current = w
    setJob(j => (j && j.id === jid ? { ...j, events: [] } : { id: jid, project_id: id, status: 'running', events: [], result: null }))
    w.onmessage = m => {
      try {
        const ev = JSON.parse(m.data)
        setJob(j => (j ? { ...j, events: [...j.events, ev] } : j))
      } catch { /* ignore malformed */ }
    }
    w.onclose = async () => {
      if (ws.current !== w) return
      try { const fresh = await api.job(jid); setJob(fresh); onChanged() } catch (e) { onError(e) }
    }
  }, [id, onChanged, onError])

  useEffect(() => {
    let alive = true
    setProject(null); setJob(null)
    api.project(id).then(async p => {
      if (!alive) return
      setProject(p)
      if (p.jobs[0]) {
        const j = await api.job(p.jobs[0].id)
        if (!alive) return
        setJob(j)
        if (j.status === 'running') watch(j.id)
      }
    }).catch(onError)
    return () => { alive = false; ws.current?.close(); ws.current = null }
  }, [id, onError, watch])

  const start = async () => {
    setStarting(true)
    try { const { id: jid } = await api.migrate(id); watch(jid); onChanged(); go(`p/${id}/migrate`) } catch (e) { onError(e) } finally { setStarting(false) }
  }

  if (!project) return (
    <div className="mx-auto max-w-7xl space-y-4 p-6">
      <div className="skeleton h-8 w-64" /><div className="skeleton h-12" />
      <div className="grid grid-cols-3 gap-3"><div className="skeleton h-24" /><div className="skeleton h-24" /><div className="skeleton h-24" /></div>
      <div className="skeleton h-80" />
    </div>
  )

  const status = job?.status ?? 'new'
  const done: Record<Tab, boolean> = { assessment: true, mappings: true, migrate: !!job && status !== 'running', report: !!job?.result?.files }

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3 animate-fade-in">
        <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
        <Badge>{project.language === 'cpp' ? 'C++' : 'Python'}</Badge>
        <Badge tone={statusMeta[status]?.tone}>{status === 'running' && <Spinner className="h-3 w-3" />}{statusMeta[status]?.label}</Badge>
        <div className="ml-auto flex gap-2">
          <Button variant="ghost" size="sm" onClick={async () => {
            if (!confirm(`Delete project "${project.name}" and its migrations?`)) return
            try { await api.remove(id); onChanged(); go('') } catch (e) { onError(e) }
          }}>{Icon.trash}Delete</Button>
          {active !== 'migrate' && status !== 'running' && <Button variant="primary" onClick={() => go(`p/${id}/migrate`)}>{Icon.play}{job ? 'Migrate again' : 'Migrate'}</Button>}
        </div>
      </div>

      <nav className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Migration steps">
        {STEPS.map((s, i) => {
          const isActive = s.id === active
          const disabled = s.id === 'report' && !done.report
          return (
            <button key={s.id} disabled={disabled} onClick={() => go(`p/${id}/${s.id}`)}
              className={cx('group flex items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-all disabled:opacity-40',
                isActive ? 'border-brand-300 bg-white shadow-sm ring-4 ring-brand-500/10 dark:border-brand-500/50 dark:bg-zinc-900' : 'border-zinc-200 hover:border-zinc-300 hover:bg-white dark:border-zinc-800 dark:hover:bg-zinc-900')}>
              <span className={cx('grid h-7 w-7 shrink-0 place-items-center rounded-full text-xs font-semibold transition-colors',
                isActive ? 'bg-brand-600 text-white' : done[s.id] && s.id !== 'assessment' && s.id !== 'mappings' ? 'bg-emerald-500 text-white' : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300')}>
                {s.id === 'migrate' && status === 'running' ? <Spinner className="h-3.5 w-3.5" /> : i + 1}
              </span>
              <span className="min-w-0"><span className="block text-sm font-medium">{s.label}</span><span className="block truncate text-xs text-zinc-500">{s.hint}</span></span>
            </button>
          )
        })}
      </nav>

      <div key={active} className="animate-fade-in">
        {active === 'assessment' && <Assessment project={project} theme={theme} />}
        {active === 'mappings' && <Mappings project={project} onError={onError} onSaved={m => setProject(p => (p ? { ...p, mappings: m } : p))} />}
        {active === 'migrate' && <Migrate project={project} job={job} starting={starting} onStart={start} onReport={() => go(`p/${id}/report`)} />}
        {active === 'report' && <Report project={project} job={job} theme={theme} />}
      </div>
    </div>
  )
}
