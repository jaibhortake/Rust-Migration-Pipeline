import { useState } from 'react'
import { api } from './api'
export default function Login({ onDone }: { onDone: () => void }) {
  const [u, setU] = useState(''); const [p, setP] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { await api.login(u, p); onDone() } catch { setErr('Invalid username or password') } finally { setBusy(false) }
  }
  const cls = 'w-full rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 outline-none focus:ring-2 focus:ring-orange-500'
  return (
    <div className="min-h-full grid place-items-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-lg">
        <h1 className="text-2xl font-semibold">Rust Migrator</h1>
        <p className="text-sm text-slate-500">Sign in to translate C++ / Python to Rust.</p>
        <input className={cls} placeholder="Username" value={u} onChange={e => setU(e.target.value)} autoFocus />
        <input className={cls} type="password" placeholder="Password" value={p} onChange={e => setP(e.target.value)} />
        {err && <div className="text-sm text-red-500">{err}</div>}
        <button disabled={busy} className="w-full rounded-lg bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white py-2 font-medium">{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}
