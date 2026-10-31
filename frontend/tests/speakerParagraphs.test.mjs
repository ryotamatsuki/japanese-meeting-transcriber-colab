import {test} from 'node:test'
import assert from 'node:assert/strict'
import {groupConsecutiveSpeakerRows,joinTranscriptText} from '../src/speakerParagraphs.ts'
import {formatTranscriptForCopy} from '../src/transcriptCopy.ts'

const rows=[
  {start:0,end:2,speaker:'話者1',text:'本日の会議を'},
  {start:2.1,end:4,speaker:'話者1',text:'始めます。'},
  {start:4,end:6,speaker:'話者2',text:'承知しました。'},
  {start:6.1,end:9,speaker:'話者1',text:'次の議題です。'},
  {start:9,end:10,speaker:'話者1',text:'追加事項があります。'}
]
test('consecutive same-speaker Whisper groups only; timestamp span preserved',()=>{
  const before=structuredClone(rows)
  assert.deepEqual(groupConsecutiveSpeakerRows(rows),[
    {start:0,end:4,speaker:'話者1',text:'本日の会議を始めます。',firstIndex:0,lastIndex:1,rowCount:2},
    {start:4,end:6,speaker:'話者2',text:'承知しました。',firstIndex:2,lastIndex:2,rowCount:1},
    {start:6.1,end:10,speaker:'話者1',text:'次の議題です。追加事項があります。',firstIndex:3,lastIndex:4,rowCount:2},
  ])
  assert.deepEqual(rows,before)
})
test('speaker changes, uncertain labels, blank manual rows and reordered timestamps are boundaries',()=>{
  const source=[
    {start:1,end:2,speaker:'話者不明',text:'あ'},
    {start:2,end:3,speaker:'話者不明',text:'い'},
    {start:3,end:4,speaker:'話者1',text:'う'},
    {start:4,end:5,speaker:'話者1',text:' '},
    {start:5,end:6,speaker:'話者1',text:'え'},
    {start:1,end:2,speaker:'話者1',text:'お'},
    {start:2,end:3,speaker:'話者2',text:'か'}
  ]
  const grouped=groupConsecutiveSpeakerRows(source)
  assert.equal(grouped.length,6)
  assert.equal(grouped[0].text,'あ')
  assert.equal(grouped[4].text,'お')
})
test('Japanese boundaries concatenate, ASCII words separate and user linebreaks remain',()=>{
  assert.equal(joinTranscriptText('議題は','予算です。'),'議題は予算です。')
  assert.equal(joinTranscriptText('Hello','world'),'Hello world')
  assert.equal(joinTranscriptText('1.','次'), '1.次')
  assert.equal(joinTranscriptText('行1\n','行2'),'行1行2')
})
test('copy default creates readable same-speaker paragraph; raw copy preserves every original line',()=>{
  assert.equal(formatTranscriptForCopy(rows),
    '話者1：本日の会議を始めます。\n\n話者2：承知しました。\n\n話者1：次の議題です。追加事項があります。')
  assert.equal(formatTranscriptForCopy(rows,'speaker-raw'),
    '話者1：本日の会議を\n\n話者1：始めます。\n\n話者2：承知しました。\n\n話者1：次の議題です。\n\n話者1：追加事項があります。')
  assert.equal(formatTranscriptForCopy(rows,'timed'),
    '[00:00:00] 話者1：本日の会議を始めます。\n\n[00:00:04] 話者2：承知しました。\n\n[00:00:06] 話者1：次の議題です。追加事項があります。')
  assert.equal(formatTranscriptForCopy(rows,'plain'),
    '本日の会議を始めます。\n\n承知しました。\n\n次の議題です。追加事項があります。')
})
test('empty input and data that was manually split preserve source rows',()=>{
  assert.deepEqual(groupConsecutiveSpeakerRows([]),[])
  const source=structuredClone(rows)
  source[1].speaker='話者不明'
  assert.equal(groupConsecutiveSpeakerRows(source).length,4)
  assert.equal(source[1].speaker,'話者不明')
})
