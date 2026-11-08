import { useCallback, useEffect, useState } from 'react'

export const store = {
  get(key: string): string | null { try { return localStorage.getItem(key) } catch { return null } },
  set(key: string, value: string) { try { localStorage.setItem(key, value) } catch { /* storage unavailable */ } },
}

/** Hash routes: #/ , #/new , #/p/<id>/<tab> , #/benchmark */
export function useRoute(): [string[], (path: string) => void] {
  const parse = () => location.hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const [parts, setParts] = useState(parse)
  useEffect(() => {
    const on = () => setParts(parse())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const go = useCallback((path: string) => { location.hash = '#/' + path.replace(/^\//, '') }, [])
  return [parts, go]
}

export type Theme = 'light' | 'dark'
export function useTheme(): [Theme, () => void] {
  const initial = (): Theme => {
    const saved = store.get('theme')
    if (saved === 'light' || saved === 'dark') return saved
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  const [theme, setTheme] = useState<Theme>(initial)
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    document.documentElement.dataset.theme = theme
    store.set('theme', theme)
  }, [theme])
  return [theme, () => setTheme(t => (t === 'dark' ? 'light' : 'dark'))]
}

export function useElapsed(running: boolean) {
  const [s, setS] = useState(0)
  useEffect(() => {
    if (!running) return
    const start = Date.now(); setS(0)
    const t = setInterval(() => setS(Math.floor((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(t)
  }, [running])
  return s
}

export const pct = (x: number | null | undefined, digits = 0) => (x == null ? '—' : `${(x * 100).toFixed(digits)}%`)
export const fmtSecs = (s: number) => (s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`)
export const ago = (t: number) => {
  const d = Date.now() / 1000 - t
  if (d < 60) return 'just now'
  if (d < 3600) return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  return new Date(t * 1000).toLocaleDateString()
}
