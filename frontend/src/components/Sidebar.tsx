import { FileText, LoaderCircle, LogOut, MessageSquare, Plus, Search, Sparkles, Trash2 } from 'lucide-react'
import type { DocumentItem, Quota, UserInfo } from '../services/api'

export type ApiStatus = 'checking' | 'waking' | 'online' | 'offline'

type Props = {
  documents: DocumentItem[]
  selectedId: string
  filter: string
  apiStatus: ApiStatus
  user: UserInfo
  quota: Quota | null
  onLogout: () => void
  onFilterChange: (value: string) => void
  onSelect: (id: string) => void
  onRemove: (doc: DocumentItem) => void
  onNewConversation: () => void
  onAddDocument: () => void
}

export function Sidebar({
  documents, selectedId, filter, apiStatus, user, quota, onLogout, onFilterChange, onSelect, onRemove, onNewConversation, onAddDocument,
}: Props) {
  const visible = documents.filter(doc => doc.name.toLowerCase().includes(filter.trim().toLowerCase()))

  return (
    <aside className="sidebar" aria-label="Workspace">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true"><Sparkles size={18} strokeWidth={2.3} /></div>
        <div className="brand-text">
          <strong>PaperPilot</strong>
          <span>Your AI reading space</span>
        </div>
      </div>

      <button className="btn btn-primary new-chat" onClick={onNewConversation} title="New conversation (Ctrl/⌘ K)">
        <Plus size={16} /> <span>New conversation</span> <kbd>⌘K</kbd>
      </button>

      <nav className="nav" aria-label="Sections">
        <span className="nav-label">Workspace</span>
        <button className="nav-item active" aria-current="page"><MessageSquare size={16} /><span>Assistant</span></button>
      </nav>

      <div className="library-head">
        <span className="nav-label">Library</span>
        <span className="count">{documents.length}</span>
        <button className="icon-button" aria-label="Add a document" onClick={onAddDocument}><Plus size={15} /></button>
      </div>

      <label className="library-search">
        <Search size={14} aria-hidden="true" />
        <input
          value={filter}
          onChange={event => onFilterChange(event.target.value)}
          placeholder="Find a document"
          aria-label="Find a document"
        />
      </label>

      <ul className="document-list">
        {visible.map(doc => (
          <li key={doc.id} className={`document-row ${doc.id === selectedId ? 'is-selected' : ''}`}>
            <button className="document-select" onClick={() => onSelect(doc.id)} aria-pressed={doc.id === selectedId}>
              <span className="pdf-icon"><FileText size={14} /></span>
              <span className="document-copy">
                <span className="doc-title" title={doc.name}>{doc.name}</span>
                {doc.index_status === 'indexing' && <small className="doc-status"><LoaderCircle size={11} className="spin" /> Preparing PDF…</small>}
                {doc.index_status === 'error' && <small className="doc-status doc-status-error">Could not prepare PDF</small>}
              </span>
            </button>
            {doc.id !== 'default-document' && (
              <button className="icon-button row-remove" aria-label={`Remove ${doc.name}`} onClick={() => onRemove(doc)}>
                <Trash2 size={13} />
              </button>
            )}
          </li>
        ))}
        {visible.length === 0 && <li className="empty-small">{documents.length ? 'No matching documents.' : 'No documents yet.'}</li>}
      </ul>

      <div className="sidebar-footer">
        {quota && (
          <div className="quota" title="One budget shared by everyone using this instance">
            <div className="quota-row"><span>Shared requests</span><b>{quota.used} / {quota.limit}</b></div>
            <div className="quota-bar" aria-hidden="true"><span style={{ width: `${Math.min(100, (quota.used / quota.limit) * 100)}%` }} /></div>
          </div>
        )}
        <div className={`status status-${apiStatus}`}>
          <span className="status-dot" aria-hidden="true" />
          <span>{statusLabel(apiStatus)}</span>
        </div>
        <div className="account">
          <span className="account-email" title={user.email}>{user.email}</span>
          <button className="icon-button" onClick={onLogout} aria-label="Sign out" title="Sign out"><LogOut size={15} /></button>
        </div>
      </div>
    </aside>
  )
}

function statusLabel(status: ApiStatus): string {
  switch (status) {
    case 'online': return 'Connected'
    case 'waking': return 'Waking up the server…'
    case 'offline': return 'Server unavailable'
    default: return 'Connecting…'
  }
}
