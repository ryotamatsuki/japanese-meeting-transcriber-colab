import { test } from 'node:test'
import assert from 'node:assert/strict'
import { formatTranscriptForCopy } from '../src/transcriptCopy.ts'

const rows = [
  { start: 12.8, speaker: '話者1', text: 'おはようございます。' },
  { start: 73.2, speaker: '話者2', text: '本日はよろしくお願いします。\n追加事項です。' },
  { start: 78.3, speaker: '話者2', text: '   ' },
]

test('default is speaker-labelled text without timestamps', () => {
  assert.equal(formatTranscriptForCopy(rows), '話者1：おはようございます。\n\n話者2：本日はよろしくお願いします。\n追加事項です。')
})
test('plain mode copies utterances only, keeping user line breaks', () => {
  assert.equal(formatTranscriptForCopy(rows, 'plain'), 'おはようございます。\n\n本日はよろしくお願いします。\n追加事項です。')
})
test('timed mode uses entire hour-minute-second time', () => {
  assert.equal(formatTranscriptForCopy(rows, 'timed'), '[00:00:12] 話者1：おはようございます。\n\n[00:01:13] 話者2：本日はよろしくお願いします。\n追加事項です。')
  assert.equal(formatTranscriptForCopy([{ start: 3611.5, speaker: '司会者', text: '進行します' }], 'timed'), '[01:00:11] 司会者：進行します')
})
test('empty/all-blank rows produce no copied text', () => {
  assert.equal(formatTranscriptForCopy([]), '')
  assert.equal(formatTranscriptForCopy([{ start: 0, speaker: '話者1', text: '\n\t' }]), '')
})
test('does not mutate transcript data, ignores page selection, reflects edits', () => {
  const changed = structuredClone(rows)
  changed[0].text = '修正した発言です。'
  const before = structuredClone(changed)
  assert.ok(formatTranscriptForCopy(changed).startsWith('話者1：修正した発言です。'))
  assert.deepEqual(changed, before)
})
