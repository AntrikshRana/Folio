import { useEffect, useState } from 'react'
import { url } from './api'
import Room from './components/Room'
import SessionGate from './components/SessionGate'
import Stats from './components/Stats'
import type { Session } from './types'

const KEY = 'folio-session'

function loadSession(): Session | null {
  // A join link should always override a stale browser session, so guests land on the invited room
  // instead of an old one silently rehydrated from local storage.
  if (new URLSearchParams(location.search).has('join')) return null
  try { return JSON.parse(localStorage.getItem(KEY) ?? 'null') } catch { return null }
}

export default function App() {
  const [session, setSession] = useState<Session | null>(loadSession)
  // Warm the coordinator and node fleet once during startup so the first real API call is not a cold miss.
  useEffect(() => { fetch(url('/nodes/health')).catch(() => {}) }, [])
  const [hash, setHash] = useState(location.hash)
  useEffect(() => { const f = () => setHash(location.hash); addEventListener('hashchange', f); return () => removeEventListener('hashchange', f) }, [])
  const change = (s: Session | null) => {
    setSession(s)
    if (s) localStorage.setItem(KEY, JSON.stringify(s)); else localStorage.removeItem(KEY)
  }
  const toggleTheme = () => {
    const r = document.documentElement
    const dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme:dark)').matches
    r.dataset.theme = dark ? 'light' : 'dark'
  }
  const stats = hash.startsWith('#stats')                        // separate live stats page, no session needed
  return (
    <div className="wrap">
      <header>
        <div><h1>Folio</h1><p className="sub">big files go in, small pieces fan out to your nodes</p></div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {!stats && <a className="theme" href="#stats" target="_blank" rel="noreferrer">Live stats</a>}
          <button className="theme" onClick={toggleTheme}>Switch paper</button>
        </div>
      </header>
      {stats ? <Stats /> : session ? <Room session={session} onLeave={() => change(null)} /> : <SessionGate onEnter={change} />}
    </div>
  )
}
