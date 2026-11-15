import { useEffect, useState, type CSSProperties } from 'react'
import { url } from '../api'
import DbStats from './DbStats'
import './stats.css'

type NodeStat = { id: number; label: string; online: boolean; chunks: number; bytes: number }
type Cell = { from: number; chunks: number; nodes: number[]; copies: number }
type Ev = { id: number; ts: number; kind: string; file: string; idx: number | null; nodes: number[]; size: number | null; detail: string | null }
type Snap = {
  now: number; replicas: number; nodes: NodeStat[]
  totals: Record<string, number>
  uploads: { id: string; size: number; chunks: number; received: number }[]
  files: { id: string; size: number; status: string; chunks: number; cells: Cell[] }[]
  events: Ev[]; throughput: { t: number; bytes: number }[]
}

const MB = 1048576
const fmt = (b: number) => (b >= 1024 * MB ? (b / 1024 / MB).toFixed(2) + ' GB' : (b / MB).toFixed(1) + ' MB')
const nm = (i: number) => `Node ${String.fromCharCode(65 + i)}`
const col = (i: number) => `var(--n${i % 4})`
const names = (ns: number[]) => ns.map(nm).join(' + ')

function sentence(e: Ev): string {
  const f = `file ${e.file}`
  switch (e.kind) {
    case 'upload_started': return `${f}: upload started (${fmt(e.size ?? 0)})`
    case 'chunk_stored': return `${f}: chunk ${e.idx} stored on ${names(e.nodes)}`
    case 'upload_completed': return `${f}: upload finished, ${e.detail ?? ''}`
    case 'upload_cancelled': return `${f}: upload cancelled, chunks removed`
    case 'preview_started': return `${f}: previewed in the browser`
    case 'text_shared': return `a text was shared (${e.detail ?? ''})`
    case 'download_started': return `${f}: download started`
    case 'chunk_served': return `${f}: chunk ${e.idx} sent from ${names(e.nodes)}`
    case 'failover': return `${f}: chunk ${e.idx}: ${names(e.nodes)} failed, ${e.detail ?? ''}`
    default: return e.kind
  }
}

/** Colour a chunk cell by the nodes that hold it: one hard-edged stripe per node. */
function stripes(nodes: number[]): string {
  if (nodes.length === 0) return 'transparent'
  if (nodes.length === 1) return col(nodes[0])
  const w = 100 / nodes.length
  return `linear-gradient(90deg, ${nodes.map((n, i) => `${col(n)} ${i * w}% ${(i + 1) * w}%`).join(', ')})`
}

