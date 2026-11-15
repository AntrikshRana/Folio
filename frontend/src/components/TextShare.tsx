import { useState } from 'react'
import { authHeaders, post, url } from '../api'
import { copyText } from '../copy'
import type { Session, SessionInfo } from '../types'
import './extras.css'

const when = (s: string) => new Date(s.replace(' ', 'T') + 'Z').toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

/** Short texts (notes, links, code) that anyone in the room can copy with one click. */
export default function TextShare({ session, info, canShare, isHost, reload }:
  { session: Session; info: SessionInfo; canShare: boolean; isHost: boolean; reload: () => unknown }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [full, setFull] = useState<Record<string, string>>({})     // long texts, loaded on demand
  const [copied, setCopied] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const base = `/sessions/${session.code}/texts`

  async function share() {
    if (!text.trim()) return
    setBusy(true); setErr('')
    try {
      const r = await post(base, { body: text }, session.hostToken, undefined, session.memberToken)
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(typeof d.detail === 'string' ? d.detail : 'Could not share that text.') }
      setText(''); reload()
    } catch (e) { setErr(e instanceof TypeError ? 'Can’t reach the server.' : (e as Error).message) }
    finally { setBusy(false) }
  }
  async function load(id: string): Promise<string | undefined> {
    try {
      const d = await (await fetch(url(`${base}/${id}`))).json()
      if (typeof d.body === 'string') { setFull(f => ({ ...f, [id]: d.body })); return d.body }
    } catch { /* shown below */ }
    setNote('Could not load that text.')
  }
  async function copy(id: string, body: string | null) {
    setNote('')
    const txt = body ?? full[id] ?? await load(id)
    if (txt === undefined) return
    const ok = await copyText(txt)
    setCopied(ok ? id : null)
    if (ok) setTimeout(() => setCopied(c => (c === id ? null : c)), 1800)
    else setNote('Your browser blocked copying. Select the text and copy it by hand.')
  }
  const remove = (id: string) => fetch(url(`${base}/${id}`), { method: 'DELETE', headers: authHeaders(session) }).then(() => reload()).catch(() => {})

  return (
    <>
      <div className="sec-t"><h2>Shared text</h2><span>notes, links or code anyone here can copy</span></div>
      {canShare && (
        <section className="sheet textbox">
          <textarea className="field" rows={3} maxLength={info.limits.text_max_chars} value={text} placeholder="Type or paste something to share…"
            onChange={e => setText(e.target.value)} />
          <div className="textbox-row">
            <small>{text.length} / {info.limits.text_max_chars}</small>
            <button className="btn" disabled={busy || !text.trim()} onClick={share}>Share text</button>
          </div>
          {err && <p className="err">{err}</p>}
        </section>
      )}
      {note && <p className="err">{note}</p>}
      {info.texts.length === 0 ? <p className="hint">Nothing shared yet.</p> : (
        <div className="texts">
          {info.texts.map(t => {
            const body = t.body ?? full[t.id]
            return (
              <article key={t.id} className="sheet text">
                <div className="text-head">
                  <span><b>{t.author ?? 'Someone'}</b> <small>{when(t.created_at)}</small></span>
                  <span className="text-actions">
                    <button className="mini" onClick={() => copy(t.id, t.body)}>{copied === t.id ? 'Copied!' : 'Copy'}</button>
                    {(isHost || t.member_id === session.memberId) && <button className="mini cancel" onClick={() => remove(t.id)}>Delete</button>}
                  </span>
                </div>
                <pre>{body ?? t.head + '…'}</pre>
                {body === undefined && <button className="mini" onClick={() => load(t.id)}>Show all {t.length} characters</button>}
              </article>
            )
          })}
        </div>
      )}
    </>
  )
}
