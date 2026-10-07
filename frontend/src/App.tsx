import { useEffect, useRef, useState, type CSSProperties } from 'react'

const MB = 1048576
const SIZES = [1, 2, 4, 8, 16, 32, 64]
type NodeInfo = { id: number; name: string; url: string; online: boolean; throughput_mbps: number; chunks: number }
type Transfer = { id: string; name: string; size: number; sent: number; chunks: { size: number; node: number }[]; label: string; done: boolean; fid?: string }
type FileRow = { id: string; filename: string; size: number; chunks: number; nodes: number[]; available: boolean }

const fmt = (b: number) => (b >= 1024 * MB ? (b / 1024 / MB).toFixed(2) + ' GB' : (b / MB).toFixed(1) + ' MB')
const post = (url: string, body?: unknown) =>
  fetch('/api' + url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })

export default function App() {
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [transfers, setTransfers] = useState<Transfer[]>([])
  const [mode, setMode] = useState<'auto' | 'fixed'>('auto')
  const [fixedIdx, setFixedIdx] = useState(3)
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const [library, setLibrary] = useState<FileRow[]>([])
  const loadLibrary = () => fetch('/api/files').then(r => r.json()).then(setLibrary).catch(() => {})

  useEffect(() => {
    const poll = () => { fetch('/api/nodes/health').then(r => r.json()).then(setNodes).catch(() => setNodes([])); loadLibrary() }
    poll(); const t = setInterval(poll, 2000); return () => clearInterval(t)
  }, [])

  const patch = (id: string, f: (t: Transfer) => Partial<Transfer>) =>
    setTransfers(ts => ts.map(t => (t.id === id ? { ...t, ...f(t) } : t)))

  async function upload(file: File) {
    const key = crypto.randomUUID(), m = mode, fixed = SIZES[fixedIdx]
    setTransfers(ts => [{ id: key, name: file.name, size: file.size, sent: 0, chunks: [], label: 'starting…', done: false }, ...ts])
    try {
      const init = await (await post('/upload/init', { filename: file.name, size: file.size, mode: m, chunk_size_mb: fixed })).json()
      patch(key, () => ({ fid: init.upload_id }))
      let off = 0, idx = 0, mb: number = init.chunk_size_mb
      while (off < file.size) {
        const blob = file.slice(off, off + mb * MB)
        const r = await fetch(`/api/upload/${init.upload_id}/chunk/${idx}`, { method: 'PUT', body: blob })
        if (!r.ok) throw new Error((await r.json()).detail ?? 'chunk failed')
        const a = await r.json()
        off += blob.size; idx++
        mb = m === 'auto' ? a.next_chunk_size_mb : fixed
        patch(key, t => ({ sent: off, chunks: [...t.chunks, { size: blob.size, node: a.node_index }], label: `chunk size ${Math.round(blob.size / MB)} MB` }))
      }
      const c = await post(`/upload/${init.upload_id}/complete`)
      if (!c.ok) throw new Error((await c.json()).detail)
      patch(key, t => ({ done: true, label: `${t.chunks.length} chunks stored` }))
      loadLibrary()
    } catch (e) {
      patch(key, () => ({ label: 'failed: ' + (e as Error).message }))
    }
  }
  const take = (fl: FileList | null) => fl && Array.from(fl).forEach(upload)

  return (
    <div className="wrap">
      <header>
        <div><h1>Folio</h1><p className="sub">big files go in, small pieces fan out to your nodes</p></div>
        <button className="theme" onClick={() => {
          const r = document.documentElement
          const dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme:dark)').matches
          r.dataset.theme = dark ? 'light' : 'dark'
        }}>Switch paper</button>
      </header>

      <div className="grid">
        <section className="sheet up">
          <div className="tape" />
          <h2>Upload a file</h2>
          <label className={'drop' + (over ? ' over' : '')}
            onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
            onDrop={e => { e.preventDefault(); setOver(false); take(e.dataTransfer.files) }}>
            <svg viewBox="0 0 48 48"><path d="M8 30v10h32V30M24 6v26M14 16L24 6l10 10" /></svg>
            <div className="big">Drop a file here, or click to choose</div>
            <span className="note">any size – it gets split for you</span>
            <input ref={input} type="file" multiple hidden onChange={e => { take(e.target.files); e.target.value = '' }} />
          </label>
          <div className="row">
            <div className="seg" data-m={mode === 'auto' ? 'auto' : 'manual'}>
              <i /><button onClick={() => setMode('auto')}>Adaptive</button><button onClick={() => setMode('fixed')}>Fixed</button>
            </div>
          </div>
          <div className="size">
            <b>{mode === 'auto' ? 'Auto' : SIZES[fixedIdx] + ' MB'}</b>
            <input type="range" min={0} max={6} value={fixedIdx} disabled={mode === 'auto'} onChange={e => setFixedIdx(+e.target.value)} />
            <p className="hint">{mode === 'auto' ? 'The coordinator measures each node and suggests the next chunk size (1–64 MB).' : `Every chunk will be exactly ${SIZES[fixedIdx]} MB.`}</p>
          </div>
        </section>

        <section>
          <h2 style={{ marginBottom: 18 }}>Storage nodes</h2>
          <div className="nodes">
            {nodes.length === 0 && <p className="hint">Can’t reach the coordinator on port 8000. Is the backend running?</p>}
            {nodes.map(n => (
              <div key={n.id} className={'sheet card' + (n.online ? '' : ' off')} style={{ '--c': `var(--n${n.id % 4})` } as CSSProperties}>
                <div className="pin" /><span className="stamp">{n.online ? 'ONLINE' : 'DOWN'}</span>
                <h3>{n.name}</h3><small>{n.url}</small>
                <div className="bar"><span style={{ width: Math.min(100, n.throughput_mbps) + '%' }} /></div>
                <div className="meta"><span>{n.online ? Math.round(n.throughput_mbps) + ' MB/s' : 'unreachable'}</span><span>{n.chunks} chunks held</span></div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="sec-t"><h2>On the desk</h2><span>wider squares = bigger chunks</span></div>
      <div className="files">
        {transfers.map(t => {
          const p = Math.min(100, (t.sent / t.size) * 100)
          return (
            <article key={t.id} className={'sheet file' + (t.done ? ' done' : '')}>
              <div className="tape" />
              <div className="fh"><h3>{t.name}</h3><span className="chip">{t.label}</span></div>
              <div className="pbar"><span style={{ width: p + '%' }} /></div>
              <div className="meta"><span>{p.toFixed(0)}% · {fmt(t.sent)} of {fmt(t.size)}</span><span>{t.chunks.length} chunks</span></div>
              <div className="chunks">
                {t.chunks.slice(-500).map((c, i) => (
                  <u key={i} title={fmt(c.size)} style={{ width: 8 + Math.log2(c.size / MB + 1) * 5, '--c': `var(--n${c.node % 4})` } as CSSProperties} />
                ))}
              </div>
              <div className="done-stamp">STORED</div>
              {t.done && t.fid && <a className="btn dl" href={`/api/download/${t.fid}`}>Download</a>}
            </article>
          )
        })}
      </div>
      {transfers.length === 0 && <div className="sheet empty">Nothing uploading yet – drop a file above.</div>}

      <div className="sec-t"><h2>Stored files</h2><span>saved in the database, ready to download</span></div>
      {library.length === 0 ? <p className="hint">No finished uploads yet.</p> : (
        <div className="lib">
          {library.map(f => (
            <div key={f.id} className="sheet lib-row">
              <div className="lib-name"><b>{f.filename}</b><small>{fmt(f.size)} · {f.chunks} chunks</small></div>
              <span className="dots" title="nodes holding chunks">
                {f.nodes.map(n => <i key={n} style={{ '--c': `var(--n${n % 4})` } as CSSProperties} />)}
              </span>
              {f.available
                ? <a className="btn dl" href={`/api/download/${f.id}`}>Download</a>
                : <button className="btn dl" disabled>Node offline</button>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
