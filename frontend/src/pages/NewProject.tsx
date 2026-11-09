import Editor from '@monaco-editor/react'
import { useEffect, useRef, useState } from 'react'
import { api, type Example, type Lang } from '../api'
import { Alert, Badge, Button, Card, cx, Icon, Spinner, Tabs } from '../components/ui'
import type { Theme } from '../hooks'

const SOURCE_RE = /(\.(py|cpp|cc|cxx|h|hpp|hh|hxx|zip)|(^|\/)(requirements\.txt|CMakeLists\.txt))$/i

export default function NewProject({ theme, onCreated, onError }: { theme: Theme; onCreated: (id: string) => void; onError: (e: unknown) => void }) {
  const [mode, setMode] = useState<'paste' | 'upload'>('paste')
  const [name, setName] = useState('')
  const [lang, setLang] = useState<Lang>('python')
  const [code, setCode] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [examples, setExamples] = useState<Example[]>([])
  const [picked, setPicked] = useState<Example | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [drag, setDrag] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => { api.examples().then(setExamples).catch(onError) }, [onError])

  const addFiles = (list: FileList | File[]) => {
    const ok = Array.from(list).filter(f => SOURCE_RE.test(f.name))
    if (!ok.length) { setErr('Choose .py, .cpp/.h files, requirements.txt, CMakeLists.txt or a .zip of a project.'); return }
    setErr(''); setPicked(null); setMode('upload')
    setFiles(prev => [...prev.filter(p => !ok.some(o => o.name === p.name)), ...ok])
  }

  const pick = (ex: Example) => {
    setPicked(ex); setName(ex.name); setLang(ex.language); setErr('')
    if (ex.kind === 'file') { setMode('paste'); setCode(Object.values(ex.files)[0]) } else { setMode('upload'); setFiles([]) }
  }

  const submit = async () => {
    setBusy(true); setErr('')
    try {
      let r: { id: string }
      if (picked?.kind === 'project') r = await api.create(name, picked.language, picked.files)
      else if (mode === 'paste') r = await api.create(name, lang, { [lang === 'python' ? 'main.py' : 'main.cpp']: code })
      else r = await api.upload(name, files)
      onCreated(r.id)
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); onError(e) } finally { setBusy(false) }
  }

  const ready = picked?.kind === 'project' || (mode === 'paste' ? code.trim().length > 0 : files.length > 0)
  const projects = examples.filter(e => e.kind === 'project')
  const singles = examples.filter(e => e.kind === 'file')

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <div className="animate-fade-in">
        <h1 className="text-2xl font-semibold tracking-tight">New migration</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Start with a free, instant static assessment. Nothing is sent to the LLM until you start the migration.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card pad={false}>
          <div className="flex flex-wrap items-center gap-3 border-b border-zinc-100 p-3 dark:border-zinc-800">
            <Tabs value={mode} onChange={m => { setMode(m); setPicked(p => (p?.kind === 'project' ? null : p)) }}
              items={[{ id: 'paste', label: 'Paste code' }, { id: 'upload', label: 'Upload files / zip' }]} />
            {mode === 'paste' && picked?.kind !== 'project' && (
              <Tabs value={lang} onChange={setLang} items={[{ id: 'python', label: 'Python' }, { id: 'cpp', label: 'C++' }]} />
            )}
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Project name (optional)" maxLength={120}
              className="ml-auto h-9 w-full rounded-lg border border-zinc-200 bg-transparent px-3 text-sm outline-none focus:border-brand-500 sm:w-56 dark:border-zinc-700" />
          </div>

          {picked?.kind === 'project' ? (
            <div className="space-y-3 p-4 animate-fade-in">
              <div className="flex items-center gap-2"><Badge tone="brand">example project</Badge><span className="font-medium">{picked.name}</span><Badge>{picked.language === 'cpp' ? 'C++' : 'Python'}</Badge></div>
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {Object.entries(picked.files).map(([p, t]) => (
                  <li key={p} className="flex items-center gap-2 rounded-lg bg-zinc-50 px-3 py-2 font-mono text-xs dark:bg-zinc-800/60">{Icon.file}{p}<span className="ml-auto text-zinc-400">{t.split('\n').length} lines</span></li>
                ))}
              </ul>
            </div>
          ) : mode === 'paste' ? (
            <div className="h-[26rem]">
              <Editor language={lang === 'cpp' ? 'cpp' : 'python'} value={code} onChange={v => setCode(v ?? '')} theme={theme === 'dark' ? 'vs-dark' : 'light'}
                options={{ minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false, automaticLayout: true, padding: { top: 12 } }} />
            </div>
          ) : (
            <div className="p-4">
              <div onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
                onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files) }}
                onClick={() => input.current?.click()}
                className={cx('flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors',
                  drag ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10' : 'border-zinc-300 hover:border-zinc-400 dark:border-zinc-700')}>
                <span className="text-zinc-400">{Icon.upload}</span>
                <div className="font-medium">Drop source files or a .zip here</div>
                <div className="text-sm text-zinc-500">.py or .cpp/.h · optional requirements.txt / CMakeLists.txt · up to 60 files · 1 MB · one language per project</div>
                <input ref={input} type="file" multiple accept=".py,.cpp,.cc,.cxx,.h,.hpp,.hh,.hxx,.zip,.txt" className="hidden"
                  onChange={e => { if (e.target.files) addFiles(e.target.files); e.target.value = '' }} />
              </div>
              {files.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {files.map(f => (
                    <li key={f.name} className="flex items-center gap-2 rounded-lg bg-zinc-50 px-3 py-2 text-sm animate-slide-up dark:bg-zinc-800/60">
                      {Icon.file}<span className="font-mono text-xs">{f.name}</span><span className="ml-auto text-xs text-zinc-400">{(f.size / 1024).toFixed(1)} KB</span>
                      <button className="text-zinc-400 hover:text-red-500" aria-label={`Remove ${f.name}`} onClick={() => setFiles(fs => fs.filter(x => x !== f))}>{Icon.x}</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="flex items-center gap-3 border-t border-zinc-100 p-3 dark:border-zinc-800">
            {err && <span className="text-sm text-red-600 dark:text-red-400">{err}</span>}
            <Button variant="primary" size="lg" className="ml-auto" disabled={!ready || busy} onClick={submit}>
              {busy ? <Spinner /> : null}Analyse project →
            </Button>
          </div>
        </Card>

        <div className="space-y-4">
          <Card title="Example projects (multi-file)">
            <div className="space-y-1.5">
              {projects.map(e => (
                <button key={e.name} onClick={() => pick(e)} className={cx('flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800', picked === e && 'bg-brand-50 ring-1 ring-brand-200 dark:bg-brand-500/10 dark:ring-brand-500/30')}>
                  <span className="font-medium">{e.name}</span>
                  <span className="ml-auto text-xs text-zinc-500">{Object.keys(e.files).length} files</span>
                  <Badge>{e.language === 'cpp' ? 'C++' : 'Py'}</Badge>
                </button>
              ))}
              {!projects.length && <div className="skeleton h-24" />}
            </div>
          </Card>
          <Card title="Single-file examples">
            <div className="max-h-72 space-y-0.5 overflow-auto">
              {singles.map(e => (
                <button key={e.language + e.name} onClick={() => pick(e)} className={cx('flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-800', picked === e && 'bg-zinc-100 dark:bg-zinc-800')}>
                  <span className="truncate">{e.name}</span><span className="ml-auto text-xs text-zinc-400">{e.language === 'cpp' ? 'C++' : 'Py'}</span>
                </button>
              ))}
            </div>
          </Card>
          <Alert tone="blue">Single functions without a <code>main</code> are fine: the pipeline generates a stdin/stdout driver first.</Alert>
        </div>
      </div>
    </div>
  )
}
