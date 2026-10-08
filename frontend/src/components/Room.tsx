import { useEffect, useState, type CSSProperties } from 'react'
import { post, url } from '../api'
import { DEMOS, demoFile } from '../demo'
import type { NodeInfo, Session, SessionInfo, Transfer } from '../types'

const MB = 1048576
const SIZES = [1, 2, 4, 8, 16, 32, 64]
const fmt = (b: number) => (b >= 1024 * MB ? (b / 1024 / MB).toFixed(2) + ' GB' : (b / MB).toFixed(1) + ' MB')
const copies = (cs: Transfer['chunks']) => cs.reduce((m, c) => Math.min(m, c.replicas), Infinity)

export default function Room({ session, onLeave }: { session: Session; onLeave: () => void }) {
  const isHost = !!session.hostToken
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [info, setInfo] = useState<SessionInfo | null>(null)
  const [transfers, setTransfers] = useState<Transfer[]>([])
  const [mode, setMode] = useState<'auto' | 'fixed'>('auto')
  const [fixedIdx, setFixedIdx] = useState(3)
  const [over, setOver] = useState(false)
  const [copied, setCopied] = useState(false)

  const loadNodes = () => fetch(url('/nodes/health')).then(r => r.json()).then(setNodes).catch(() => setNodes([]))
  const loadInfo = () => fetch(url(`/sessions/${session.code}`))
    .then(r => { if (r.status === 404) { onLeave(); return null } return r.json() })
    .then(d => d && setInfo(d)).catch(() => {})
  useEffect(() => {
    const poll = () => { loadNodes(); loadInfo() }
    poll(); const t = setInterval(poll, 2000); return () => clearInterval(t)
  }, [session.code])

  const patch = (id: string, f: (t: Transfer) => Partial<Transfer>) =>
    setTransfers(ts => ts.map(t => (t.id === id ? { ...t, ...f(t) } : t)))

  async function upload(file: File) {
    const key = crypto.randomUUID(), m = mode, fixed = SIZES[fixedIdx]
    setTransfers(ts => [{ id: key, name: file.name, size: file.size, sent: 0, chunks: [], label: 'starting…', done: false }, ...ts])
    try {
      const ir = await post('/upload/init', { session: session.code, filename: file.name, size: file.size, mode: m, chunk_size_mb: fixed }, session.hostToken)
      const init = await ir.json()
      if (!ir.ok) throw new Error(typeof init.detail === 'string' ? init.detail : 'init failed')
      patch(key, () => ({ fid: init.upload_id }))
      let off = 0, idx = 0, mb: number = init.chunk_size_mb
      while (off < file.size) {
        const blob = file.slice(off, off + mb * MB)
        const r = await fetch(url(`/upload/${init.upload_id}/chunk/${idx}`), { method: 'PUT', body: blob })
        if (!r.ok) throw new Error((await r.json()).detail ?? 'chunk failed')
        const a = await r.json()
        off += blob.size; idx++
        mb = m === 'auto' ? a.next_chunk_size_mb : init.chunk_size_mb
        patch(key, t => ({ sent: off, chunks: [...t.chunks, { size: blob.size, node: a.node_index, replicas: a.replicas }], label: `chunk size ${Math.round(blob.size / MB)} MB` }))
      }
      const c = await post(`/upload/${init.upload_id}/complete`)
      if (!c.ok) throw new Error((await c.json()).detail)
      patch(key, t => ({ done: true, label: `${t.chunks.length} chunks stored` }))
      loadInfo()
    } catch (e) {
      patch(key, () => ({ label: 'failed: ' + (e as Error).message }))
    }
  }
  const take = (fl: FileList | null) => fl && Array.from(fl).forEach(upload)

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(`${location.origin}/?join=${session.code}`); setCopied(true); setTimeout(() => setCopied(false), 1800) } catch { /* clipboard unavailable */ }
  }
  const dl = (id: string) => url(`/sessions/${session.code}/files/${id}/download`)

  return (
    <>
      <section className="sheet room">
        <div className="tape" />
        <div className="room-head">
          <div><span className="note-h">session code</span><div className="code">{session.code}</div></div>
          <div className="room-actions">
            <button className="btn" onClick={copyLink}>{copied ? 'Link copied!' : 'Copy invite link'}</button>
            <button className="theme" onClick={onLeave}>Leave</button>
          </div>
        </div>
        <div className="members">
          {info?.members.map(m => <span key={m.name} className={'who ' + m.role}>{m.name}<small>{m.role}</small></span>)}
        </div>
        <p className="hint">{isHost
          ? 'Share the code or invite link. Anyone who joins can download every file in this session.'
          : `You joined as ${session.name}. The host uploads files – you can download them below.`}</p>
      </section>

      <div className="grid">
        {isHost ? (
          <section className="sheet up">
            <div className="tape" />
            <h2>Upload a file</h2>
            <label className={'drop' + (over ? ' over' : '')}
              onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
              onDrop={e => { e.preventDefault(); setOver(false); take(e.dataTransfer.files) }}>
              <svg viewBox="0 0 48 48"><path d="M8 30v10h32V30M24 6v26M14 16L24 6l10 10" /></svg>
              <div className="big">Drop a file here, or click to choose</div>
              <span className="note">any size – it gets split for you</span>
              <input type="file" multiple hidden onChange={e => { take(e.target.files); e.target.value = '' }} />
            </label>
            <div className="demos">
              <span className="note-h">or try a demo file:</span>
              {DEMOS.map(d => <button key={d.name} className="chip-btn" onClick={() => upload(demoFile(d))}>{d.name} <small>{d.label}</small></button>)}
            </div>
            <div className="row">
              <div className="seg" data-m={mode === 'auto' ? 'auto' : 'manual'}>
                <i /><button onClick={() => setMode('auto')}>Adaptive</button><button onClick={() => setMode('fixed')}>Fixed</button>
              </div>
            </div>
            <div className="size">
              <b>{mode === 'auto' ? 'Auto' : SIZES[fixedIdx] + ' MB'}</b>
              <input type="range" min={0} max={6} value={fixedIdx} disabled={mode === 'auto'} onChange={e => setFixedIdx(+e.target.value)} />
              <p className="hint">{mode === 'auto' ? 'The coordinator measures each node and suggests the next chunk size.' : `Every chunk will be ${SIZES[fixedIdx]} MB (capped by the server's limit).`}</p>
            </div>
          </section>
        ) : (
          <section className="sheet up">
            <div className="tape" />
            <h2>Guest access</h2>
            <p className="hint">Files appear under “Shared files” the moment the host finishes uploading. Nothing to do here but download.</p>
          </section>
        )}

        <section>
          <h2 style={{ marginBottom: 18 }}>Storage nodes</h2>
          <div className="nodes">
            {nodes.length === 0 && <p className="hint">Can’t reach the coordinator. Is the backend running?</p>}
            {nodes.map(n => (
              <div key={n.id} className={'sheet card' + (n.online ? '' : ' off')} style={{ '--c': `var(--n${n.id % 4})` } as CSSProperties}>
                <div className="pin" /><span className="stamp">{n.failed ? 'FAILED' : n.online ? 'ONLINE' : 'DOWN'}</span>
                <h3>{n.name}</h3><small>{n.url}</small>
                <div className="bar"><span style={{ width: Math.min(100, n.throughput_mbps) + '%' }} /></div>
                <div className="meta"><span>{n.online ? Math.round(n.throughput_mbps) + ' MB/s' : 'unreachable'}</span><span>{n.chunks} chunks held</span></div>
                {isHost && (
                  <button className="mini" disabled={!n.online && !n.failed}
                    onClick={() => post(`/nodes/${n.id}/${n.failed ? 'recover' : 'fail'}`, undefined, session.hostToken).then(loadNodes)}>
                    {n.failed ? 'Recover node' : 'Simulate failure'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      </div>

      {isHost && transfers.length > 0 && (
        <>
          <div className="sec-t"><h2>On the desk</h2><span>wider squares = bigger chunks</span></div>
          <div className="files">
            {transfers.map(t => {
              const p = Math.min(100, (t.sent / t.size) * 100)
              return (
                <article key={t.id} className={'sheet file' + (t.done ? ' done' : '')}>
                  <div className="tape" />
                  <div className="fh"><h3>{t.name}</h3><span className="chip">{t.label}</span></div>
                  <div className="pbar"><span style={{ width: p + '%' }} /></div>
                  <div className="meta"><span>{p.toFixed(0)}% · {fmt(t.sent)} of {fmt(t.size)}</span>
                    <span>{t.chunks.length} chunks{t.chunks.length > 0 && ` · ×${copies(t.chunks)} copies`}</span></div>
                  <div className="chunks">
                    {t.chunks.slice(-500).map((c, i) => (
                      <u key={i} title={fmt(c.size)} style={{ width: 8 + Math.log2(c.size / MB + 1) * 5, '--c': `var(--n${c.node % 4})` } as CSSProperties} />
                    ))}
                  </div>
                  <div className="done-stamp">STORED</div>
                </article>
              )
            })}
          </div>
        </>
      )}

      <div className="sec-t"><h2>Shared files</h2><span>everyone in this session can download these</span></div>
      {!info || info.files.length === 0 ? <p className="hint">No finished uploads yet.</p> : (
        <div className="lib">
          {info.files.map(f => (
            <div key={f.id} className="sheet lib-row">
              <div className="lib-name"><b>{f.filename}</b><small>{fmt(f.size)} · {f.chunks} chunks · ×{f.min_replicas} copies</small></div>
              <span className="dots" title="nodes holding chunks">
                {f.nodes.map(n => <i key={n} style={{ '--c': `var(--n${n % 4})` } as CSSProperties} />)}
              </span>
              {f.available ? <a className="btn dl" href={dl(f.id)}>Download</a> : <button className="btn dl" disabled>Node offline</button>}
            </div>
          ))}
        </div>
      )}
    </>
  )
}
