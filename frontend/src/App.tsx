import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, FileText, X } from 'lucide-react'
import { Analytics } from '@vercel/analytics/react'
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
import { formatTime, newId, tokenStore } from './lib/session'

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

  // Refs let async callbacks read the latest values without re-running their effects.
  const freshRef = useRef(freshConversation)
  const pendingRef = useRef(pendingFor)
  freshRef.current = freshConversation
  pendingRef.current = pendingFor

  const selectedDoc = useMemo(() => documents.find(doc => doc.id === selectedId) ?? null, [documents, selectedId])
  const messages = transcripts[selectedId] ?? []
  const pending = pendingFor !== null && pendingFor === selectedId
  const lockedReason = !selectedDoc && documents.length > 0
    ? 'Choose a PDF above to start asking questions.'
    : selectedDoc?.index_status === 'indexing'
    ? 'Preparing this PDF… You can ask questions as soon as it’s ready.'
    : selectedDoc?.index_status === 'error'
      ? (selectedDoc.index_error || 'This PDF could not be prepared. Remove it and upload it again.')
      : quota && quota.remaining <= 0
        ? 'The shared request limit has been reached. Your past conversations are still available.'
        : null

  const hasIndexingDocuments = documents.some(doc => doc.index_status === 'indexing')

  const loadLibrary = useCallback(async () => {
    const [docs, budget] = await Promise.all([api.documents(), api.quota()])
    setDocuments(docs)
    setQuota(budget)
    setSelectedId(current => {
      if (docs.some(doc => doc.id === current)) return current
      return ''
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
    setError('')
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
      else {
        setApiStatus('offline')
        setError(messageOf(err))
      }
    }
  }, [loadLibrary, signOut])

  useEffect(() => { void boot() }, [boot])

  useEffect(() => {
    if (!hasIndexingDocuments) return
    let cancelled = false
    let refreshing = false
    const refreshStatuses = async () => {
      if (refreshing) return
      refreshing = true
      try {
        const latest = await api.documents()
        if (cancelled) return
        setDocuments(latest)
        const selected = latest.find(doc => doc.id === selectedId)
        if (selected?.index_status === 'error') {
          setError(selected.index_error || 'PaperPilot could not prepare this PDF. Remove it and upload it again.')
        }
      } catch {
        // Keep showing the indexing state and retry on the next poll.
      } finally {
        refreshing = false
      }
    }
    const timer = window.setInterval(() => { void refreshStatuses() }, 1500)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [hasIndexingDocuments, selectedId])

  // Load the saved conversation whenever a document is opened.
  useEffect(() => {
    if (authState !== 'signed-in' || !selectedId) return
    // The user started a fresh chat for this PDF: keep the empty transcript.
    if (freshRef.current[selectedId]) return
    let cancelled = false
    api.conversation(selectedId)
      .then(result => {
        if (cancelled || pendingRef.current === selectedId) return
        setTranscripts(current => ({ ...current, [selectedId]: result.messages.map(toChatMessage) }))
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
      setDraft(current => current || question)
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
      const library = await api.documents().catch(() => null)
      const uploadedDoc = library?.find(item => item.id === doc.id) ?? doc
      setDocuments(current => {
        const existing = (library ?? current).filter(item => item.id !== uploadedDoc.id)
        const firstOwned = existing.findIndex(item => !item.shared)
        const insertAt = firstOwned < 0 ? existing.length : firstOwned
        return [...existing.slice(0, insertAt), uploadedDoc, ...existing.slice(insertAt)]
      })
      setTranscripts(current => ({ ...current, [uploadedDoc.id]: [] }))
      setFreshConversation(current => ({ ...current, [uploadedDoc.id]: false }))
      setSelectedId(uploadedDoc.id)
      setShowAdd(false)
      setError('')
      void api.quota().then(setQuota).catch(() => undefined)
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
      if (selectedId === doc.id) setSelectedId('')
      setError('')
    } catch (err) {
      setError(messageOf(err))
    }
  }

  if (authState === 'checking') {
    const offline = apiStatus === 'offline'
    return (
      <main className="splash" aria-live="polite">
        <div className={`brand-mark ${offline ? 'is-still' : ''}`} aria-hidden="true" />
        <p>
          {offline
            ? (error || 'Could not reach the PaperPilot server.')
            : apiStatus === 'waking'
              ? 'Waking up the server. This can take up to a minute on first load…'
              : 'Loading PaperPilot…'}
        </p>
        {offline && <button className="btn btn-primary" onClick={() => void boot()}>Try again</button>}
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
        onSelect={id => { if (pendingFor !== null) return; setSelectedId(id); setError('') }}
        onRemove={removeDocument}
        onNewConversation={startNewConversation}
        onAddDocument={() => setShowAdd(true)}
      />

      <main className="main">
        <header className="topbar">
          <div className="document-scope">
            <div className="document-scope-copy">
              <label htmlFor="active-pdf">Answering from</label>
              <small>Choose the PDF for this chat</small>
            </div>
            <div className="document-scope-field">
              <FileText size={15} aria-hidden="true" />
              <select
                id="active-pdf"
                value={selectedId}
                disabled={documents.length === 0 || pendingFor !== null}
                aria-label="Choose the PDF PaperPilot should answer from"
                onChange={event => { setSelectedId(event.target.value); setError('') }}
              >
                <option value="" disabled>{documents.length ? 'Select a PDF…' : 'No PDFs in your library'}</option>
                {documents.map(doc => (
                  <option key={doc.id} value={doc.id}>
                    {doc.name}{doc.index_status === 'indexing' ? ' · preparing' : doc.index_status === 'error' ? ' · needs attention' : ''}
                  </option>
                ))}
              </select>
              <ChevronDown size={15} aria-hidden="true" />
            </div>
          </div>
          <button className="btn btn-ghost" onClick={startNewConversation} disabled={!selectedDoc}>
            New chat
          </button>
        </header>

        <section className="stage">
          {error && (
            <div className="banner" role="alert">
              <span>{error}</span>
              {apiStatus === 'offline' && <button className="banner-action" onClick={() => void loadLibrary().catch(err => setError(messageOf(err)))}>Try again</button>}
              <button className="icon-button" onClick={() => setError('')} aria-label="Dismiss message"><X size={15} /></button>
            </div>
          )}

          {messages.length === 0 && !pending ? (
            <Welcome documentName={selectedDoc?.name ?? null}
              hasDocuments={documents.length > 0}
              disabled={!selectedDoc || pendingFor !== null || lockedReason !== null}
              onAddDocument={() => setShowAdd(true)}
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
      <Analytics />
    </div>
  )
}
