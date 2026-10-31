/** Reliable UI interpretation of a server-authored processing snapshot.
 * The percentage is audio decoded within ASR, NEVER total job completion.
 */
export type ProcessingPhase = 'preparing' | 'asr' | 'diarization' | 'formatting' | 'saving'
export type ProgressSnapshot = {
  phase: ProcessingPhase
  audio_done?: number
  audio_total?: number
  phase_started_at?: number
  updated_at?: number
}
export type ProgressJob = {
  filename: string
  status: 'uploading' | 'queued' | 'running' | 'complete' | 'failed' | 'deleted'
  duration: number | null
  created: number
  started_at?: number
  progress?: ProgressSnapshot
}

export const processingSteps = [
  {key:'preparing',label:'準備'},
  {key:'asr',label:'文字認識'},
  {key:'diarization',label:'話者分離'},
  {key:'formatting',label:'仕上げ'},
] as const

const ranks: Record<ProcessingPhase, number> = {
  preparing:0, asr:1, diarization:2, formatting:3, saving:3,
}
export function progressInfo(job: ProgressJob, nowSeconds: number) {
  const stage = job.status === 'queued' ? null : job.progress?.phase ?? null
  const stageRank = stage === null ? -1 : ranks[stage]
  const fraction = stage==='asr' && Number.isFinite(job.progress?.audio_done)
    && Number.isFinite(job.progress?.audio_total) && (job.progress?.audio_total ?? 0)>0
    ? Math.max(0,Math.min(1,(job.progress?.audio_done ?? 0)/(job.progress?.audio_total ?? 1)))
    : null
  const started = job.started_at ?? job.created
  const elapsed = Math.max(0, nowSeconds-started)
  const stageElapsed = Math.max(0,nowSeconds-(job.progress?.phase_started_at ?? nowSeconds))
  const fresh = nowSeconds-(job.progress?.updated_at ?? 0) < 35
  // Estimate only the current ASR phase from observed actual throughput.
  // This is NOT the total remaining time, and is hidden if data is too thin.
  const asrRemaining = fraction!==null && stageElapsed>=15 && fraction>=0.12
      && fraction<0.98 && fresh
    ? Math.ceil(stageElapsed*(1-fraction)/fraction)
    : null
  const title = job.status==='queued'?'処理を開始する準備をしています'
    : stage==='preparing'?'音声データを準備しています'
    : stage==='asr'?'音声を文字に変換しています'
    : stage==='diarization'?'誰が話したかを識別しています'
    : stage==='formatting'?'発言と話者を整理しています'
    : stage==='saving'?'結果を安全に保存しています'
    :'AIが会議音声を処理しています'
  return {stageRank, fraction, elapsed, asrRemaining, title}
}

export function durationLabel(seconds: number): string {
  const positive = Math.max(0, Math.floor(Number.isFinite(seconds)?seconds:0))
  return String(Math.floor(positive/60)).padStart(2,'0')+':'
    +String(positive%60).padStart(2,'0')
}
