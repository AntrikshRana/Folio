import { useState } from 'react'
import { post } from '../api'
import type { Rules, Session, SessionInfo } from '../types'
import { RulesFields } from './Rules'
import './extras.css'

const MB = 1048576

/** Host-only panel: change the room rules and decide who may upload. */
export default function Teacher({ session, info, reload }: { session: Session; info: SessionInfo; reload: () => unknown }) {
  const [err, setErr] = useState('')
  const rules: Rules = { upload_policy: info.upload_policy, max_file_mb: info.limits.max_file_mb,
    max_files_per_guest: info.limits.max_files_per_guest, room_quota_mb: info.limits.room_quota_mb }

  const send = async (path: string, body: unknown) => {
    setErr('')
    try {
      const r = await post(path, body, session.hostToken)
      if (!r.ok) { const d = await r.json().catch(() => ({})); setErr(typeof d.detail === 'string' ? d.detail : 'That change was not accepted.') }
    } catch { setErr('Can’t reach the server.') }
    reload()
  }
  const setMember = (id: string, allowed: boolean) => send(`/sessions/${session.code}/members/${id}/upload`, { allowed })

  const guests = info.members.filter(m => m.role === 'guest')
  const waiting = guests.filter(g => g.upload === 'pending').length
  const usedPct = Math.min(100, (info.room_used / (info.limits.room_quota_mb * MB)) * 100)

  return (
    <section className="sheet teacher">
      <div className="tape" />
      <h2>Teacher controls</h2>
      <RulesFields value={rules} onChange={patch => send(`/sessions/${session.code}/settings`, patch)} />
      <p className="hint">Limits apply to guests; you are exempt. Changes take effect on the next upload, and blocking someone stops their upload at its next chunk.</p>
      <div className="pbar" title="room storage used"><span style={{ width: usedPct + '%' }} /></div>
      <p className="hint">{(info.room_used / MB).toFixed(1)} MB of {info.limits.room_quota_mb} MB used in this room</p>
      {err && <p className="err">{err}</p>}

      <h3 className="people-h">People {waiting > 0 && <span className="chip">{waiting} waiting for approval</span>}</h3>
      {guests.length === 0 ? <p className="hint">Nobody has joined yet. Share the code or invite link.</p> : (
        <div className="people">
          {guests.map(g => (
            <div key={g.id} className="person">
              <b>{g.name}</b>
              <span className={'chip st-' + g.upload}>{g.upload === 'allowed' ? 'can upload' : g.upload === 'blocked' ? 'blocked' : 'waiting'}</span>
              <span className="person-actions">
                {g.upload !== 'allowed' && <button className="mini" onClick={() => setMember(g.id, true)}>{g.upload === 'pending' ? 'Approve' : 'Allow'}</button>}
                {g.upload !== 'blocked' && <button className="mini cancel" onClick={() => setMember(g.id, false)}>Block</button>}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
