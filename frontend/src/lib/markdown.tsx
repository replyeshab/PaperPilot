import { Fragment, type ReactNode } from 'react'



const BLOCK_START = /^(```|#{1,3}\s|[-*•]\s+|\d+[.)]\s+)/

// "[Passage 2]" / "[Passage 1, 3]" citations from the model become small badges.
const CITATION = /^\[Passages?\s*\d/

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\[Passages?\s*\d+(?:\s*(?:,|and|&)\s*(?:Passages?\s*)?\d+)*\]|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g).map((part, index) => {
    const key = `${keyPrefix}-${index}`
    if (CITATION.test(part) && part.endsWith(']')) {
      return <span key={key} className="cite">{part.slice(1, -1)}</span>
    }
    if (part.length > 4 && part.startsWith('**') && part.endsWith('**')) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }
    if (part.length > 2 && part.startsWith('*') && part.endsWith('*')) {
      return <em key={key}>{part.slice(1, -1)}</em>
    }
    if (part.length > 2 && part.startsWith('`') && part.endsWith('`')) {
      return <code key={key}>{part.slice(1, -1)}</code>
    }
    return <Fragment key={key}>{part}</Fragment>
  })
}

export function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0
  let key = 0
  const nextKey = () => `b${key++}`

  while (index < lines.length) {
    const trimmed = lines[index].trim()

    if (!trimmed) {
      index += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const code: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        code.push(lines[index])
        index += 1
      }
      index += 1
      blocks.push(<pre key={nextKey()}><code>{code.join('\n')}</code></pre>)
      continue
    }

    const heading = /^(#{1,3})\s+(.*)$/.exec(trimmed)
    if (heading) {
      const Tag = heading[1].length === 1 ? 'h3' : 'h4'
      blocks.push(<Tag key={nextKey()}>{renderInline(heading[2], nextKey())}</Tag>)
      index += 1
      continue
    }

    if (/^[-*•]\s+/.test(trimmed) || /^\d+[.)]\s+/.test(trimmed)) {
      const ordered = /^\d+[.)]\s+/.test(trimmed)
      const itemPattern = ordered ? /^\d+[.)]\s+(.*)$/ : /^[-*•]\s+(.*)$/
      const start = ordered ? Number(/^(\d+)/.exec(trimmed)?.[1] ?? 1) : undefined
      const items: ReactNode[] = []
      while (index < lines.length) {
        const match = itemPattern.exec(lines[index].trim())
        if (!match) break
        items.push(<li key={nextKey()}>{renderInline(match[1], nextKey())}</li>)
        index += 1
        // Models often put a blank line between items; keep them in one list so numbering does not restart.
        let lookahead = index
        while (lookahead < lines.length && !lines[lookahead].trim()) lookahead += 1
        if (lookahead > index && lookahead < lines.length && itemPattern.test(lines[lookahead].trim())) index = lookahead
      }
      blocks.push(ordered ? <ol key={nextKey()} start={start}>{items}</ol> : <ul key={nextKey()}>{items}</ul>)
      continue
    }

    const paragraph: string[] = []
    while (index < lines.length) {
      const current = lines[index].trim()
      if (!current || BLOCK_START.test(current)) break
      paragraph.push(current)
      index += 1
    }
    blocks.push(<p key={nextKey()}>{renderInline(paragraph.join(' '), nextKey())}</p>)
  }

  return <div className="markdown">{blocks}</div>
}
