export type NodeInfo = { id: number; name: string; url: string; online: boolean; failed: boolean; throughput_mbps: number; chunks: number }
export type Chunk = { size: number; node: number; replicas: number }
export type Transfer = { id: string; name: string; size: number; sent: number; chunks: Chunk[]; label: string; done: boolean; fid?: string; ended?: boolean; cancelled?: boolean }
export type FileRow = { id: string; filename: string; size: number; chunks: number; nodes: number[]; min_replicas: number; available: boolean }
export type Member = { name: string; role: 'host' | 'guest' }
export type SessionInfo = { code: string; title: string; expires_at: string; members: Member[]; files: FileRow[] }
/** Stored in localStorage. hostToken exists only for the host. */
export type Session = { code: string; name: string; hostToken?: string }
