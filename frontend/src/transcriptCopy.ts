/** Format the complete transcript for pasting into notes or messages.
 * Never use a paginated/filtered subset. This is a pure client-side operation. */
export type TranscriptCopyMode = 'speaker' | 'plain' | 'timed'
export type TranscriptCopyRow = {
  start: number
  speaker: string
  text: string
}

function clock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  return [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60]
    .map(value => String(value).padStart(2, '0')).join(':')
}

export function formatTranscriptForCopy(rows: readonly TranscriptCopyRow[], mode: TranscriptCopyMode = 'speaker'): string {
  return rows.filter(row => row.text.trim().length > 0).map(row => {
    if (mode === 'plain') return row.text
    const speech = `${row.speaker}：${row.text}`
    return mode === 'timed' ? `[${clock(row.start)}] ${speech}` : speech
  }).join('\n\n')
}
