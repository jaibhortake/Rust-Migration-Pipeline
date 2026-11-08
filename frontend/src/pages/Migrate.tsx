import type { Job, Project } from '../api'
import DepGraph from '../components/DepGraph'
import Timeline from '../components/Timeline'
import { Alert, Badge, Button, Card, Empty, Icon, Spinner, statusMeta } from '../components/ui'
import { fmtSecs, useElapsed } from '../hooks'

export default function Migrate({ project, job, starting, onStart, onReport }: {
  project: Project; job: Job | null; starting: boolean; onStart: () => void; onReport: () => void
}) {
  const running = job?.status === 'running'
  const elapsed = useElapsed(running)
  const s = project.assessment.summary
  const blocked = s.blockers.length > 0 && !s.single_function

  // live module status for the graph
  const modStatus: Record<string, string> = {}
  for (const e of job?.events ?? []) {
    if (e.stage !== 'translate' || typeof e.module !== 'string') continue
    for (const m of e.module.split(',')) modStatus[m] = e.status === 'ok' ? 'compiles' : e.status === 'failed' ? 'failed' : 'working'
  }
  const done = job?.events.find(e => e.stage === 'done')

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_1.2fr]">
      <Card title="Pipeline" action={running ? <Badge tone="blue"><Spinner className="h-3 w-3" />{fmtSecs(elapsed)}</Badge> : job ? <Badge tone={statusMeta[job.status]?.tone}>{statusMeta[job.status]?.label}</Badge> : null}>
        {!job ? (
          <Empty title="Ready to migrate" icon={Icon.play}>
            Runs in an isolated sandbox: no network, capped CPU/memory, non-root. Typical run: 1–4 minutes, about 4–12 LLM calls.
            <div className="mt-4">
              <Button variant="primary" size="lg" disabled={starting || blocked} onClick={onStart}>{starting ? <Spinner /> : Icon.play}Start migration</Button>
            </div>
            {blocked && <div className="mt-2 text-red-600">Fix the blockers in the assessment first.</div>}
          </Empty>
        ) : (
          <>
            <Timeline events={job.events} />
            {done && (
              <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-zinc-100 pt-4 dark:border-zinc-800 animate-fade-in">
                {done.message ? <span className="text-sm text-zinc-600 dark:text-zinc-400">{String(done.message)}</span> : null}
                <div className="ml-auto flex gap-2">
                  <Button onClick={onStart} disabled={starting}>Run again</Button>
                  {job.result?.files && Object.keys(job.result.files).length > 0 && <Button variant="primary" onClick={onReport}>View report →</Button>}
                </div>
              </div>
            )}
          </>
        )}
      </Card>
      <div className="space-y-6">
        <Card title="Module progress" action={<span className="text-xs text-zinc-500">blue = translating · green = compiles</span>}>
          <DepGraph units={project.assessment.units} order={project.assessment.graph.order} status={modStatus} />
        </Card>
        <Alert tone="blue">
          <b>How results are judged.</b> The original is run on every generated input and its real output is recorded; the Rust
          must reproduce it exactly. Inputs come from the LLM, from mutation fuzzing, and from prompts aimed at lines the
          tests have not reached yet, and coverage of the original is reported. This is strong evidence of equivalence, not a proof.
        </Alert>
      </div>
    </div>
  )
}
