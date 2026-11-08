import { useState } from 'react'
import { api } from '../api'
import { Alert, Button, Icon, Spinner } from '../components/ui'

export default function Login({ onDone }: { onDone: () => void }) {
  const [username, setU] = useState('admin')
  const [password, setP] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await api.login(username, password); onDone() } catch (x) { setErr(x instanceof Error ? x.message : String(x)) } finally { setBusy(false) }
  }
  const input = 'h-10 w-full rounded-lg border border-zinc-300 bg-white px-3 text-sm shadow-sm outline-none transition focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15 dark:border-zinc-700 dark:bg-zinc-900'
  return (
    <div className="grid min-h-full place-items-center bg-[radial-gradient(ellipse_at_top,rgb(247_76_13/0.12),transparent_60%)] p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-2xl border border-zinc-200 bg-white/80 p-7 shadow-xl backdrop-blur animate-slide-up dark:border-zinc-800 dark:bg-zinc-900/80">
        <div className="flex items-center gap-3">
          {Icon.logo}
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Rust Migrator</h1>
            <p className="text-xs text-zinc-500">Analysis-first C++ / Python → Rust migration</p>
          </div>
        </div>
        {err && <Alert>{err === 'invalid credentials' ? 'Wrong username or password.' : err}</Alert>}
        <label className="block space-y-1.5"><span className="text-sm font-medium">Username</span>
          <input className={input} value={username} onChange={e => setU(e.target.value)} autoComplete="username" /></label>
        <label className="block space-y-1.5"><span className="text-sm font-medium">Password</span>
          <input className={input} type="password" value={password} onChange={e => setP(e.target.value)} autoComplete="current-password" autoFocus /></label>
        <Button variant="primary" size="lg" className="w-full" disabled={busy || !password}>{busy && <Spinner />}Sign in</Button>
      </form>
    </div>
  )
}
