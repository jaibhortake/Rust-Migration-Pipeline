import { useEffect, useState } from 'react'
import { api, Unauthorized, type Benchmark } from './api'

const tone: Record<string, string> = {
  verified: 'text-green-600', compiles_only: 'text-amber-500', failed: 'text-red-600', error: 'text-red-600',
}

export default function BenchmarkPanel({ onUnauthorized }: { onUnauthorized: () => void }) {
  const [data, setData] = useState<Benchmark | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.benchmark().then(setData).catch(e => { if (e instanceof Unauthorized) onUnauthorized(); else setError(String(e.message ?? e)) })
  }, [onUnauthorized])

  if (error) return <div className="text-sm text-red-600">{error}</div>
  if (!data) return <div className="text-sm text-slate-500">Loading…</div>
  if (!data.available) return <div className="text-sm text-slate-500">No benchmark results yet. Run <code>backend/scripts/benchmark.py</code> to create them.</div>

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-semibold">{data.percent_verified?.toFixed(0)}%</span>
        <span className="text-sm text-slate-500">verified ({data.verified} of {data.total} samples)</span>
      </div>
      <div className="overflow-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500">
            <tr><th className="px-3 py-2">Sample</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Tests</th><th className="px-3 py-2">Attempts</th><th className="px-3 py-2">Seconds</th></tr>
          </thead>
          <tbody>
            {(data.results ?? []).map(r => (
              <tr key={r.file} className="border-t border-slate-200 dark:border-slate-800">
                <td className="px-3 py-1.5 font-mono text-xs">{r.file}</td>
                <td className={`px-3 py-1.5 ${tone[r.status] ?? ''}`}>{r.status}</td>
                <td className="px-3 py-1.5">{r.tests_passed}/{r.tests_total}</td>
                <td className="px-3 py-1.5">{r.attempts}</td>
                <td className="px-3 py-1.5">{r.seconds}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
