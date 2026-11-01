import { useRef, type KeyboardEvent } from 'react'
import { FileUp, LoaderCircle, Send } from 'lucide-react'

type Props = {
  value: string
  documentName: string | null
  lockedReason: string | null
  busy: boolean
  onChange: (value: string) => void
  onSend: () => void
  onAddDocument: () => void
}

export function Composer({ value, documentName, lockedReason, busy, onChange, onSend, onAddDocument }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const canSend = value.trim().length > 0 && !busy && documentName !== null && !lockedReason

  function handleKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (canSend) onSend()
    }
  }

  return (
    <div className="composer">
      <div className="composer-box">
        <textarea
          ref={ref}
          value={value}
          rows={1}
          maxLength={4000}
          disabled={documentName === null || lockedReason !== null}
          onChange={event => onChange(event.target.value)}
          onKeyDown={handleKey}
          placeholder={lockedReason ?? (documentName ? `Ask about ${documentName}…` : 'Add a PDF to start asking questions')}
          aria-label="Your question"
        />
        <button className="btn btn-send" onClick={onSend} disabled={!canSend} aria-label="Send question">
          {busy ? <LoaderCircle size={16} className="spin" /> : <Send size={15} />}
        </button>
      </div>
      <div className="composer-meta">
        <button className="link-button" onClick={onAddDocument}><FileUp size={14} /> Add a PDF</button>
        <span><kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line</span>
      </div>
    </div>
  )
}
