import { tokenStore } from '../lib/session'

export type UserInfo = { id: string; email: string }
export type AuthResult = { token: string; user: UserInfo }
export type DocumentItem = {
  id: string
  name: string
  source_type: 'url' | 'upload'
  source: string
  shared: boolean
  created_at: string
  index_status: 'indexing' | 'ready' | 'error'
  index_error?: string | null
}
export type Quota = { used: number; limit: number; remaining: number }
export type ChatResult = { answer: string; conversation_id: string; document_id: string; quota: Quota }
export type StoredMessage = { id: string; role: 'user' | 'assistant'; content: string; created_at: string }
export type ConversationResult = { conversation_id: string | null; messages: StoredMessage[] }
export type ChatMessage = { id: string; role: 'user' | 'assistant'; content: string; time: string; failed?: boolean }
export type HealthResult = { status: 'ok' | 'degraded'; database: string; environment: string }

/** An error that is safe to show to the user. */
export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')
const TIMEOUTS: Record<'default' | 'chat' | 'upload', number> = { default: 20_000, chat: 150_000, upload: 480_000 }
const UNREACHABLE = 'Could not reach the PaperPilot server. Check your connection and try again.'

let onSessionExpired: (() => void) | null = null
/** App registers this so an expired session returns the user to the sign-in screen. */
export function setSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler
}

function messageFrom(payload: unknown, status: number): string {
  const detail = (payload as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg
  if (status === 413) return 'That file is too large.'
  if (status === 429) return 'Too many requests right now. Please wait a moment and try again.'
  if (status >= 500) return 'The server ran into a problem. Please try again in a moment.'
  return `Request failed (${status}).`
}

async function send(path: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  try {
    return await fetch(`${API_BASE}/api${path}`, { ...init, headers, signal: controller.signal })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The server took too long to respond. Please try again.', 0)
    }
    throw new ApiError(UNREACHABLE, 0)
  } finally {
    window.clearTimeout(timer)
  }
}

async function parse<T>(response: Response, path: string): Promise<T> {
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const isAuthCall = path.startsWith('/auth/login') || path.startsWith('/auth/signup')
    if (response.status === 401 && !isAuthCall) onSessionExpired?.()
    throw new ApiError(messageFrom(payload, response.status), response.status)
  }
  return payload as T
}

async function getJson<T>(path: string): Promise<T> {
  return parse<T>(await send(path, { headers: { Accept: 'application/json' } }, TIMEOUTS.default), path)
}

async function postJson<T>(path: string, body: unknown, timeoutMs = TIMEOUTS.default): Promise<T> {
  return parse<T>(await send(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  }, timeoutMs), path)
}

export const api = {
  health: () => getJson<HealthResult>('/health'),
  signup: (email: string, password: string) => postJson<AuthResult>('/auth/signup', { email, password }),
  login: (email: string, password: string) => postJson<AuthResult>('/auth/login', { email, password }),
  async logout(): Promise<void> {
    await send('/auth/logout', { method: 'POST' }, TIMEOUTS.default).catch(() => undefined)
  },
  me: () => getJson<UserInfo>('/auth/me'),
  quota: () => getJson<Quota>('/quota'),
  documents: () => getJson<DocumentItem[]>('/documents'),
  conversation: (documentId: string) =>
    getJson<ConversationResult>(`/documents/${encodeURIComponent(documentId)}/conversation`),
  addDocument: (url: string) => postJson<DocumentItem>('/documents', { url }, TIMEOUTS.upload),
  uploadDocument: async (file: File): Promise<DocumentItem> => {
    const form = new FormData()
    form.append('file', file)
    return parse<DocumentItem>(await send('/documents/upload', { method: 'POST', body: form }, TIMEOUTS.upload), '/documents/upload')
  },
  removeDocument: async (id: string): Promise<void> => {
    await parse<unknown>(await send(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }, TIMEOUTS.default), '/documents')
  },
  chat: (input: { question: string; documentId: string; newConversation: boolean }) =>
    postJson<ChatResult>('/chat', {
      question: input.question,
      document_id: input.documentId,
      new_conversation: input.newConversation,
    }, TIMEOUTS.chat),
}

/** Polls the health endpoint so the UI can show a message while a free-tier server wakes up. */
export async function waitForApi(onWaking: () => void, attempts = 8): Promise<HealthResult> {
  let lastError: unknown
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await api.health()
    } catch (error) {
      lastError = error
      if (attempt === 1) onWaking()
      await new Promise(resolve => setTimeout(resolve, Math.min(1500 * attempt, 6000)))
    }
  }
  throw lastError
}
