export type Lang = 'cpp' | 'python'
export type Status = 'running' | 'verified' | 'compiles_only' | 'failed'
export interface JobSummary { id: string; language: Lang; status: Status }
export interface PipelineEvent { stage: string; status: 'running' | 'ok' | 'failed'; attempt?: number; errors?: string; passed?: number; total?: number; [k: string]: unknown }
export interface JobResult { status: Exclude<Status, 'running'>; rust: string; original: string; attempts: number; unsafe_count: number; providers: string[] | string; message?: string; tests_passed?: number; tests_total?: number; seconds: number; failures?: Failure[] }
export interface Failure { stdin: string; expected: string; actual: string }
export interface BenchRow { file: string; status: string; tests_passed: number; tests_total: number; attempts: number; seconds: number }
export interface Benchmark { available: boolean; verified?: number; total?: number; percent_verified?: number; results?: BenchRow[]; rows?: BenchRow[] }
export interface JobDetail { id: string; language: Lang; events: PipelineEvent[]; result: JobResult | null }

export class Unauthorized extends Error {}
async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch('/api' + path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...init })
  if (r.status === 401) throw new Unauthorized()
  if (!r.ok) throw new Error(`${r.status} ${await r.text().catch(() => '')}`)
  return r.json().catch(() => ({})) as Promise<T>
}
export const api = {
  login: (username: string, password: string) => req('/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => req('/logout', { method: 'POST' }),
  me: () => req<{ username?: string }>('/me'),
  create: (language: Lang, code: string) => req<{ id: string }>('/jobs', { method: 'POST', body: JSON.stringify({ language, code }) }),
  list: () => req<JobSummary[]>('/jobs'),
  get: (id: string) => req<JobDetail>('/jobs/' + id),
  benchmark: () => req<Benchmark>('/benchmark'),
}
export function openWs(id: string) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${location.host}/api/jobs/${id}/ws`)
}
