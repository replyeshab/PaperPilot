import { useEffect, useState, type FormEvent } from 'react'
import { Check, FileUp, Globe, LoaderCircle, ShieldCheck, X } from 'lucide-react'

type Props = {
  busy: boolean
  onClose: () => void
  onAddUrl: (url: string) => Promise<void>
  onUpload: (file: File) => Promise<void>
}

const MAX_MB = 20

export function AddDocumentModal({ busy, onClose, onAddUrl, onUpload }: Props) {
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => { if (event.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  async function submitUrl(event: FormEvent) {
    event.preventDefault()
    setError('')
    try { await onAddUrl(url.trim()) } catch (err) { setError(messageOf(err)) }
  }

  async function submitFile(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    setError('')
    if (file.size > MAX_MB * 1024 * 1024) { setError(`That file is larger than ${MAX_MB} MB.`); return }
    try { await onUpload(file) } catch (err) { setError(messageOf(err)) }
  }

  return (
    <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="add-title">
        <header className="modal-head">
          <div className="modal-icon"><FileUp size={18} /></div>
          <button className="icon-button" onClick={onClose} aria-label="Close" disabled={busy}><X size={17} /></button>
        </header>
        <h2 id="add-title">Bring a document into focus</h2>
        <p className="modal-lede">Add a public PDF link or upload a file. Uploaded PDFs open automatically. Large documents can take a minute to index.</p>

        {error && <div className="inline-error" role="alert">{error}</div>}

        <form onSubmit={submitUrl} className="modal-form">
          <label htmlFor="pdf-url">Public PDF link</label>
          <div className="modal-row">
            <input
              id="pdf-url"
              type="url"
              placeholder="https://example.com/research-paper.pdf"
              value={url}
              onChange={event => setUrl(event.target.value)}
              disabled={busy}
              autoFocus
            />
            <button className="btn btn-primary" type="submit" disabled={busy || !url.trim()}>
              {busy ? <LoaderCircle size={15} className="spin" /> : <Globe size={15} />} Add
            </button>
          </div>
        </form>

        <div className="divider"><span>or</span></div>

        <form onSubmit={submitFile} className="modal-form">
          <label className={`file-drop ${file ? 'has-file' : ''}`} htmlFor="pdf-file">
            <FileUp size={20} />
            <b>{file ? file.name : 'Choose a PDF from your computer'}</b>
            <small>PDF only · up to {MAX_MB} MB</small>
            <input id="pdf-file" type="file" accept="application/pdf,.pdf" disabled={busy}
              onChange={event => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <div className="modal-foot">
            <span className="modal-tip"><ShieldCheck size={14} /> Only add documents you have permission to use.</span>
            <button className="btn btn-primary" type="submit" disabled={busy || !file}>
              {busy ? <LoaderCircle size={15} className="spin" /> : <Check size={15} />} Upload &amp; open
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}
