import type { ButtonHTMLAttributes, ReactNode } from 'react'

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(' ')

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
const variants: Record<Variant, string> = {
  primary: 'bg-brand-600 text-white shadow-sm shadow-brand-600/20 hover:bg-brand-500 active:bg-brand-700',
  secondary: 'border border-zinc-200 bg-white text-zinc-800 shadow-sm hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800',
  ghost: 'text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100',
  danger: 'text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/50',
}

export function Button({ variant = 'secondary', size = 'md', className, children, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' | 'lg' }) {
  const sizes = { sm: 'h-8 px-2.5 text-xs gap-1.5', md: 'h-9 px-3.5 text-sm gap-2', lg: 'h-11 px-5 text-sm gap-2' }
  return (
    <button {...rest} className={cx('inline-flex items-center justify-center rounded-lg font-medium transition-all duration-150 disabled:pointer-events-none disabled:opacity-50', sizes[size], variants[variant], className)}>
      {children}
    </button>
  )
}

export function Card({ className, children, title, action, pad = true }: { className?: string; children: ReactNode; title?: ReactNode; action?: ReactNode; pad?: boolean }) {
  return (
    <section className={cx('rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60 animate-slide-up', className)}>
      {(title || action) && (
        <header className="flex items-center gap-3 border-b border-zinc-100 px-4 py-3 dark:border-zinc-800">
          <h3 className="text-sm font-semibold">{title}</h3>
          <div className="ml-auto flex items-center gap-2">{action}</div>
        </header>
      )}
      <div className={pad ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

const tones = {
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20',
  amber: 'bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20',
  red: 'bg-red-50 text-red-700 ring-red-600/20 dark:bg-red-500/10 dark:text-red-400 dark:ring-red-500/20',
  blue: 'bg-sky-50 text-sky-700 ring-sky-600/20 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/20',
  zinc: 'bg-zinc-100 text-zinc-700 ring-zinc-500/20 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-700',
  brand: 'bg-brand-50 text-brand-700 ring-brand-600/20 dark:bg-brand-500/10 dark:text-brand-300 dark:ring-brand-500/20',
}
export type Tone = keyof typeof tones
export function Badge({ tone = 'zinc', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return <span className={cx('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap', tones[tone], className)}>{children}</span>
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'good' | 'warn' | 'bad' }) {
  const color = tone === 'good' ? 'text-emerald-600 dark:text-emerald-400' : tone === 'warn' ? 'text-amber-600 dark:text-amber-400' : tone === 'bad' ? 'text-red-600 dark:text-red-400' : ''
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900/60 animate-slide-up">
      <div className="text-xs font-medium text-zinc-500 dark:text-zinc-400">{label}</div>
      <div className={cx('mt-1 text-2xl font-semibold tracking-tight tabular-nums', color)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{hint}</div>}
    </div>
  )
}

export function Bar({ value, tone = 'brand' }: { value: number; tone?: 'brand' | 'green' | 'amber' | 'red' }) {
  const c = { brand: 'bg-brand-500', green: 'bg-emerald-500', amber: 'bg-amber-500', red: 'bg-red-500' }[tone]
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
      <div className={cx('h-full rounded-full transition-all duration-700', c)} style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
    </div>
  )
}

export function Ring({ value, size = 88, label }: { value: number; size?: number; label?: string }) {
  const r = (size - 10) / 2, c = 2 * Math.PI * r
  const color = value >= 0.85 ? '#10b981' : value >= 0.6 ? '#f59e0b' : '#ef4444'
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="8" className="stroke-zinc-100 dark:stroke-zinc-800" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="8" stroke={color} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - value)} style={{ transition: 'stroke-dashoffset 0.9s ease' }} />
      </svg>
      <div className="absolute text-center">
        <div className="text-xl font-semibold tabular-nums">{Math.round(value * 100)}</div>
        {label && <div className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</div>}
      </div>
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <svg className={cx('h-4 w-4 animate-spin', className)} viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" /><path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" /></svg>
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-300 px-6 py-12 text-center dark:border-zinc-700 animate-fade-in">
      {icon && <div className="text-zinc-400">{icon}</div>}
      <div className="font-medium">{title}</div>
      {children && <div className="max-w-md text-sm text-zinc-500 dark:text-zinc-400">{children}</div>}
    </div>
  )
}

export function Alert({ tone = 'red', children, onClose }: { tone?: 'red' | 'amber' | 'blue'; children: ReactNode; onClose?: () => void }) {
  const c = { red: 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300',
    amber: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200',
    blue: 'border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900/60 dark:bg-sky-950/30 dark:text-sky-200' }[tone]
  return (
    <div role="alert" className={cx('flex items-start gap-3 rounded-lg border px-3.5 py-2.5 text-sm animate-slide-up', c)}>
      <div className="min-w-0 flex-1 break-words">{children}</div>
      {onClose && <button onClick={onClose} className="opacity-60 hover:opacity-100" aria-label="Dismiss">✕</button>}
    </div>
  )
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode; disabled?: boolean }[] }) {
  return (
    <div className="inline-flex rounded-lg bg-zinc-100 p-0.5 dark:bg-zinc-800/80">
      {items.map(it => (
        <button key={it.id} disabled={it.disabled} onClick={() => onChange(it.id)}
          className={cx('rounded-md px-3 py-1 text-sm font-medium transition-all disabled:opacity-40',
            value === it.id ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-950 dark:text-zinc-100' : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100')}>
          {it.label}
        </button>
      ))}
    </div>
  )
}

