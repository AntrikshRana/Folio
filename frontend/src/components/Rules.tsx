import type { Rules } from '../types'
import './extras.css'

export const DEFAULT_RULES: Rules = { upload_policy: 'approval', max_file_mb: 50, max_files_per_guest: 5, room_quota_mb: 1024 }

const FILE_MB = [10, 25, 50, 100, 500, 1024]
const FILES = [1, 3, 5, 10, 20]
const ROOM_MB = [100, 500, 1024, 5120, 10240]
const size = (mb: number) => (mb >= 1024 ? `${mb / 1024} GB` : `${mb} MB`)
const withCurrent = (opts: number[], v: number) => (opts.includes(v) ? opts : [...opts, v].sort((a, b) => a - b))

/** The room rules as four dropdowns. Used when starting a session and by the teacher afterwards. */
export function RulesFields({ value, onChange }: { value: Rules; onChange: (patch: Partial<Rules>) => void }) {
  return (
    <div className="rules">
      <label>Who can upload
        <select className="field" value={value.upload_policy} onChange={e => onChange({ upload_policy: e.target.value as Rules['upload_policy'] })}>
          <option value="approval">Only people I approve</option>
          <option value="open">Everyone, I will block anyone</option>
        </select>
      </label>
      <label>Largest file (guests)
        <select className="field" value={value.max_file_mb} onChange={e => onChange({ max_file_mb: +e.target.value })}>
          {withCurrent(FILE_MB, value.max_file_mb).map(v => <option key={v} value={v}>{size(v)}</option>)}
        </select>
      </label>
      <label>Files per guest
        <select className="field" value={value.max_files_per_guest} onChange={e => onChange({ max_files_per_guest: +e.target.value })}>
          {withCurrent(FILES, value.max_files_per_guest).map(v => <option key={v} value={v}>{v}</option>)}
        </select>
      </label>
      <label>Room storage
        <select className="field" value={value.room_quota_mb} onChange={e => onChange({ room_quota_mb: +e.target.value })}>
          {withCurrent(ROOM_MB, value.room_quota_mb).map(v => <option key={v} value={v}>{size(v)}</option>)}
        </select>
      </label>
    </div>
  )
}
