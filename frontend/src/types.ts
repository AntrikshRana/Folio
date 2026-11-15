export type NodeInfo = { id: number; name: string; url: string; online: boolean; failed: boolean; throughput_mbps: number; chunks: number }
export type Chunk = { size: number; node: number; replicas: number }
export type Transfer = { id: string; name: string; size: number; sent: number; chunks: Chunk[]; count: number; minCopies: number; label: string; done: boolean; fid?: string; ended?: boolean; cancelled?: boolean }
export type FileRow = { id: string; preview: boolean; uploader?: string | null; filename: string; size: number; chunks: number; nodes: number[]; min_replicas: number; available: boolean }
/** allowed: may share; pending: the room needs approval and none was given; blocked: the teacher said no */
export type UploadState = 'allowed' | 'pending' | 'blocked'
export type Member = { id: string; name: string; role: 'host' | 'guest'; upload: UploadState }
export type Rules = { upload_policy: 'open' | 'approval'; max_file_mb: number; max_files_per_guest: number; room_quota_mb: number }
export type TextRow = { id: string; member_id: string | null; created_at: string; length: number; body: string | null; head: string; author: string | null }
export type SessionInfo = { code: string; title: string; expires_at: string; upload_policy: Rules['upload_policy']; limits: Rules & { preview_max_mb: number; text_max_chars: number }; room_used: number; members: Member[]; texts: TextRow[]; files: FileRow[] }
/** Stored in localStorage. hostToken exists only for the host; memberToken identifies this person to the server. */
export type Session = { code: string; name: string; hostToken?: string; memberToken?: string; memberId?: string }