export function Pre({ children, className }: { children: ReactNode; className?: string }) {
  return <pre className={cx('max-h-64 overflow-auto rounded-lg bg-zinc-50 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all ring-1 ring-zinc-200 ring-inset dark:bg-zinc-950 dark:ring-zinc-800', className)}>{children}</pre>
}

export const statusMeta: Record<string, { label: string; tone: Tone; dot: string }> = {
  new: { label: 'Assessed', tone: 'zinc', dot: 'bg-zinc-400' },
  running: { label: 'Migrating', tone: 'blue', dot: 'bg-sky-500 animate-pulse' },
  equivalent: { label: 'Equivalent on tests', tone: 'green', dot: 'bg-emerald-500' },
  partial: { label: 'Partial match', tone: 'amber', dot: 'bg-amber-500' },
  compile_failed: { label: 'Did not compile', tone: 'red', dot: 'bg-red-500' },
  failed: { label: 'Failed', tone: 'red', dot: 'bg-red-500' },
  interrupted: { label: 'Interrupted', tone: 'zinc', dot: 'bg-zinc-400' },
}

export const Icon = {
  logo: <svg viewBox="0 0 32 32" className="h-7 w-7"><defs><linearGradient id="lg" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#ff7038" /><stop offset="1" stopColor="#c02508" /></linearGradient></defs><rect width="32" height="32" rx="8" fill="url(#lg)" /><path d="M9 11h8a4 4 0 0 1 0 8h-3l5 5M9 11v13M20 8l4 3-4 3" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  plus: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor"><path d="M10 4a1 1 0 0 1 1 1v4h4a1 1 0 1 1 0 2h-4v4a1 1 0 1 1-2 0v-4H5a1 1 0 1 1 0-2h4V5a1 1 0 0 1 1-1Z" /></svg>,
  sun: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor"><path d="M10 2a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V3a1 1 0 0 1 1-1Zm4 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0Zm-.46 4.95.7.7a1 1 0 0 0 1.42-1.41l-.71-.71a1 1 0 0 0-1.41 1.42ZM16 10a1 1 0 0 1 1-1h1a1 1 0 1 1 0 2h-1a1 1 0 0 1-1-1Zm-6 6a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1Zm-6-6a1 1 0 0 1-1 1H2a1 1 0 1 1 0-2h1a1 1 0 0 1 1 1Zm.05-5.95a1 1 0 0 1 1.41 0l.71.71A1 1 0 1 1 4.76 6.17l-.7-.7a1 1 0 0 1 0-1.42Zm11.9 0a1 1 0 0 1 0 1.42l-.71.7a1 1 0 1 1-1.41-1.41l.7-.71a1 1 0 0 1 1.42 0ZM5.46 14.95a1 1 0 0 1-1.41 0 1 1 0 0 1 0-1.41l.7-.71a1 1 0 1 1 1.42 1.41l-.71.71Z" /></svg>,
  moon: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor"><path d="M17.3 13.35A8 8 0 0 1 6.65 2.7a8 8 0 1 0 10.65 10.65Z" /></svg>,
  upload: <svg viewBox="0 0 24 24" className="h-8 w-8" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  file: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M5 2.75h6.5L15 6.25v11H5z" strokeLinejoin="round" /><path d="M11.5 2.75v3.5H15" strokeLinejoin="round" /></svg>,
  check: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor"><path fillRule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-8 8a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.4L8 12.58l7.3-7.3a1 1 0 0 1 1.4 0Z" clipRule="evenodd" /></svg>,
  x: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor"><path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" /></svg>,
  download: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor"><path d="M10.75 2.75a.75.75 0 0 0-1.5 0v8.6L6.3 8.24a.75.75 0 1 0-1.1 1.02l4.25 4.5a.75.75 0 0 0 1.1 0l4.25-4.5a.75.75 0 0 0-1.1-1.02l-2.95 3.1V2.75Z" /><path d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z" /></svg>,
  play: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor"><path d="M6.3 2.84A1.5 1.5 0 0 0 4 4.11v11.78a1.5 1.5 0 0 0 2.3 1.27l9.34-5.89a1.5 1.5 0 0 0 0-2.54L6.3 2.84Z" /></svg>,
  menu: <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor"><path fillRule="evenodd" d="M2 4.75A.75.75 0 0 1 2.75 4h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 4.75ZM2 10a.75.75 0 0 1 .75-.75h14.5a.75.75 0 0 1 0 1.5H2.75A.75.75 0 0 1 2 10Zm0 5.25a.75.75 0 0 1 .75-.75h14.5a.75.75 0 0 1 0 1.5H2.75a.75.75 0 0 1-.75-.75Z" clipRule="evenodd" /></svg>,
  trash: <svg viewBox="0 0 20 20" className="h-4 w-4" fill="currentColor"><path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.44c-.8.08-1.58.17-2.37.29a.75.75 0 1 0 .23 1.48l.15-.02.84 10.52A2.75 2.75 0 0 0 7.59 19h4.82a2.75 2.75 0 0 0 2.74-2.54l.84-10.52.15.02a.75.75 0 0 0 .23-1.48c-.79-.12-1.58-.21-2.37-.29v-.44A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.67.02 2.5.07v-.32c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.32C8.33 4.02 9.16 4 10 4Z" clipRule="evenodd" /></svg>,
}
