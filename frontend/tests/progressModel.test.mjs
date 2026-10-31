import {test} from 'node:test'
import assert from 'node:assert/strict'
import {progressInfo,durationLabel,processingSteps} from '../src/progressModel.ts'
const baseline={filename:'会議.wav',status:'running',duration:3600,created:1000,started_at:1100}
test('No misleading overall percent during queue or diarization',()=>{
  const waiting=progressInfo({...baseline,status:'queued'},1200)
  assert.equal(waiting.fraction,null)
  assert.match(waiting.title,/準備/)
  const diar=progressInfo({...baseline,progress:{phase:'diarization',updated_at:1300}},1310)
  assert.equal(diar.fraction,null)
  assert.equal(diar.stageRank,2)
})
test('Measured audio only, ASR-only ETA after enough observed throughput',()=>{
  const raw={...baseline,progress:{phase:'asr',audio_done:1800,audio_total:3600,phase_started_at:1100,updated_at:1300}}
  const p=progressInfo(raw,1310)
  assert.equal(p.fraction,0.5)
  assert.equal(p.asrRemaining,210)
  assert.equal(p.stageRank,1)
  assert.equal(progressInfo(raw,1390).asrRemaining,null)
  assert.equal(progressInfo({...raw,progress:{...raw.progress,audio_done:0}},1310).asrRemaining,null)
  assert.equal(progressInfo({...raw,progress:{...raw.progress,audio_total:0}},1310).fraction,null)
})
test('Stage list, elapsed and timestamps',()=>{
  assert.equal(processingSteps.length,4)
  assert.equal(durationLabel(3700),'61:40')
  assert.equal(progressInfo(baseline,1300).elapsed,200)
})
