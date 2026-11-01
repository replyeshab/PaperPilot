export type DocumentItem = { id: string; name: string; url: string; status: string }
export type ChatMessage = { id: string; role: 'assistant' | 'user'; content: string; time: string }
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch(`${API_BASE}/api${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } }) }
  catch { throw new Error('Could not reach the backend. Make sure the API is running, then try again.') }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `Request failed (${response.status}).`)
  return payload as T
}
export const api = {
  health: () => request<{ status: string }>('/health'),
  documents: () => request<DocumentItem[]>('/documents'),
  addDocument: (url: string) => request<DocumentItem>('/documents', { method: 'POST', body: JSON.stringify({ url }) }),
  uploadDocument: async (file: File) => {
    const form = new FormData(); form.append('file', file)
    let response: Response
    try { response = await fetch(`${API_BASE}/api/documents/upload`, { method: 'POST', body: form }) }
    catch { throw new Error('Could not reach the backend. Make sure the API is running, then try again.') }
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `Upload failed (${response.status}).`)
    return payload as DocumentItem
  },
  removeDocument: (id: string) => request<{ deleted: boolean }>(`/documents/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  chat: (question: string, newConversation = false, documentId?: string) => request<{ answer: string; run_id?: string | null }>('/chat', { method: 'POST', body: JSON.stringify({ question, new_conversation: newConversation, document_id: documentId || null }) }),
}
