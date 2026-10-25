import { useCallback, useEffect, useRef, useState } from 'react'
import Editor, { DiffEditor } from '@monaco-editor/react'
import { api, openWs, Unauthorized, type JobResult, type JobSummary, type Lang, type PipelineEvent } from './api'
import Login from './Login'
import Timeline from './Timeline'
import BenchmarkPanel from './BenchmarkPanel'
import { EXAMPLES } from './examples'

const badge: Record<string, string> = {
  verified: 'bg-green-600', compiles_only: 'bg-amber-500', failed: 'bg-red-600', running: 'bg-blue-500',
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  useEffect(() => { api.me().then(() => setAuthed(true)).catch(() => setAuthed(false)) }, [])
  if (authed === null) return null
  if (!authed) return <Login onDone={() => setAuthed(true)} />
  return <Main onLogout={() => setAuthed(false)} />
}

const store = {
  get(key: string): string | null { try { return localStorage.getItem(key) } catch { return null } },
  set(key: string, value: string) { try { localStorage.setItem(key, value) } catch { /* storage unavailable */ } },
}

const statusLabel: Record<string, string> = {
  verified: 'Verified', compiles_only: 'Compiles, output differs', failed: 'Failed', running: 'Running',
}

function Main({ onLogout }: { onLogout: () => void }) {
  const [lang, setLang] = useState<Lang>(store.get('lang') === 'cpp' ? 'cpp' : 'python')
  const [code, setCode] = useState(store.get('draft') ?? EXAMPLES[0].code)
  const [labels, setLabels] = useState<Record<string, string>>(() => { try { return JSON.parse(store.get('labels') ?? '{}') } catch { return {} } })
  const [elapsed, setElapsed] = useState(0)
  const [view, setView] = useState<'translate' | 'benchmark'>('translate')
  const translateRef = useRef<() => void>(() => {})
  useEffect(() => { store.set('draft', code) }, [code])
  useEffect(() => { store.set('lang', lang) }, [lang])
  useEffect(() => { store.set('labels', JSON.stringify(labels)) }, [labels])
  const [events, setEvents] = useState<PipelineEvent[]>([])
  const [result, setResult] = useState<JobResult | null>(null)
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [curId, setCurId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [sidebar, setSidebar] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const loadFile = async (f: File) => {
    if (f.size > 50_000) { setError('File is too large (limit is 50,000 characters).'); return }
    const name = f.name.toLowerCase()
    if (/\.py$/.test(name)) setLang('python')
    else if (/\.(cpp|cc|cxx|hpp|h)$/.test(name)) setLang('cpp')
    setCode(await f.text())
    setError('')
  }
  const [dark, setDark] = useState(document.documentElement.classList.contains('dark'))
  const ws = useRef<WebSocket | null>(null)

  const fail = useCallback((e: unknown) => { if (e instanceof Unauthorized) onLogout(); else setError(String(e instanceof Error ? e.message : e)) }, [onLogout])
  const refresh = useCallback(() => api.list().then(setJobs).catch(fail), [fail])
  useEffect(() => { refresh(); return () => ws.current?.close() }, [refresh])

  const finish = useCallback(async (id: string) => {
    try { const d = await api.get(id); setResult(d.result); setEvents(d.events) } catch (e) { fail(e) }
    setRunning(false); refresh()
  }, [fail, refresh])

  const watch = useCallback((id: string) => {
    ws.current?.close()
    const w = openWs(id); ws.current = w
    setEvents([]); setResult(null); setRunning(true)
    w.onmessage = m => { try { setEvents(ev => [...ev, JSON.parse(m.data)]) } catch { /* ignore */ } }
    w.onclose = () => { if (ws.current === w) finish(id) }
  }, [finish])

  const translate = async () => {
    if (!code.trim() || running) return
    setError('')
    try {
      const { id } = await api.create(lang, code)
      const first = code.split('\n').find(l => l.trim()) ?? ''
      setLabels(m => ({ ...m, [id]: first.trim().slice(0, 28) }))
      setCurId(id); watch(id); refresh()
    } catch (e) { fail(e) }
  }
  translateRef.current = translate

  useEffect(() => {
    if (!running) return
    const start = Date.now(); setElapsed(0)
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(t)
  }, [running])

  const downloadProject = () => { if (curId) window.location.href = `/api/jobs/${curId}/download` }

  const load = async (id: string) => {
    ws.current?.close(); ws.current = null; setError(''); setSidebar(false)
    try {
      const d = await api.get(id)
      setCurId(id); setLang(d.language); setEvents(d.events); setResult(d.result)
      if (d.result) { setCode(d.result.original); setRunning(false) } else watch(id)
    } catch (e) { fail(e) }
  }

  const monacoTheme = dark ? 'vs-dark' : 'light'
  const opts = { minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false, automaticLayout: true }
  const providers = result ? (Array.isArray(result.providers) ? result.providers.join(', ') : result.providers) : ''
  const btn = 'rounded-lg border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800'

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 px-3 py-2">
        <button className={btn + ' lg:hidden'} onClick={() => setSidebar(s => !s)}>History</button>
        <h1 className="font-semibold">Rust Migrator</h1>
        <div className="ml-auto flex gap-2">
          <button className={btn} onClick={() => setView(v => v === 'benchmark' ? 'translate' : 'benchmark')}>{view === 'benchmark' ? 'Back to translator' : 'Benchmark'}</button>
          <button className={btn} onClick={() => { document.documentElement.classList.toggle('dark'); setDark(d => !d) }}>{dark ? 'Light' : 'Dark'}</button>
          <button className={btn} onClick={async () => { await api.logout().catch(() => {}); onLogout() }}>Logout</button>
        </div>
      </header>
      <div className="flex flex-1 min-h-0 relative">
        <aside className={`${sidebar ? 'block' : 'hidden'} lg:block absolute lg:static z-10 inset-y-0 left-0 w-64 shrink-0 overflow-auto border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-2`}>
          <div className="text-xs uppercase text-slate-500 px-2 py-1">History</div>
          {jobs.length === 0 && <div className="px-2 text-sm text-slate-400">No jobs yet</div>}
          {[...jobs].reverse().map(j => (
            <button key={j.id} onClick={() => load(j.id)} className={`w-full flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800 ${j.id === curId ? 'bg-slate-100 dark:bg-slate-800' : ''}`}>
              <span className={`h-2 w-2 rounded-full ${badge[j.status] ?? 'bg-slate-400'}`} />
              <span className="truncate font-mono text-xs" title={j.id}>{labels[j.id] || j.id.slice(0, 8)}</span>
              <span className="ml-auto text-xs text-slate-500">{j.language}</span>
            </button>
          ))}
        </aside>
        <main className="flex-1 min-w-0 overflow-auto p-3 space-y-3">
          {view === 'benchmark' ? <BenchmarkPanel onUnauthorized={onLogout} /> : <>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-lg border border-slate-300 dark:border-slate-700 overflow-hidden text-sm">
              {(['cpp', 'python'] as Lang[]).map(l => (
                <button key={l} onClick={() => setLang(l)} className={`px-3 py-1.5 ${lang === l ? 'bg-orange-600 text-white' : 'hover:bg-slate-100 dark:hover:bg-slate-800'}`}>{l === 'cpp' ? 'C++' : 'Python'}</button>
              ))}
            </div>
            <select className={btn + ' bg-transparent'} value="" onChange={e => { const x = EXAMPLES[Number(e.target.value)]; if (x) { setLang(x.language); setCode(x.code) } }}>
              <option value="" disabled>Examples…</option>
              {EXAMPLES.map((x, i) => <option key={x.name} value={i} className="text-black">{x.name}</option>)}
            </select>
            <input ref={fileRef} type="file" accept=".py,.cpp,.cc,.cxx,.hpp,.h,.txt" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) loadFile(f); e.target.value = '' }} />
            <button onClick={() => fileRef.current?.click()} className={btn}>Upload file</button>
            <button onClick={() => { setCode(''); setError('') }} className={btn} disabled={!code}>Clear</button>
            <span className="text-xs text-slate-500">{code.split('\n').length} lines</span>
            <button onClick={translate} disabled={running} title="Ctrl+Enter" className="ml-auto rounded-lg bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white px-4 py-1.5 text-sm font-medium">{running ? `Translating… ${elapsed}s` : 'Translate'}</button>
          </div>
          {error && <div className="rounded-lg bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300 px-3 py-2 text-sm">{error}</div>}
          <div className="grid gap-3 xl:grid-cols-[1fr_18rem]">
            <div className="h-72 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-800"
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) loadFile(f) }}>
              <Editor language={lang === 'cpp' ? 'cpp' : 'python'} value={code} onChange={v => setCode(v ?? '')} theme={monacoTheme} options={opts}
                onMount={(ed, monaco) => ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => translateRef.current())} />
            </div>
            <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-2">
              <div className="text-xs uppercase text-slate-500 px-2 pb-1">Pipeline</div>
              <Timeline events={events} />
            </div>
          </div>
          {result && (
            <section className="space-y-2">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <span className={`rounded-full px-3 py-0.5 text-white font-medium ${badge[result.status]}`}>{statusLabel[result.status] ?? result.status}</span>
                <span>unsafe: {result.unsafe_count}</span>
                <span>{result.seconds?.toFixed?.(1)}s</span>
                <span>attempts: {result.attempts}</span>
                {result.tests_total !== undefined && <span>tests: {result.tests_passed}/{result.tests_total}</span>}
                {providers && <span className="text-slate-500">providers: {providers}</span>}
                <button className={btn + ' ml-auto'} onClick={() => { navigator.clipboard.writeText(result.rust); setCopied(true); setTimeout(() => setCopied(false), 1500) }}>{copied ? 'Copied' : 'Copy Rust'}</button>
                <button className={btn} onClick={downloadProject} disabled={!curId}>Download Cargo project</button>
              </div>
              {result.message && <div className="text-sm text-slate-500">{result.message}</div>}
              {result.status !== 'verified' && result.failures && result.failures.length > 0 && (
                <details open className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-2 text-sm">
                  <summary className="cursor-pointer font-medium">Failing tests ({result.failures.length})</summary>
                  <div className="mt-2 space-y-2">
                    {result.failures.map((f, i) => (
                      <div key={i} className="grid gap-2 md:grid-cols-3 text-xs">
                        {([['Input', f.stdin], ['Expected (original)', f.expected], ['Got (Rust)', f.actual]] as const).map(([title, text]) => (
                          <div key={title}><div className="uppercase text-slate-500 mb-0.5">{title}</div><pre className="rounded bg-slate-100 dark:bg-slate-800 p-2 whitespace-pre-wrap break-all">{text || '(empty)'}</pre></div>
                        ))}
                      </div>
                    ))}
                  </div>
                </details>
              )}
              <div className="flex text-xs uppercase text-slate-500"><span className="w-1/2 px-1">Original</span><span className="w-1/2 px-1">Rust</span></div>
              <div className="h-[28rem] rounded-lg overflow-hidden border border-slate-200 dark:border-slate-800">
                <DiffEditor original={result.original} modified={result.rust} originalLanguage={lang === 'cpp' ? 'cpp' : 'python'} modifiedLanguage="rust" theme={monacoTheme} options={{ ...opts, readOnly: true, renderSideBySide: true, renderOverviewRuler: false }} />
              </div>
            </section>
          )}
          </>}
        </main>
      </div>
    </div>
  )
}
