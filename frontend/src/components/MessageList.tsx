import { useEffect, useRef } from 'react'
import { Sparkles } from 'lucide-react'
import type { ChatMessage } from '../services/api'
import { Markdown } from '../lib/markdown'

type Props = { messages: ChatMessage[]; pending: boolean }

export function MessageList({ messages, pending }: Props) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, pending])

  return (
    <div className="thread" role="log" aria-live="polite">
      {messages.map(message => (
        <article key={message.id} className={`message message-${message.role} ${message.failed ? 'is-failed' : ''}`}>
          <div className={`avatar ${message.role === 'assistant' ? 'avatar-ai' : 'avatar-user'}`} aria-hidden="true">
            {message.role === 'assistant' ? <Sparkles size={14} /> : 'You'}
          </div>
          <div className="message-body">
            <div className="message-meta">
              <b>{message.role === 'assistant' ? 'PaperPilot' : 'You'}</b>
              <span>{message.time}</span>
            </div>
            {message.role === 'assistant' ? <Markdown text={message.content} /> : <p className="user-text">{message.content}</p>}
          </div>
        </article>
      ))}
      {pending && (
        <article className="message message-assistant">
          <div className="avatar avatar-ai" aria-hidden="true"><Sparkles size={14} /></div>
          <div className="message-body">
            <div className="message-meta"><b>PaperPilot</b><span>thinking</span></div>
            <div className="thinking" aria-label="Searching the document">
              <span /><span /><span />
              <em>Searching the document and composing an answer…</em>
            </div>
          </div>
        </article>
      )}
      <div ref={endRef} />
    </div>
  )
}
