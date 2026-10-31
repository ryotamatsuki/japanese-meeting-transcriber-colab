/** Presentation-only consecutive-speaker paragraphs.
 * Never mutate edit rows, word timing, speaker boundaries, SRT or JSON data.
 * No LLM: the order and speaker IDs already stored in the edited transcript
 * determine paragraph boundaries. Unknown speakers are intentionally not merged.
 */
export type SpeakerRow = Readonly<{
  start: number
  end: number
  speaker: string
  text: string
}>

export type SpeakerParagraph = {
  start: number
  end: number
  speaker: string
  text: string
  firstIndex: number
  lastIndex: number
  rowCount: number
}

function reliableSpeaker(label: string): boolean {
  const speaker = label.trim()
  return !!speaker && !/^(?:話者不明|話者未設定|不明|unknown|unassigned)$/i.test(speaker)
}

/** Join Japanese text directly; separate adjacent ASCII words with a space.
 * Avoid an LLM-generated punctuation guess. Original rows are untouched. */
export function joinTranscriptText(left: string, right: string): string {
  const a = left.trimEnd()
  const b = right.trimStart()
  if (!a) return b
  if (!b) return a
  const between = /[A-Za-z0-9]$/.test(a) && /^[A-Za-z0-9]/.test(b) ? ' ' : ''
  return a + between + b
}

export function groupConsecutiveSpeakerRows(rows: readonly SpeakerRow[]): SpeakerParagraph[] {
  const grouped: SpeakerParagraph[] = []
  let lastSource: number | null = null
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index]
    const text = row.text.trim()
    if (!text) {
      lastSource = null // A blank/manual segment is an intentional boundary.
      continue
    }
    const last = grouped[grouped.length - 1]
    // Never reorder overlapping speech. A speaker switch remains a boundary.
    const contiguous = last && lastSource === index - 1
      && last.speaker === row.speaker && reliableSpeaker(row.speaker)
      && Number.isFinite(row.start) && Number.isFinite(row.end)
      && row.start >= rows[index - 1].start && row.end >= row.start
    if (contiguous) {
      last.text = joinTranscriptText(last.text, text)
      last.end = Math.max(last.end, row.end)
      last.lastIndex = index
      last.rowCount++
    } else {
      grouped.push({
        start: row.start, end: row.end, speaker: row.speaker,
        text, firstIndex: index, lastIndex: index, rowCount: 1,
      })
    }
    lastSource = index
  }
  return grouped
}
