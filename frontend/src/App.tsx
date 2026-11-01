import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Activity, ArrowDown, ArrowUp, BookOpen, Check, ChevronDown, CircleHelp, FileText, FileUp, Globe, LoaderCircle, MessageSquare, MoreHorizontal, Plus, Search, Send, Settings2, ShieldCheck, Sparkles, Trash2, X, Zap } from 'lucide-react'
import { api, type ChatMessage, type DocumentItem } from './services/api'

const suggestions = [
  { icon: BookOpen, title: 'Summarize this document', sub: 'Get the key ideas in seconds' },
  { icon: Search, title: 'Find the most important points', sub: 'Surface details worth remembering' },
  { icon: Sparkles, title: 'Explain a complex idea simply', sub: 'Turn dense text into clear language' },
  { icon: MessageSquare, title: 'Create study questions', sub: 'Check your understanding' },
]
const stamp = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

export default function App() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [selected, setSelected] = useState<string>('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [apiOnline, setApiOnline] = useState(false)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [sourceUrl, setSourceUrl] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [adding, setAdding] = useState(false)
  const [filter, setFilter] = useState('')
  const [newConversation, setNewConversation] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  async function refresh() {
    try { const [docs] = await Promise.all([api.documents(), api.health()]); setDocuments(docs); setSelected(current => current || docs[0]?.id || ''); setApiOnline(true); setError('') }
    catch (e) { setApiOnline(false); setError(e instanceof Error ? e.message : 'Could not load the application.') }
  }
  useEffect(() => { void refresh() }, [])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  async function addDocument(e: FormEvent) {
    e.preventDefault(); setAdding(true); setError('')
    try { const doc = await api.addDocument(sourceUrl.trim()); setDocuments(items => items.some(x => x.id === doc.id) ? items : [...items, doc]); setSelected(doc.id); setSourceUrl(''); setShowAdd(false); setMessages([]); setNewConversation(true) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not add this PDF URL.') }
    finally { setAdding(false) }
  }
  async function uploadPdf(e: FormEvent) {
    e.preventDefault(); if (!uploadFile) return
    setAdding(true); setError('')
    try { const doc = await api.uploadDocument(uploadFile); setDocuments(items => [...items, doc]); setSelected(doc.id); setUploadFile(null); setShowAdd(false); setMessages([]); setNewConversation(true) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not upload this PDF.') }
    finally { setAdding(false) }
  }
  async function removeDocument(doc: DocumentItem) {
    if (!window.confirm(`Remove “${doc.name}” from your library?`)) return
    try { await api.removeDocument(doc.id); setDocuments(items => items.filter(x => x.id !== doc.id)); if (selected === doc.id) setSelected(''); setError('') }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not remove the document.') }
  }
  async function sendMessage(text = question) {
    const clean = text.trim(); if (!clean || loading) return
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: clean, time: stamp() }
    setMessages(items => [...items, userMessage]); setQuestion(''); setLoading(true); setError('')
    try { const result = await api.chat(clean, newConversation, selected || undefined); setMessages(items => [...items, { id: crypto.randomUUID(), role: 'assistant', content: result.answer, time: stamp() }]); setNewConversation(false) }
    catch (e) { setError(e instanceof Error ? e.message : 'The assistant could not answer.'); }
    finally { setLoading(false) }
  }
  function onComposerKey(e: KeyboardEvent<HTMLTextAreaElement>) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendMessage() } }
  const selectedDoc = documents.find(doc => doc.id === selected)
  const visibleDocs = documents.filter(doc => doc.name.toLowerCase().includes(filter.toLowerCase()))

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Sparkles size={19} strokeWidth={2.3}/></div><div><strong>paperpilot</strong><span>YOUR AI READING SPACE</span></div></div>
      <button className="workspace-select"><div className="workspace-icon">P</div><span><b>Personal workspace</b><small>Free workspace</small></span><ChevronDown size={15}/></button>
      <button className="primary-button new-chat" onClick={() => { setMessages([]); setNewConversation(true); setError('') }}><Plus size={17}/> New conversation <span>⌘ K</span></button>
      <div className="nav-label">WORKSPACE</div>
      <button className="nav-item active"><MessageSquare size={17}/> AI assistant</button>
      <button className="nav-item" onClick={() => setShowAdd(true)}><FileText size={17}/> My documents <span className="count">{documents.length}</span></button>
      <div className="library-heading"><span className="nav-label">YOUR LIBRARY</span><button aria-label="Add document" onClick={() => setShowAdd(true)}><Plus size={16}/></button></div>
      <div className="library-search"><Search size={14}/><input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Find a document" /></div>
      <div className="document-list">{visibleDocs.map(doc => <div key={doc.id} className={`document-row ${selected === doc.id ? 'selected' : ''}`}><button className="document-select" onClick={() => { setSelected(doc.id); setMessages([]); setNewConversation(true) }}><span className="pdf-icon"><FileText size={15}/></span><span className="doc-title">{doc.name}</span></button>{doc.id !== 'default-document' && <button className="icon-button remove-doc" aria-label={`Remove ${doc.name}`} onClick={() => void removeDocument(doc)}><Trash2 size={14}/></button>}</div>)}{visibleDocs.length === 0 && <p className="empty-small">No documents found.</p>}</div>
      <div className="sidebar-bottom"><div className="upgrade-card"><div className="upgrade-icon"><Zap size={16}/></div><b>Make space for big ideas.</b><p>Your documents, one thoughtful conversation at a time.</p><button onClick={() => setShowAdd(true)}>Add a document <ArrowDown size={13}/></button></div><button className="nav-item muted"><Settings2 size={17}/> Settings <span className="soon">SOON</span></button><div className="profile"><div className="avatar">E</div><div><b>Explorer</b><small>Personal account</small></div><MoreHorizontal size={18}/></div></div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><b>AI assistant</b></div><div className="topbar-right"><div className={`connection ${apiOnline ? 'online' : 'offline'}`}><span/>{apiOnline ? 'System operational' : 'Connecting to API'}</div><button className="help-button" aria-label="Help"><CircleHelp size={18}/></button><div className="top-avatar">E</div></div></header>
      <section className={`conversation-area ${messages.length ? 'has-messages' : ''}`}>
        {messages.length === 0 ? <div className="welcome-content"><div className="welcome-eyebrow"><span className="eyebrow-line"/><Sparkles size={13}/> YOUR PERSONAL RESEARCH PARTNER <span className="eyebrow-line"/></div><div className="hero-orb"><div className="orb-ring ring-one"/><div className="orb-ring ring-two"/><div className="orb-core"><Sparkles size={29}/></div><span className="orb-star star-a">✳</span><span className="orb-star star-b">✦</span></div><h1>Your PDF,<br/><em>understood.</em></h1><p className="hero-subtitle">Big ideas hide in long documents. Let's find yours.<br/>Ask a question, explore a concept, or start with a suggestion.</p><div className="suggestion-grid">{suggestions.map(({ icon: Icon, title, sub }) => <button className="suggestion-card" key={title} onClick={() => void sendMessage(title)}><span className="suggestion-icon"><Icon size={17}/></span><span className="suggestion-copy"><b>{title}</b><small>{sub}</small></span><ArrowUp size={15} className="suggestion-arrow"/></button>)}</div><div className="privacy-note"><ShieldCheck size={14}/> Your workspace is private. Your documents stay yours.</div></div> : <div className="message-thread">{messages.map(message => <article className={`message ${message.role}`} key={message.id}>{message.role === 'assistant' ? <div className="message-avatar"><Sparkles size={15}/></div> : <div className="user-avatar">E</div>}<div className="message-body"><div className="message-meta"><b>{message.role === 'assistant' ? 'PaperPilot' : 'You'}</b><span>{message.time}</span></div><div className="message-text">{message.content}</div></div></article>)}{loading && <article className="message assistant"><div className="message-avatar"><Sparkles size={15}/></div><div className="message-body"><div className="message-meta"><b>PaperPilot</b><span>thinking</span></div><div className="thinking"><span/><span/><span/> Searching your document and composing an answer…</div></div></article>}<div ref={bottomRef}/></div>}
        {error && <div className="error-banner" role="alert"><CircleHelp size={16}/><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={15}/></button></div>}
      </section>
      <footer className="composer-area"><div className="composer-wrap"><div className="composer-topline"><span><span className="composer-dot"/> {selectedDoc ? selectedDoc.name : 'Choose a document from your library'}</span><span className="model-badge"><span/> GROQ AI</span></div><div className="composer"><textarea value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={onComposerKey} placeholder="Ask anything about your document…" rows={2} aria-label="Ask your PDF assistant"/><div className="composer-actions"><div className="composer-hints"><button onClick={() => setShowAdd(true)} title="Add a document"><FileUp size={16}/><span>Add PDF URL</span></button><span className="hint-divider"/><span className="keyboard-hint"><kbd>↵</kbd> to send <kbd>⇧ ↵</kbd> new line</span></div><button className="send-button" disabled={!question.trim() || loading} onClick={() => void sendMessage()} aria-label="Send message">{loading ? <LoaderCircle size={17} className="spin"/> : <Send size={16}/>}</button></div></div><div className="composer-disclaimer">PaperPilot can make mistakes. Verify important details against the source document.</div></div></footer>
      <div className="statusbar"><span><Activity size={13}/> Built for curious minds</span><span><Globe size={13}/> Secure by design <span className="status-separator">·</span> v1.0.0</span></div>
    </main>
    {showAdd && <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setShowAdd(false) }}><section className="add-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div className="modal-top"><div className="modal-icon"><FileUp size={20}/></div><button className="icon-button" onClick={() => setShowAdd(false)} aria-label="Close"><X size={18}/></button></div><h2 id="modal-title">Bring a document into focus.</h2><p>Upload a PDF or add a public URL. PaperPilot uses your configured Phi + PostgreSQL/pgvector knowledge base when you ask questions.</p><form onSubmit={addDocument}><label htmlFor="pdf-url">Add from a public URL</label><input id="pdf-url" type="url" placeholder="https://example.com/research-paper.pdf" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} pattern="https?://.+\.pdf(\?.*)?" title="Enter a direct HTTP or HTTPS URL ending in .pdf"/><div className="modal-actions url-actions"><button type="button" className="secondary-button" onClick={() => setShowAdd(false)}>Cancel</button><button className="primary-button" disabled={adding || !sourceUrl.trim()} type="submit">{adding ? <><LoaderCircle size={15} className="spin"/> Adding…</> : <><Globe size={15}/> Add URL</>}</button></div></form><div className="modal-divider"><span>OR UPLOAD A FILE</span></div><form onSubmit={uploadPdf}><label className="file-drop" htmlFor="pdf-file"><FileUp size={20}/><b>{uploadFile ? uploadFile.name : 'Choose a PDF from your computer'}</b><small>PDF only · up to 20 MB</small><input id="pdf-file" type="file" accept="application/pdf,.pdf" onChange={e => setUploadFile(e.target.files?.[0] || null)} /></label><div className="modal-tip"><ShieldCheck size={15}/> Only add PDFs you have permission to use.</div><div className="modal-actions"><button className="primary-button" disabled={adding || !uploadFile} type="submit">{adding ? <><LoaderCircle size={15} className="spin"/> Uploading…</> : <><Check size={15}/> Upload PDF</>}</button></div></form></section></div>}
  </div>
}
