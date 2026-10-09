import { useState } from 'react'
import { API, post } from '../api'
import type { Session } from '../types'

export default function SessionGate({ onEnter }: { onEnter: (s: Session) => void }) {
  const invite = new URLSearchParams(location.search).get('join') ?? ''
  const [name, setName] = useState('')
  const [code, setCode] = useState(invite.toUpperCase())
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [waking, setWaking] = useState(false)

  async function go(kind: 'create' | 'join') {
    if (!name.trim()) return setErr('Please enter your name first.')
    if (kind === 'join' && !code.trim()) return setErr('Enter the session code you were given.')
    setBusy(true); setErr('')
    try {
      const r = kind === 'create'
        ? await post('/sessions', { name: name.trim() }, undefined, () => setWaking(true))
        : await post(`/sessions/${encodeURIComponent(code.trim())}/join`, { name: name.trim() }, undefined, () => setWaking(true))
      const d = await r.json()
      if (!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : 'Could not continue')
      history.replaceState(null, '', location.pathname)
      onEnter({ code: d.code, name: name.trim(), hostToken: d.host_token })
    } catch (e) {
      if (e instanceof TypeError) {            // the browser never got an answer
        setErr(`Can't reach the server at ${API}. ` + (import.meta.env.PROD && API === '/api'
          ? 'This build has no VITE_API_URL set: set it to your coordinator URL and redeploy the site.'
          : `Open ${API}/healthz in a new tab. If it shows {"ok":true}, the server is fine and CORS_ORIGINS is wrong; if it does not load, the server is down or the URL is wrong.`))
      } else setErr((e as Error).message)
    } finally { setBusy(false); setWaking(false) }
  }

  return (
    <div className="gate">
      <section className="sheet">
        <div className="tape" />
        <h2>Who are you?</h2>
        <input className="field" placeholder="Your name" maxLength={40} value={name} onChange={e => setName(e.target.value)} />
      </section>
      <div className="gate-cols">
        <section className="sheet">
          <h2>Start a session</h2>
          <p className="hint">You become the host: upload files, then share the code so others can download them.</p>
          <button className="btn" disabled={busy} onClick={() => go('create')}>Start session</button>
        </section>
        <section className="sheet">
          <h2>Join a session</h2>
          <p className="hint">{invite ? 'You were invited – just add your name.' : 'Enter the code the host shared with you.'}</p>
          <input className="field code-field" placeholder="K7Q2-9XMA" value={code} onChange={e => setCode(e.target.value.toUpperCase())} />
          <button className="btn" disabled={busy} onClick={() => go('join')}>Join</button>
        </section>
      </div>
      {waking && <p className="hint" style={{ textAlign: 'center' }}>Waking up the server – free hosting sleeps when idle, this can take up to a minute…</p>}
      {err && <p className="err">{err}</p>}
    </div>
  )
}
