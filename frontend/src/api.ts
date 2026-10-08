/** API base: '/api' in dev (Vite proxy), or VITE_API_URL at build time (e.g. your Render coordinator URL). */
const base = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '')
export const API = base ?? '/api'
export const url = (path: string) => API + path

export function post(path: string, body?: unknown, hostToken?: string) {
  return fetch(url(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(hostToken ? { 'X-Host-Token': hostToken } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
}
