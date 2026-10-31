import {AudioLines, Check, Clock3, Headphones} from 'lucide-react'
import {durationLabel, processingSteps, progressInfo} from './progressModel'
import type {ProgressJob} from './progressModel'

export function JobProgress({job,now}: {job:ProgressJob;now:number}) {
  const state=progressInfo(job,now)
  const measured=state.fraction!==null
  const percentage=measured?Math.round((state.fraction ?? 0)*100):null
  return <section className="processing-card" aria-label="文字起こしの処理状況">
    <div className="processing-head">
      <div className="processing-heading">
        <div className="processing-kicker"><span className="processing-live-dot"/> PROCESSING</div>
        <h2>文字起こしを作成中</h2>
        <p className="processing-file" title={job.filename}><Headphones size={15}/>{job.filename}
          {job.duration ? <span>· 音声 {durationLabel(job.duration)}</span> : null}</p>
      </div>
      <div className="processing-icon" aria-hidden="true"><AudioLines size={24}/></div>
    </div>
    <div className="processing-main">
      <div className="processing-mainline" aria-live="polite" aria-atomic="true">
        <strong>{state.title}</strong>
        {measured ? <span className="processing-percent">{percentage}% <small>文字認識</small></span> : null}
      </div>
      <div className={'processing-track'+(!measured?' processing-track-unknown':'')}
        role="progressbar" aria-label={measured?'文字認識した音声の割合':'現在の処理工程（完了率は測定できません）'}
        aria-valuemin={measured?0:undefined} aria-valuemax={measured?100:undefined}
        aria-valuenow={measured?percentage??undefined:undefined}
        aria-valuetext={measured?('音声の'+percentage+'%を文字認識済み'):'現在の工程を処理中'}>
        {measured?<div className="processing-fill" style={{width:percentage+'%'}}/>:
          <div className="processing-indeterminate"/>}
      </div>
      <div className="processing-meta">
        <span>{measured?('音声 '+durationLabel(job.progress?.audio_done ?? 0)+' / '+durationLabel(job.progress?.audio_total ?? 0)+' を認識済み'):'工程の進行状況を確認しています'}</span>
        <span><Clock3 size={13}/> 経過 {durationLabel(state.elapsed)}</span>
      </div>
      {state.asrRemaining!==null ?
        <p className="processing-estimate">文字認識工程の残り目安：約{Math.max(1,Math.ceil(state.asrRemaining/60))}分
          <small> · 話者分離・仕上げの時間は含みません</small></p>:
        <p className="processing-estimate subtle">終了時刻は音声の内容や話者分離の処理状況により変わります。</p>}
    </div>
    <ol className="processing-steps" aria-label="処理工程">
      {processingSteps.map((step,index)=><li key={step.key}
        className={index<state.stageRank?'step-done':index===state.stageRank?'step-active':'step-upcoming'}
        aria-current={index===state.stageRank?'step':undefined}>
        <span className="processing-step-marker">
          {index<state.stageRank?<Check size={14}/>:String(index+1).padStart(2,'0')}
        </span>
        <span>{step.label}</span>
      </li>)}
    </ol>
    <p className="processing-footnote">この画面を離れても処理は続きます。結果は「最近の文字起こし」に表示されます。</p>
  </section>
}
