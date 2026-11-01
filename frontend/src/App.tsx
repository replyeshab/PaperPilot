import { useCallback, useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import { AddDocumentModal } from './components/AddDocumentModal'
import { AuthScreen } from './components/AuthScreen'
import { Composer } from './components/Composer'
import { MessageList } from './components/MessageList'
import { Sidebar, type ApiStatus } from './components/Sidebar'
import { Welcome } from './components/Welcome'
import {
  ApiError, api, setSessionExpiredHandler, waitForApi,
  type AuthResult, type ChatMessage, type DocumentItem, type Quota, type StoredMessage, type UserInfo,
} from './services/api'
import { formatTime, lastDocument, newId, tokenStore } from './lib/session'

type AuthState = 'checking' | 'signed-out' | 'signed-in'

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

function toChatMessage(message: StoredMessage): ChatMessage {
  return { id: message.id, role: message.role, content: message.content, time: formatTime(message.created_at) }
}

export default function App() {
  const [authState, setAuthState] = useState<AuthState>('checking')
  const [authNotice, setAuthNotice] = useState('')
  const [user, setUser] = useState<UserInfo | null>(null)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [transcripts, setTranscripts] = useState<Record<string, ChatMessage[]>>({})
  const [freshConversation, setFreshConversation] = useState<Record<string, boolean>>({})
  const [draft, setDraft] = useState('')
  const [pendingFor, setPendingFor] = useState<string | null>(null)
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const [quota, setQuota] = useState<Quota | null>(null)
  const [filter, setFilter] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')

  const selectedDoc = useMemo(() => documents.find(doc => doc.id === selectedId) ?? null, [documents, selectedId])
  const messages = transcripts[selectedId] ?? []
  const pending = pendingFor !== null && pendingFor === selectedId
  const lockedReason = quota && quota.remaining <= 0
    ? 'The shared request limit has been reached. Your past conversations are still available.'
    : null

  const loadLibrary = useCallback(async () => {
    const [docs, budget] = await Promise.all([api.documents(), api.quota()])
    setDocuments(docs)
    setQuota(budget)
    const preferred = lastDocument.get()
    setSelectedId(current => {
      if (docs.some(doc => doc.id === current)) return current
      if (preferred && docs.some(doc => doc.id === preferred)) return preferred
      return docs[0]?.id ?? ''
    })
  }, [])

  const signOut = useCallback((notice = '') => {
    tokenStore.clear()
    setUser(null)
    setDocuments([])
    setTranscripts({})
    setFreshConversation({})
    setQuota(null)
    setSelectedId('')
    setError('')
    setAuthNotice(notice)
    setAuthState('signed-out')
  }, [])

  useEffect(() => {
    setSessionExpiredHandler(() => signOut('Your session has expired. Please sign in again.'))
  }, [signOut])

  const boot = useCallback(async () => {
    setApiStatus('checking')
    try {
      await waitForApi(() => setApiStatus('waking'))
      setApiStatus('online')
    } catch (err) {
      setApiStatus('offline')
      setError(messageOf(err))
      return
    }
    if (!tokenStore.get()) {
      setAuthState('signed-out')
      return
    }
    try {
      setUser(await api.me())
      setAuthState('signed-in')
      await loadLibrary()
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) signOut()
      else setError(messageOf(err))
    }
  }, [loadLibrary, signOut])

  useEffect(() => { void boot() }, [boot])

  useEffect(() => {
    if (selectedId) lastDocument.set(selectedId)
  }, [selectedId])

  // Load the saved conversation whenever a document is opened.
  useEffect(() => {
    if (authState !== 'signed-in' || !selectedId) return
    let cancelled = false
    api.conversation(selectedId)
      .then(result => {
        if (!cancelled) setTranscripts(current => ({ ...current, [selectedId]: result.messages.map(toChatMessage) }))
      })
      .catch(err => { if (!cancelled) setError(messageOf(err)) })
    return () => { cancelled = true }
  }, [selectedId, authState])

  // Ctrl/⌘ + K starts a new conversation, matching the hint in the sidebar.
  const startNewConversation = useCallback(() => {
    if (!selectedId) return
    setTranscripts(current => ({ ...current, [selectedId]: [] }))
    setFreshConversation(current => ({ ...current, [selectedId]: true }))
    setError('')
  }, [selectedId])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        startNewConversation()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [startNewConversation])

  async function handleAuthenticated(result: AuthResult) {
    tokenStore.set(result.token)
    setAuthNotice('')
    setUser(result.user)
    setAuthState('signed-in')
    try {
      await loadLibrary()
    } catch (err) {
      setError(messageOf(err))
    }
  }

  async function logout() {
    await api.logout()
    signOut()
  }

  async function askQuestion(text: string) {
    const question = text.trim()
    const docId = selectedId
    if (!question || !docId || pendingFor || lockedReason) return

    const userMessage: ChatMessage = { id: newId(), role: 'user', content: question, time: formatTime() }
    setTranscripts(current => ({ ...current, [docId]: [...(current[docId] ?? []), userMessage] }))
    setDraft('')
    setPendingFor(docId)
    setError('')

    try {
      const result = await api.chat({ question, documentId: docId, newConversation: Boolean(freshConversation[docId]) })
      setFreshConversation(current => ({ ...current, [docId]: false }))
      setQuota(result.quota)
      const reply: ChatMessage = { id: newId(), role: 'assistant', content: result.answer, time: formatTime() }
      setTranscripts(current => ({ ...current, [docId]: [...(current[docId] ?? []), reply] }))
    } catch (err) {
      // Put the question back so the user can retry without retyping it.
      setTranscripts(current => ({
        ...current,
        [docId]: (current[docId] ?? []).filter(message => message.id !== userMessage.id),
      }))
      setDraft(question)
      setError(messageOf(err))
      if (err instanceof ApiError && err.status === 404) void loadLibrary().catch(() => undefined)
      else void api.quota().then(setQuota).catch(() => undefined)
    } finally {
      setPendingFor(null)
    }
  }

  async function addUrl(url: string) {
    setAdding(true)
    try {
      const doc = await api.addDocument(url)
      setDocuments(current => (current.some(item => item.id === doc.id) ? current : [...current, doc]))
      setSelectedId(doc.id)
      setShowAdd(false)
      setError('')
      setQuota(await api.quota())
    } finally {
      setAdding(false)
    }
  }

  async function uploadFile(file: File) {
    setAdding(true)
    try {
      const doc = await api.uploadDocument(file)
      setDocuments(current => [...current, doc])
      setSelectedId(doc.id)
      setShowAdd(false)
      setError('')
      setQuota(await api.quota())
    } finally {
      setAdding(false)
    }
  }

  async function removeDocument(doc: DocumentItem) {
    if (!window.confirm(`Remove “${doc.name}” from your library? Its conversation will be deleted too.`)) return
    try {
      await api.removeDocument(doc.id)
      const remaining = documents.filter(item => item.id !== doc.id)
      setDocuments(remaining)
      setTranscripts(current => {
        const next = { ...current }
        delete next[doc.id]
        return next
      })
      if (selectedId === doc.id) setSelectedId(remaining[0]?.id ?? '')
      setError('')
    } catch (err) {
      setError(messageOf(err))
    }
  }

  if (authState === 'checking') {
    return (
      <main className="splash" aria-live="polite">
        <div className="brand-mark" aria-hidden="true" />
        <p>{apiStatus === 'waking' ? 'Waking up the server. This can take up to a minute on first load…' : 'Loading PaperPilot…'}</p>
      </main>
    )
  }

  if (authState === 'signed-out') {
    return <AuthScreen onAuthenticated={result => void handleAuthenticated(result)} notice={authNotice} />
  }

  return (
    <div className="app">
      <Sidebar
        documents={documents}
        selectedId={selectedId}
        filter={filter}
        apiStatus={apiStatus}
        user={user!}
        quota={quota}
        onLogout={() => void logout()}
        onFilterChange={setFilter}
        onSelect={id => { setSelectedId(id); setError('') }}
        onRemove={removeDocument}
        onNewConversation={startNewConversation}
        onAddDocument={() => setShowAdd(true)}
      />

      <main className="main">
        <header className="topbar">
          <div className="crumbs">
            <span>Assistant</span>
            <span className="crumb-sep">/</span>
            <b title={selectedDoc?.name}>{selectedDoc?.name ?? 'No document selected'}</b>
          </div>
          <button className="btn btn-ghost" onClick={startNewConversation} disabled={!selectedDoc}>
            New chat
          </button>
        </header>

        <section className="stage">
          {error && (
            <div className="banner" role="alert">
              <span>{error}</span>
              {apiStatus === 'offline' && <button className="banner-action" onClick={() => void boot()}>Try again</button>}
              <button className="icon-button" onClick={() => setError('')} aria-label="Dismiss message"><X size={15} /></button>
            </div>
          )}

          {messages.length === 0 && !pending ? (
            <Welcome documentName={selectedDoc?.name ?? null}
              disabled={!selectedDoc || pendingFor !== null || lockedReason !== null}
              onPick={text => void askQuestion(text)} />
          ) : (
            <MessageList messages={messages} pending={pending} />
          )}
        </section>

        <footer className="dock">
          <Composer
            value={draft}
            documentName={selectedDoc?.name ?? null}
            lockedReason={lockedReason}
            busy={pendingFor !== null}
            onChange={setDraft}
            onSend={() => void askQuestion(draft)}
            onAddDocument={() => setShowAdd(true)}
          />
          <p className="disclaimer">PaperPilot can make mistakes. Check important details against the source.</p>
        </footer>
      </main>

      {showAdd && (
        <AddDocumentModal busy={adding} onClose={() => setShowAdd(false)} onAddUrl={addUrl} onUpload={uploadFile} />
      )}
    </div>
  )
}
