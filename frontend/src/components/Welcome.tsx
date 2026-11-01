import { ArrowUpRight, BookOpen, MessageSquare, Search, ShieldCheck, Sparkles, type LucideIcon } from 'lucide-react'

const suggestions: { icon: LucideIcon; title: string; detail: string }[] = [
  { icon: BookOpen, title: 'Summarize this document', detail: 'The key ideas in a few paragraphs' },
  { icon: Search, title: 'Find the most important points', detail: 'Surface details worth remembering' },
  { icon: Sparkles, title: 'Explain a complex idea simply', detail: 'Turn dense text into plain language' },
  { icon: MessageSquare, title: 'Create study questions', detail: 'Check your understanding' },
]

type Props = {
  documentName: string | null
  disabled: boolean
  onPick: (prompt: string) => void
}

export function Welcome({ documentName, disabled, onPick }: Props) {
  return (
    <div className="welcome">
      <p className="eyebrow">Your personal research partner</p>
      <h1>Your PDF, <em>understood.</em></h1>
      <p className="lead">
        {documentName
          ? <>Ask anything about <strong>{documentName}</strong>, or start with a suggestion.</>
          : 'Add a PDF from a link or upload one to begin.'}
      </p>
      <div className="suggestions">
        {suggestions.map(({ icon: Icon, title, detail }) => (
          <button key={title} className="suggestion" disabled={disabled} onClick={() => onPick(title)}>
            <span className="suggestion-icon"><Icon size={16} /></span>
            <span className="suggestion-copy">
              <b>{title}</b>
              <small>{detail}</small>
            </span>
            <ArrowUpRight size={15} className="suggestion-arrow" aria-hidden="true" />
          </button>
        ))}
      </div>
      <p className="privacy"><ShieldCheck size={14} /> Your questions are answered only from the document you select.</p>
    </div>
  )
}