export default function Stats() {
  const [s, setS] = useState<Snap | null>(null)
  const [err, setErr] = useState(false)
  const [at, setAt] = useState(0)
  const [tab, setTab] = useState<'live' | 'db'>(location.hash === '#stats-db' ? 'db' : 'live')
  const pick = (t: 'live' | 'db') => { setTab(t); history.replaceState(null, '', t === 'db' ? '#stats-db' : '#stats') }

  useEffect(() => {
    let stop = false, timer: ReturnType<typeof setTimeout>
    const tick = async () => {
      if (!document.hidden) {
        try {
          const r = await fetch(url('/stats'))
          if (!r.ok) throw new Error()
          setS(await r.json()); setErr(false); setAt(Date.now())
        } catch { setErr(true) }
      }
      if (!stop) timer = setTimeout(tick, 1500)
    }
    tick()
    return () => { stop = true; clearTimeout(timer) }
  }, [])

  const t = s?.totals ?? {}
  const maxNodeBytes = Math.max(1, ...(s?.nodes.map(n => n.bytes) ?? [1]))
  const peak = Math.max(1, ...(s?.throughput.map(p => p.bytes) ?? [1]))
  const rate = (bytes: number) => (bytes / 10 / MB).toFixed(1)

  return (
    <>
      <section className="sheet st-head">
        <div className="tape" />
        <div>
          <h2>All stats</h2>
          <p className="hint">Every upload and download in this Folio server, updated every couple of seconds. File names and people are not shown.</p>
        </div>
        <div className="st-status">
          <span className={'st-dot' + (err ? ' bad' : s ? ' ok' : '')} />
          <span>{err ? 'Can’t reach the coordinator' : s ? `Live, updated ${new Date(at).toLocaleTimeString()}` : 'Connecting…'}</span>
          <a className="theme" href="#">Back to Folio</a>
        </div>
      </section>

      <div className="st-tabs" role="group" aria-label="Stats sections">
        <button className="theme" aria-pressed={tab === 'live'} onClick={() => pick('live')}>Live storage</button>
        <button className="theme" aria-pressed={tab === 'db'} onClick={() => pick('db')}>Database</button>
      </div>

      {tab === 'db' ? <DbStats /> : <>
      <div className="st-tiles">
        {[
          ['Files stored', t.files ?? 0], ['Data stored', fmt(t.bytes ?? 0)], ['Uploading now', t.uploads_active ?? 0],
          ['Chunks stored', t.chunks_stored ?? 0], ['Downloads', t.downloads ?? 0], ['Failovers', t.failovers ?? 0],
        ].map(([label, v]) => <div key={label as string} className="sheet st-tile"><b>{v}</b><small>{label}</small></div>)}
      </div>

      <div className="sec-t"><h2>Storage nodes</h2><span>each chunk is kept on {s?.replicas ?? 2} of them</span></div>
      <div className="st-nodes">
        {s?.nodes.map(n => (
          <div key={n.id} className={'sheet st-node' + (n.online ? '' : ' off')} style={{ '--c': col(n.id) } as CSSProperties}>
            <div className="st-node-top"><h3>{n.label}</h3><span className="chip">{n.online ? 'online' : 'down'}</span></div>
            <div className="pbar"><span style={{ width: (n.bytes / maxNodeBytes) * 100 + '%' }} /></div>
            <div className="meta"><span>{fmt(n.bytes)}</span><span>{n.chunks} chunk copies</span></div>
          </div>
        ))}
        {!s && <p className="hint">Waiting for the first update…</p>}
      </div>

      {s && s.uploads.length > 0 && (
        <>
          <div className="sec-t"><h2>Uploading now</h2><span>progress as chunks reach the nodes</span></div>
          <div className="st-list">
            {s.uploads.map(u => (
              <div key={u.id} className="sheet st-row">
                <b>file {u.id}</b>
                <div className="pbar"><span style={{ width: Math.min(100, u.size ? (u.received / u.size) * 100 : 0) + '%' }} /></div>
                <small>{fmt(u.received)} of {fmt(u.size)} · {u.chunks} chunks</small>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="sec-t"><h2>Where the chunks live</h2><span>each square is a chunk; its stripes are the nodes holding a copy</span></div>
      <div className="st-legend">
        {s?.nodes.map(n => <span key={n.id}><i style={{ background: col(n.id) }} />{n.label}</span>)}
        <span><i className="dashed" />fewer copies than wanted</span>
      </div>
      {!s || s.files.length === 0 ? <p className="hint">No files yet. Upload one in a session and it will appear here.</p> : (
        <div className="st-list">
          {s.files.map(f => (
            <div key={f.id} className="sheet st-file">
              <div className="st-file-head"><b>file {f.id}</b><span className="chip">{f.status === 'complete' ? 'stored' : 'uploading'}</span>
                <small>{fmt(f.size)} · {f.chunks} chunks</small></div>
              <div className="st-cells">
                {f.cells.map(c => (
                  <u key={c.from} className={c.copies < s.replicas ? 'thin' : ''} style={{ background: stripes(c.nodes) }}
                    title={(c.chunks === 1 ? `chunk ${c.from}` : `chunks ${c.from}–${c.from + c.chunks - 1}`) + ` → ${names(c.nodes)}`} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="st-two">
        <section>
          <div className="sec-t"><h2>Upload speed</h2><span>last 5 minutes, peak {rate(peak)} MB/s</span></div>
          <div className="sheet st-chart" role="img" aria-label="Upload speed over the last five minutes">
            {s?.throughput.map(p => <u key={p.t} style={{ height: Math.max(2, (p.bytes / peak) * 100) + '%' }} title={`${rate(p.bytes)} MB/s`} />)}
          </div>
        </section>
        <section>
          <div className="sec-t"><h2>Activity</h2><span>newest first</span></div>
          <div className="sheet st-feed">
            {(!s || s.events.length === 0) && <p className="hint">Nothing has happened yet.</p>}
            {s?.events.map(e => (
              <div key={e.id} className={'st-ev ' + e.kind}>
                <time>{new Date(e.ts * 1000).toLocaleTimeString()}</time><span>{sentence(e)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
      </>}
    </>
  )
}
