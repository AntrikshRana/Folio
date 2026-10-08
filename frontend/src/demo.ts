const MB = 1048576
export const DEMOS = [
  { name: 'notes.txt', mb: 0.2, text: true, label: '200 KB' },
  { name: 'photo.jpg', mb: 4, text: false, label: '4 MB' },
  { name: 'report.pdf', mb: 25, text: false, label: '25 MB' },
  { name: 'dataset.csv', mb: 120, text: true, label: '120 MB' },
  { name: 'lecture.mp4', mb: 500, text: false, label: '500 MB' },
  { name: 'disk-image.iso', mb: 1024, text: false, label: '1 GB' },
]

/** Builds a demo file of the requested size. Repeating one 1 MB Blob keeps browser memory low even for 1 GB. */
export function demoFile(d: { name: string; mb: number; text: boolean }): File {
  const u = new Uint8Array(MB)
  if (d.text) { const line = new TextEncoder().encode('id,name,value\n1,folio,42\n'); for (let i = 0; i < MB; i++) u[i] = line[i % line.length] }
  else for (let o = 0; o < MB; o += 65536) crypto.getRandomValues(u.subarray(o, o + 65536))
  const unit = new Blob([u]), bytes = Math.round(d.mb * MB)
  const parts: Blob[] = Array(Math.floor(bytes / MB)).fill(unit)
  if (bytes % MB) parts.push(unit.slice(0, bytes % MB))
  return new File(parts, d.name)
}
