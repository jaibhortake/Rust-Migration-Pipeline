export type Lang = 'cpp' | 'python'
export type JobStatus = 'running' | 'equivalent' | 'partial' | 'compile_failed' | 'failed' | 'interrupted'
export type ProjectStatus = JobStatus | 'new'
export type Severity = 'high' | 'medium' | 'low'

export interface ProjectSummary { id: string; name: string; language: Lang; created: number; loc: number; status: ProjectStatus }

export interface Unit {
  id: string; files: string[]; is_entry: boolean; deps: string[]; external: string[]
  loc: number; complexity: number; classes: number; functions: number; risk_score: number; difficulty: number; manual_hours: number
}
export interface Risk { rule: string; severity: Severity; title: string; file: string; line: number; why: string; strategy: string }
export interface Assessment {
  language: Lang
  summary: {
    files: number; loc: number; units: number; classes: number; functions: number
    risks: Record<Severity, number>; manual_hours: number; library_coverage: number
    readiness: 'easy' | 'moderate' | 'hard' | 'blocked'; verdict: string; blockers: string[]; unsupported: string[]; single_function: boolean
  }
  graph: { units: Record<string, { id: string; files: string[]; is_entry: boolean; deps: string[] }>; order: string[][]; entry: string | null; cycles: string[][] }
  units: Unit[]
  risks: Risk[]
}
export interface TypeMapping { source: string; target: string; note: string; count: number }
export interface LibMapping { source: string; target: string; kind: 'std' | 'crate' | 'manual' | 'unsupported'; crates: string[]; confidence: string; note: string; used_in: string[] }
export interface ClassMapping {
  name: string; file: string; line: number; source_kind: string; strategy: string; target: string
  trait_impls: string[]; members: string[]; rationale: string; notes: string
}
export interface Mappings { types: TypeMapping[]; libraries: LibMapping[]; classes: ClassMapping[] }
export interface JobRef { id: string; status: JobStatus; created: number }
export interface Project {
  id: string; name: string; language: Lang; files: Record<string, string>; assessment: Assessment; mappings: Mappings
  created: number; jobs: JobRef[]; strategies: string[]
}

export interface PipelineEvent { stage: string; status: string; [k: string]: unknown }
export interface Failure { stdin: string; expected: string; actual: string; minimized?: string }
export interface Quality {
  score: number; loc: number; unsafe: number; unwraps: number; clones: number; shared_mutability: number
  clippy_warnings: number; clippy_by_lint: Record<string, number>; rustfmt_changed_lines: number | null
  warnings: { lint: string; message: string; file: string; line: number }[]
}
export interface JobResult {
  status: Exclude<JobStatus, 'running'>; confidence: 'high' | 'medium' | 'low' | 'none'; message: string
  files: Record<string, string>; original_files: Record<string, string>
  modules: { id: string; files: string[]; rust: string; status: string; fixes: number }[]
  evidence: {
    tests_total: number; tests_passed: number; numeric_matches: number; line_coverage: number | null; branch_coverage: number | null
    inputs_by_origin: Record<string, number>; flaky_dropped: number; uncovered: Record<string, number[]>
  }
  failures: Failure[]; quality: Quality | null
  performance: { original_s: number; rust_s: number; ratio: number | null; note: string }
  attempts: { module_fixes: number; verify_rounds: number; refine_accepted: boolean }
  usage: { calls: number; cached: number; prompt_tokens: number; completion_tokens: number; providers: string[] }
  tests: { stdin: string; expected: string; origin: string }[]
  sandbox: string; seconds: number
}
export interface Job { id: string; project_id: string; status: JobStatus; events: PipelineEvent[]; result: JobResult | null }
export interface Example { name: string; language: Lang; kind: 'file' | 'project'; files: Record<string, string> }
export interface Health { ok: boolean; llm: string; sandbox: { mode: string; ready: boolean; error?: string; warning?: string } }

export interface BenchRow {
  name: string; language: Lang; kind: string; loc: number
  pipeline: { status: string; tests_passed: number; tests_total: number; line_coverage: number | null; quality: number | null; seconds: number; llm_calls: number }
  baseline: { status: string; tests_passed: number; tests_total: number }
}
export interface Benchmark { available: boolean; generated?: string; model?: string; rows?: BenchRow[]; totals?: Record<string, number> }

export class Unauthorized extends Error {}
export class ApiError extends Error {}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch('/api' + path, {
    credentials: 'same-origin',
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (r.status === 401) throw new Unauthorized()
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try { const j = await r.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    throw new ApiError(msg)
  }
  return r.json() as Promise<T>
}

export const api = {
  login: (username: string, password: string) => req('/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => req('/logout', { method: 'POST' }),
  me: () => req<{ user: string }>('/me'),
  health: () => req<Health>('/health'),
  projects: () => req<ProjectSummary[]>('/projects'),
  project: (id: string) => req<Project>('/projects/' + id),
  create: (name: string, language: Lang, files: Record<string, string>) =>
    req<{ id: string }>('/projects', { method: 'POST', body: JSON.stringify({ name, language, files }) }),
  upload: (name: string, files: File[]) => {
    const fd = new FormData()
    files.forEach(f => fd.append('files', f, (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name))
    fd.append('name', name)
    return req<{ id: string }>('/projects/upload', { method: 'POST', body: fd })
  },
  remove: (id: string) => req('/projects/' + id, { method: 'DELETE' }),
  saveMappings: (id: string, m: Mappings) => req('/projects/' + id + '/mappings', { method: 'PUT', body: JSON.stringify(m) }),
  resetMappings: (id: string) => req<Mappings>('/projects/' + id + '/reset-mappings', { method: 'POST' }),
  migrate: (id: string) => req<{ id: string }>('/projects/' + id + '/migrate', { method: 'POST' }),
  job: (id: string) => req<Job>('/jobs/' + id),
  examples: () => req<Example[]>('/examples'),
  benchmark: () => req<Benchmark>('/benchmark'),
}

export function openWs(id: string) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${location.host}/api/jobs/${id}/ws`)
}
