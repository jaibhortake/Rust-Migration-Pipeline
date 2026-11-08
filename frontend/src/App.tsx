import { useCallback, useEffect, useState } from 'react'
import { api, Unauthorized, type Health, type ProjectSummary } from './api'
import { Alert, Button, cx, Icon, statusMeta } from './components/ui'
import { ago, useRoute, useTheme } from './hooks'
import Benchmark from './pages/Benchmark'
import Login from './pages/Login'
import NewProject from './pages/NewProject'
import ProjectView from './pages/ProjectView'

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  useTheme()
  useEffect(() => { api.me().then(() => setAuthed(true)).catch(() => setAuthed(false)) }, [])
  if (authed === null) return <div className="grid h-full place-items-center"><div className="skeleton h-10 w-40" /></div>
  if (!authed) return <Login onDone={() => setAuthed(true)} />
  return <Shell onLogout={() => setAuthed(false)} />
}

function Shell({ onLogout }: { onLogout: () => void }) {
  const [route, go] = useRoute()
  const [theme, toggleTheme] = useTheme()
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState('')
  const [nav, setNav] = useState(false)

  const onError = useCallback((e: unknown) => {
    if (e instanceof Unauthorized) onLogout()
    else setError(e instanceof Error ? e.message : String(e))
  }, [onLogout])
  const refresh = useCallback(() => { api.projects().then(setProjects).catch(onError) }, [onError])
  useEffect(() => { refresh(); api.health().then(setHealth).catch(() => {}) }, [refresh])
  useEffect(() => { setNav(false); setError('') }, [route.join('/')])

  const [page, pid, tab] = route
  const sandboxBad = health && !health.sandbox.ready

  return (
    <div className="flex h-full flex-col">
      <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-zinc-200 bg-white/80 px-4 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/80">
        <button className="rounded-md p-1 text-zinc-500 lg:hidden" onClick={() => setNav(n => !n)} aria-label="Toggle projects">{Icon.menu}</button>
        <a href="#/" className="flex items-center gap-2.5">{Icon.logo}<span className="font-semibold tracking-tight">Rust Migrator</span></a>
        <nav className="ml-4 hidden gap-1 sm:flex">
          {[['', 'Projects'], ['benchmark', 'Benchmark']].map(([p, l]) => (
            <a key={p} href={`#/${p}`} className={cx('rounded-md px-3 py-1.5 text-sm font-medium transition-colors', (page === p || (!page && !p) || (page === 'p' && !p) || (page === 'new' && !p)) ? 'text-zinc-900 dark:text-zinc-100' : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100')}>{l}</a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          {health && <span title={health.sandbox.error || health.sandbox.warning || `sandbox: ${health.sandbox.mode}`}
            className={cx('hidden items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium md:inline-flex', sandboxBad ? 'bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300' : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300')}>
            <span className={cx('h-1.5 w-1.5 rounded-full', sandboxBad ? 'bg-red-500' : health.sandbox.mode === 'docker' ? 'bg-emerald-500' : 'bg-amber-500')} />
            {health.sandbox.mode} sandbox · {health.llm}</span>}
          <Button variant="ghost" size="sm" onClick={toggleTheme} aria-label="Toggle theme">{theme === 'dark' ? Icon.sun : Icon.moon}</Button>
          <Button variant="ghost" size="sm" onClick={async () => { await api.logout().catch(() => {}); onLogout() }}>Sign out</Button>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        <aside className={cx('absolute inset-y-0 left-0 z-20 w-72 shrink-0 flex-col border-r border-zinc-200 bg-white transition-transform duration-200 lg:static lg:flex lg:translate-x-0 dark:border-zinc-800 dark:bg-zinc-950',
          nav ? 'flex translate-x-0 shadow-xl' : 'hidden -translate-x-full lg:flex')}>
          <div className="p-3"><Button variant="primary" className="w-full" onClick={() => go('new')}>{Icon.plus}New migration</Button></div>
          <div className="px-4 pb-1 text-xs font-medium tracking-wide text-zinc-500 uppercase">Projects</div>
          <div className="flex-1 space-y-0.5 overflow-auto px-2 pb-4">
            {projects === null && [0, 1, 2].map(i => <div key={i} className="skeleton mx-2 my-2 h-10" />)}
            {projects?.length === 0 && <p className="px-3 py-2 text-sm text-zinc-500">No projects yet. Start with an example.</p>}
            {projects?.map(p => (
              <a key={p.id} href={`#/p/${p.id}`} className={cx('group flex items-center gap-2.5 rounded-lg px-3 py-2 transition-colors', pid === p.id ? 'bg-zinc-100 dark:bg-zinc-800/80' : 'hover:bg-zinc-50 dark:hover:bg-zinc-900')}>
                <span className={cx('h-2 w-2 shrink-0 rounded-full', statusMeta[p.status]?.dot ?? 'bg-zinc-400')} title={statusMeta[p.status]?.label} />
                <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{p.name}</span>
                  <span className="block text-xs text-zinc-500">{p.language === 'cpp' ? 'C++' : 'Python'} · {p.loc} loc · {ago(p.created)}</span></span>
              </a>
            ))}
          </div>
        </aside>
        {nav && <div className="absolute inset-0 z-10 bg-black/20 lg:hidden" onClick={() => setNav(false)} />}

        <main className="min-w-0 flex-1 overflow-auto">
          {(error || sandboxBad) && (
            <div className="mx-auto max-w-7xl space-y-2 px-4 pt-4 sm:px-6">
              {sandboxBad && <Alert tone="amber">Sandbox not ready: {health?.sandbox.error}</Alert>}
              {error && <Alert onClose={() => setError('')}>{error}</Alert>}
            </div>
          )}
          {page === 'p' && pid ? <ProjectView key={pid} id={pid} tab={tab} theme={theme} go={go} onError={onError} onChanged={refresh} />
            : page === 'benchmark' ? <Benchmark onError={onError} />
              : page === 'new' || !projects?.length ? <NewProject theme={theme} onError={onError} onCreated={id => { refresh(); go(`p/${id}`) }} />
                : <Home projects={projects} go={go} />}
        </main>
      </div>
    </div>
  )
}

function Home({ projects, go }: { projects: ProjectSummary[]; go: (p: string) => void }) {
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <div className="flex items-center gap-3 animate-fade-in">
        <div><h1 className="text-2xl font-semibold tracking-tight">Projects</h1><p className="text-sm text-zinc-500">Assess, map, migrate and verify C++ and Python codebases.</p></div>
        <Button variant="primary" className="ml-auto" onClick={() => go('new')}>{Icon.plus}New migration</Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map(p => (
          <a key={p.id} href={`#/p/${p.id}`} className="group rounded-xl border border-zinc-200 bg-white p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md animate-slide-up dark:border-zinc-800 dark:bg-zinc-900/60">
            <div className="flex items-center gap-2"><span className={cx('h-2 w-2 rounded-full', statusMeta[p.status]?.dot)} /><span className="truncate font-medium">{p.name}</span></div>
            <div className="mt-2 text-sm text-zinc-500">{p.language === 'cpp' ? 'C++' : 'Python'} · {p.loc} lines</div>
            <div className="mt-3 flex items-center justify-between text-xs"><span className="text-zinc-500">{statusMeta[p.status]?.label}</span><span className="text-zinc-400">{ago(p.created)}</span></div>
          </a>
        ))}
      </div>
    </div>
  )
}
