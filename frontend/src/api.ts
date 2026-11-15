/** API base: '/api' in dev (Vite proxy), or VITE_API_URL at build time (e.g. your Render coordinator URL). */
const base = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '')
export const API = base ?? '/api'
export const url = (path: string) => API + path

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

/** fetch that retries network-level failures. Opt-in via onWait, because free servers may still be waking up. */
export async function fetchRetry(input: string, init?: RequestInit, onWait?: () => void, tries = 10): Promise<Response> {
  for (let i = 0; ; i++) {
    try { return await fetch(input, init) }
    catch (e) { if (!onWait || i >= tries - 1) throw e; onWait(); await sleep(4000) }
  }
}

/** Headers that tell the server who is calling. */
export const authHeaders = (s: { hostToken?: string; memberToken?: string }): Record<string, string> => ({
  ...(s.hostToken ? { 'X-Host-Token': s.hostToken } : {}),
  ...(s.memberToken ? { 'X-Member-Token': s.memberToken } : {}),
})

export function post(path: string, body?: unknown, hostToken?: string, onWait?: () => void, memberToken?: string) {
  return fetchRetry(url(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders({ hostToken, memberToken }) },
    body: body ? JSON.stringify(body) : undefined,
  }, onWait)
}
