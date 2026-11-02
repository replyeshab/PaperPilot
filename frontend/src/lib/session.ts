
const TOKEN_KEY = 'paperpilot.token'
export const tokenStore = {
  get(): string | null {
    try { return window.localStorage.getItem(TOKEN_KEY) } catch { return null }
  },
  set(token: string): void {
    try { window.localStorage.setItem(TOKEN_KEY, token) } catch { /* storage unavailable: session lasts this tab */ }
  },
  clear(): void {
    try { window.localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
  },
}

export function newId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function formatTime(value: string | Date = new Date()): string {
  const date = typeof value === 'string' ? new Date(value) : value
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
