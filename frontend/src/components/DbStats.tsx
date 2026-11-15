import { useEffect, useState } from 'react'
import { url } from '../api'

type Col = { name: string; type: string; pk: number; notnull: boolean; default: string | null }
type Fk = { from: string[]; to: string[]; table: string; on_delete: string }
type Idx = { name: string; unique: boolean; origin: string; columns: string[] }
type Tbl = { name: string; rows: number; columns: Col[]; foreign_keys: Fk[]; indexes: Idx[] }
type Engine = { sqlite: string; journal_mode: string; foreign_keys: boolean; synchronous: string; encoding: string; page_size: number; pages: number; free_pages: number; bytes: number; wal_bytes: number }
type Check = { name: string; detail: string; bad: number }
type Query = { title: string; why: string; sql: string; plan: { detail: string; depth: number }[]; rows: number; ms: number }
type Snap = { engine: Engine; tables: Tbl[]; checks: Check[]; queries: Query[] }
type Demo = { note: string; steps: { title: string; why: string; sql: string; outcome: 'ok' | 'error'; message: string; counts: Record<string, number> }[] }

const fmtB = (b: number) => (b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB')

// ---- entity-relationship diagram, laid out from the foreign keys the database itself reports
const W = 240, HEAD = 28, ROW = 17, PAD = 8, GAPX = 90, GAPY = 24

function layout(tables: Tbl[]) {
  const by = new Map(tables.map(t => [t.name, t]))
  const parents = (t: Tbl) => [...new Set(t.foreign_keys.map(f => f.table))].filter(p => p !== t.name && by.has(p))
  const kids = new Map<string, string[]>()
  tables.forEach(t => parents(t).forEach(p => kids.set(p, [...(kids.get(p) ?? []), t.name])))
  const depth = new Map<string, number>()
  const d = (n: string, seen: string[]): number => {
    if (depth.has(n)) return depth.get(n)!
    if (seen.includes(n)) return 0                                  // guard against cycles
    const ps = parents(by.get(n)!)
    const v = ps.length ? 1 + Math.max(...ps.map(p => d(p, [...seen, n]))) : 0
    depth.set(n, v)
    return v
  }
  tables.forEach(t => d(t.name, []))
  tables.forEach(t => {                                             // a table nothing points from sits just left of its nearest child
    if (!parents(t).length && kids.has(t.name)) depth.set(t.name, Math.min(...kids.get(t.name)!.map(c => depth.get(c)!)) - 1)
  })
  const related = tables.filter(t => parents(t).length || kids.has(t.name))
  const alone = tables.filter(t => !related.includes(t))
  const hOf = (t: Tbl) => HEAD + t.columns.length * ROW + PAD
  const cols = new Map<number, Tbl[]>()
  related.forEach(t => cols.set(depth.get(t.name)!, [...(cols.get(depth.get(t.name)!) ?? []), t]))
  const pos = new Map<string, { x: number; y: number; h: number }>()
  let bottom = 0
  const keys = [...cols.keys()].sort((a, b) => a - b)
  keys.forEach((k, ci) => {
    let y = 10
    cols.get(k)!.forEach(t => { pos.set(t.name, { x: 10 + ci * (W + GAPX), y, h: hOf(t) }); y += hOf(t) + GAPY })
    bottom = Math.max(bottom, y)
  })
  let width = 10 + keys.length * (W + GAPX) - GAPX + 10
  if (alone.length) {                                               // tables with no relationships go in a row underneath
    const y = bottom + 24
    alone.forEach((t, i) => pos.set(t.name, { x: 10 + i * (W + 30), y, h: hOf(t) }))
    bottom = y + Math.max(...alone.map(hOf)) + 10
    width = Math.max(width, 10 + alone.length * (W + 30))
  }
  const rowY = (t: Tbl, col: string) => pos.get(t.name)!.y + HEAD + Math.max(0, t.columns.findIndex(c => c.name === col)) * ROW + ROW / 2
  const edges = related.flatMap(t => t.foreign_keys.filter(f => by.has(f.table) && f.table !== t.name).map(f => {
    const c = pos.get(t.name)!, p = pos.get(f.table)!, pt = by.get(f.table)!
    const y1 = rowY(t, f.from[0]), y2 = rowY(pt, f.to[0])
    const left = p.x < c.x
    const x1 = left ? c.x : c.x + W, x2 = left ? p.x + W : p.x + W
    const s = left ? -1 : 1
    return { key: `${t.name}>${f.table}>${f.from.join(',')}`, x1, y1, x2, y2, s, cascade: f.on_delete === 'CASCADE',
      d: `M${x1} ${y1} C${x1 + s * 45} ${y1} ${x2 - s * 45} ${y2} ${x2} ${y2}` }
  }))
  return { boxes: tables.map(t => ({ t, ...pos.get(t.name)! })), edges, width, height: bottom }
}

function ErDiagram({ tables }: { tables: Tbl[] }) {
  const { boxes, edges, width, height } = layout(tables)
  return (
    <div className="er-wrap">
      <svg className="er" viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img"
        aria-label="Entity relationship diagram: tables, their columns, and the foreign keys between them">
        {edges.map(e => (
          <g key={e.key}>
            <path d={e.d} className={'er-edge' + (e.cascade ? ' cascade' : '')} />
            <text className="er-card" x={e.x1 + e.s * 10} y={e.y1 - 5} textAnchor="middle">N</text>
            <text className="er-card" x={e.x2 - e.s * 10} y={e.y2 - 5} textAnchor="middle">1</text>
          </g>
        ))}
        {boxes.map(({ t, x, y, h }) => {
          const fks = new Set(t.foreign_keys.flatMap(f => f.from))
          return (
            <g key={t.name}>
              <rect className="er-box" x={x} y={y} width={W} height={h} rx={6} />
              <rect className="er-head" x={x} y={y} width={W} height={HEAD} rx={6} />
              <text className="er-title" x={x + 10} y={y + 19}>{t.name}</text>
              <text className="er-rows" x={x + W - 8} y={y + 19} textAnchor="end">{t.rows} rows</text>
              {t.columns.map((c, i) => {
                const ty = y + HEAD + i * ROW + 12.5
                return (
                  <g key={c.name}>
                    <text className="er-tag" x={x + 8} y={ty}>{[c.pk ? 'PK' : '', fks.has(c.name) ? 'FK' : ''].filter(Boolean).join(' ')}</text>
                    <text className="er-col" x={x + 46} y={ty}>{c.name}</text>
                    <text className="er-type" x={x + W - 8} y={ty} textAnchor="end">{c.type.toLowerCase()}</text>
                  </g>
                )
              })}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

const DESIGN_NOTES: [string, string][] = [
  ['Composite primary keys', 'A chunk is identified by (file_id, idx) and a stored copy by (file_id, idx, node_id), so the same copy can never be recorded twice.'],
  ['A junction table for copies', 'chunk_replicas turns "one chunk, many nodes" into rows. Chunks never carry a repeating list of nodes, and the number of copies can change without altering the schema.'],
  ['Foreign keys with cascades', 'Cancelling an upload is one DELETE: its chunks and copies go with it. Expiring a session removes its members, files and texts the same way (see the live demo below).'],
  ['CHECK and UNIQUE constraints', 'Roles, file status and sizes are validated by the database itself, and session codes and member tokens are unique, so a bug in the app cannot store nonsense.'],
  ['Hashed credentials', 'Only a SHA-256 hash of each member token is stored, so a leaked database file does not leak logins.'],
  ['Indexes where queries need them', 'idx_replicas_node serves the per-node load queries and idx_files_session the file list. The query lab shows the plan with and without an index.'],
  ['WAL journaling', 'Write-ahead logging lets readers (downloads, this page) continue while an upload writes.'],
  ['Immediate transactions for check-then-insert', 'Quota and per-person limits are checked and applied inside BEGIN IMMEDIATE, so simultaneous uploads cannot oversubscribe a room. A test sends 8 at once into a 3 MB room and exactly 3 get in.'],
  ['Counters beside an event log', 'stat_counters keeps cheap running totals while the events table is trimmed to 5,000 rows. Events deliberately have no foreign keys so history survives deleted files.'],
  ['Safe, repeatable migrations', 'New columns are added with ALTER TABLE only when PRAGMA table_info says they are missing, and databases from earlier versions were upgraded in tests without losing data.'],
  ['Parameterised queries', 'User input reaches SQL only as bound parameters. Column names in settings updates come from a fixed model, never from the request.'],
]

export default function DbStats() {
  const [d, setD] = useState<Snap | null>(null)
  const [err, setErr] = useState(false)
  const [demo, setDemo] = useState<Demo | null>(null)

  useEffect(() => {
    let stop = false, timer: ReturnType<typeof setTimeout>
    const tick = async () => {
      if (!document.hidden) {
        try { const r = await fetch(url('/stats/db')); if (!r.ok) throw new Error(); setD(await r.json()); setErr(false) } catch { setErr(true) }
      }
      if (!stop) timer = setTimeout(tick, 5000)
    }
    tick()
    return () => { stop = true; clearTimeout(timer) }
  }, [])
  const runDemo = () => fetch(url('/stats/db/demo')).then(r => r.json()).then(setDemo).catch(() => setErr(true))
  useEffect(() => { runDemo() }, [])

  const e = d?.engine
  const idxCount = d?.tables.reduce((n, t) => n + t.indexes.filter(i => i.origin === 'c').length, 0) ?? 0
  return (
    <>
      {err && <p className="err">Can’t reach the coordinator.</p>}
      <div className="sec-t"><h2>The database engine</h2><span>SQLite, read live from the running server</span></div>
      <div className="st-tiles">
        {e ? ([
          ['SQLite version', e.sqlite], ['Journal mode', e.journal_mode.toUpperCase()], ['Foreign keys', e.foreign_keys ? 'ON' : 'OFF'],
          ['Synchronous', e.synchronous], ['Page size', e.page_size + ' B'], ['Database size', fmtB(e.bytes)],
          ['Tables', d!.tables.length], ['Indexes', idxCount],
        ] as [string, string | number][]).map(([k, v]) => <div key={k} className="sheet st-tile"><b>{v}</b><small>{k}</small></div>)
          : <p className="hint">Loading…</p>}
      </div>

      <div className="sec-t"><h2>Entity-relationship diagram</h2><span>drawn from the live foreign keys; dashed lines are ON DELETE CASCADE</span></div>
      <section className="sheet st-er">{d ? <ErDiagram tables={d.tables} /> : <p className="hint">Loading…</p>}</section>

      <div className="sec-t"><h2>Integrity report</h2><span>consistency checks run against the live data</span></div>
      <div className="st-checks">
        {d?.checks.map(c => (
          <div key={c.name} className="sheet st-check">
            <span className={'st-badge ' + (c.bad === 0 ? 'ok' : 'bad')}>{c.bad === 0 ? '✓ OK' : `${c.bad} found`}</span>
            <div><b>{c.name}</b><small>{c.detail}</small></div>
          </div>
        ))}
      </div>

      <div className="sec-t"><h2>Tables</h2><span>columns, keys and indexes</span></div>
      <div className="st-tables">
        {d?.tables.map(t => {
          const fk = new Set(t.foreign_keys.flatMap(f => f.from))
          return (
            <article key={t.name} className="sheet st-tbl">
              <div className="st-tbl-head"><h3>{t.name}</h3><span className="chip">{t.rows} rows</span></div>
              <table className="dbtable">
                <tbody>
                  {t.columns.map(c => (
                    <tr key={c.name}>
                      <td>{c.name}</td><td>{c.type.toLowerCase()}</td>
                      <td>{[c.pk ? 'PK' : '', fk.has(c.name) ? 'FK' : '', c.notnull && !c.pk ? 'NOT NULL' : ''].filter(Boolean).join(' · ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {t.foreign_keys.map(f => <small key={f.from.join()} className="st-note">({f.from.join(', ')}) → {f.table}({f.to.join(', ')}) · on delete {f.on_delete.toLowerCase()}</small>)}
              {t.indexes.map(i => <small key={i.name} className="st-note">{i.unique ? 'unique ' : ''}index {i.origin === 'c' ? i.name : `(${i.origin === 'pk' ? 'primary key' : 'unique constraint'})`} on ({i.columns.join(', ')})</small>)}
            </article>
          )
        })}
      </div>

      <div className="sec-t"><h2>Query lab</h2><span>real queries Folio runs, with the plan SQLite chose and the time taken (best of 3)</span></div>
      <div className="st-list">
        {d?.queries.map(q => (
          <article key={q.title} className="sheet st-q">
            <div className="st-q-head"><b>{q.title}</b><span className="chip">{q.rows} rows · {q.ms} ms</span></div>
            <small>{q.why}</small>
            <pre className="sql">{q.sql}</pre>
            <ul className="plan">
              {q.plan.map((p, i) => <li key={i} className={p.detail.startsWith('SCAN') ? 'scan' : p.detail.startsWith('SEARCH') ? 'search' : ''} style={{ paddingLeft: p.depth * 16 }}>{p.detail}</li>)}
            </ul>
          </article>
        ))}
      </div>

      <div className="sec-t"><h2>Live demo: constraints, transactions, cascades</h2>
        <button className="mini" onClick={runDemo}>Run again</button></div>
      {demo && <p className="hint">{demo.note}</p>}
      <div className="st-list">
        {demo?.steps.map((s, i) => (
          <article key={i} className="sheet st-step">
            <div className="st-q-head"><b>{i + 1}. {s.title}</b>
              <span className={'st-badge ' + (s.outcome === 'error' ? 'bad' : 'ok')}>{s.outcome === 'error' ? 'rejected' : 'ok'}</span></div>
            {s.why && <small>{s.why}</small>}
            <pre className="sql">{s.sql}</pre>
            <p className="st-msg">{s.message}</p>
            <small>files {s.counts.files} · chunks {s.counts.chunks} · copies {s.counts.chunk_replicas}</small>
          </article>
        ))}
      </div>

      <div className="sec-t"><h2>Design decisions</h2><span>what the schema is doing and why</span></div>
      <div className="st-notes">
        {DESIGN_NOTES.map(([t, body]) => <div key={t} className="sheet st-note-card"><b>{t}</b><p>{body}</p></div>)}
      </div>
    </>
  )
}
