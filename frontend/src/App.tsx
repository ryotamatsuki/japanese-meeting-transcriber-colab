import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, ReactNode } from 'react'
import {
  Activity, AlertCircle, ArrowRight, Check, CheckCheck, ChevronDown, ChevronLeft,
  ChevronRight, Clock3, CloudUpload, Download, FileAudio2, FileText, Headphones,
  LoaderCircle, LogOut, Menu, Mic2, Pause, Play, Plus, RotateCw, Save, Search,
  ShieldCheck, SlidersHorizontal, Trash2, Volume2, WandSparkles, X, RotateCcw, Pencil, ListChecks
} from 'lucide-react'

type JobStatus = 'uploading' | 'queued' | 'running' | 'complete' | 'failed' | 'deleted'
type Job = { id: string; filename: string; status: JobStatus; received: number;
  expected_size: number; duration: number | null; speakers: number; created: number;
  utterances?: number; error?: string }
type Row = { start: number; end: number; speaker: string; text: string }
type ReviewWindow = { id: string; start: number; end: number }
type Review = { available: boolean; total_candidates: number; windows: ReviewWindow[]; reviewed_ids: string[] }
type Session = { csrf: string; anonymous?: boolean; limits: { file_bytes: number; duration_seconds: number } }
const PREVIEW_ONLY = import.meta.env.VITE_PREVIEW_ONLY === 'true'
const CHUNK = 4 * 1024 * 1024
const PAGE = 60
let csrf = ''

async function api<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.method && !['GET', 'HEAD'].includes(init.method.toUpperCase())) headers.set('X-CSRF', csrf)
  const res = await fetch(url, { ...init, headers, credentials: 'same-origin' })
  if (res.status === 401) { window.location.assign('/'); throw Error('セッションの期限が切れました。ページを再読み込みしてください') }
  if (!res.ok) {
    let reason = 'HTTP ' + res.status
    try { const value = await res.json() as {detail?: string}; if (typeof value.detail === 'string') reason = value.detail } catch {}
    throw Error(reason)
  }
  return res.json() as Promise<T>
}
function hhmmss(v: number | null | undefined) {
  if (v == null || !Number.isFinite(v)) return '--:--'
  const seconds = Math.max(0, Math.floor(v))
  return String(Math.floor(seconds / 60)).padStart(2, '0') + ':' + String(seconds % 60).padStart(2, '0')
}
function mb(v: number) { return (v / 1048576).toFixed(1) + ' MB' }
function speakerColor(name: string) {
  const letter = name.trim().match(/(?:話者)?([A-E])$/i)
  if (letter) return 'color-' + 'ABCDE'.indexOf(letter[1].toUpperCase())
  let hash = 0
  for (const code of name) hash = (hash * 31 + code.charCodeAt(0)) % 5
  return 'color-' + hash
}
const statuses: Record<JobStatus, { label: string; style: string }> = {
  uploading: { label: 'アップロード中', style: 'neutral' },
  queued: { label: '処理待ち', style: 'amber' },
  running: { label: 'AIが処理中', style: 'blue' },
  complete: { label: '完了', style: 'green' },
  failed: { label: '失敗', style: 'red' },
  deleted: { label: '削除済み', style: 'neutral' },
}
function TinyButton(props: {icon: ReactNode; title: string; disabled?: boolean; onClick: () => void}) {
  return <button className="icon-button" type="button" aria-label={props.title} title={props.title} onClick={props.onClick} disabled={props.disabled}>{props.icon}</button>
}

export default function App() {
  const [ready, setReady] = useState(false)
  const [session, setSession] = useState<Session | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [review, setReview] = useState<Review | null>(null)
  const [changed, setChanged] = useState(false)
  const [saving, setSaving] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [speakerCount, setSpeakerCount] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [query, setQuery] = useState('')
  const [reviewOnly, setReviewOnly] = useState(false)
  const [followAudio, setFollowAudio] = useState(true)
  const [page, setPage] = useState(0)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [mobileMenu, setMobileMenu] = useState(false)
  const [actionId, setActionId] = useState<string | null>(null)
  const [notice, setNotice] = useState<{message: string; error?: boolean} | null>(null)
  const player = useRef<HTMLAudioElement | null>(null)
  const inputFile = useRef<HTMLInputElement | null>(null)
  const rowNodes = useRef(new Map<number, HTMLElement>())
  const revision = useRef(0)
  const selectedId = useRef<string | null>(null)
  const opening = useRef(false)
  const refresh = useCallback(async () => {
    const result = await api<{jobs: Job[]}>('/api/jobs')
    setJobs(result.jobs)
  }, [])

  useEffect(() => {
    let mounted = true
    async function initialize() {
      try {
        const value = await api<Session>('/api/session')
        if (!mounted) return
        csrf = value.csrf
        setSession(value)
        await refresh()
        if (mounted) setReady(true)
      } catch (e) { if (mounted) setNotice({ message: String(e), error: true }) }
    }
    void initialize()
    return () => { mounted = false }
  }, [refresh])
  useEffect(() => {
    // The edit workspace must open at the top, not preserve a long dashboard's scroll position.
    window.scrollTo({top:0,behavior:'instant'})
  }, [selected?.id])
  useEffect(() => {
    if (!ready) return
    const timer = window.setInterval(() => { void refresh().catch(() => {}) }, 10000)
    return () => window.clearInterval(timer)
  }, [ready, refresh])
  useEffect(() => {
    if (!changed) return
    const before = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', before)
    return () => window.removeEventListener('beforeunload', before)
  }, [changed])
  useEffect(() => {
    function shortcut(e: KeyboardEvent) {
      const el = e.target as HTMLElement
      const editable = ['INPUT','TEXTAREA','SELECT'].includes(el.tagName) || el.isContentEditable
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault(); document.getElementById('save-transcript')?.click()
      } else if (!editable && selectedId.current && player.current && e.code === 'Space') {
        e.preventDefault()
        if (player.current.paused) void player.current.play().catch(() => {})
        else player.current.pause()
      } else if (!editable && selectedId.current && player.current && (e.code === 'ArrowLeft' || e.code === 'ArrowRight')) {
        e.preventDefault()
        const change = e.code === 'ArrowLeft' ? -3 : 3
        const limit = Number.isFinite(player.current.duration) ? player.current.duration : Infinity
        player.current.currentTime = Math.max(0, Math.min(limit, player.current.currentTime + change))
        setTime(player.current.currentTime)
      }
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [])

  const speakers = useMemo(() => [...new Set(rows.map(r => r.speaker))], [rows])
  const activeIndex = useMemo(() => rows.findIndex(r => r.start <= time && time < r.end), [rows,time])
  // Only overlap review windows have verified per-window check state. This tab
  // must not imply that ordinary transcript rows were human-reviewed.
  const pendingWindows = useMemo(() => review?.available
    ? review.windows.filter(w => !review.reviewed_ids.includes(w.id))
    : [], [review])
  const matches = useMemo(() => rows.map((row, index) => ({row,index})).filter(x => {
    if (reviewOnly && !pendingWindows.some(w => x.row.start < w.end && w.start < x.row.end)) return false
    return !query.trim() || (x.row.speaker + ' ' + x.row.text).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
  }), [rows,query,reviewOnly,pendingWindows])
  const pages = Math.max(1, Math.ceil(matches.length / PAGE))
  const currentPage = Math.min(page, pages - 1)
  const visible = matches.slice(currentPage * PAGE, (currentPage + 1) * PAGE)
  const running = jobs.find(j => ['uploading','queued','running'].includes(j.status))
  const completedCount = jobs.filter(j=>j.status==='complete').length
  useEffect(() => {
    if (!followAudio || !playing || !selectedId.current || query || reviewOnly || activeIndex < 0) return
    const destination = Math.floor(activeIndex / PAGE)
    if (page !== destination) setPage(destination)
    const timeout = window.setTimeout(() => rowNodes.current.get(activeIndex)?.scrollIntoView({
      behavior: 'smooth', block: 'nearest'
    }), 80)
    return () => window.clearTimeout(timeout)
  }, [activeIndex,followAudio,playing,page,query,reviewOnly])
  function abandon() { return !changed || window.confirm('保存していない編集があります。破棄しますか？') }
  function edit(fn: (items: Row[]) => Row[]) { revision.current++; setRows(fn); setChanged(true) }
  function changeField(index: number, field: keyof Row, value: string | number) {
    edit(before => before.map((r,i) => i === index ? {...r,[field]:value} : r))
  }
  async function openJob(j: Job) {
    if (opening.current || !abandon()) return
    opening.current = true; setActionId(j.id); setNotice(null)
    try {
      const [info, data, checks] = await Promise.all([
        api<Job>('/api/jobs/' + j.id),
        api<{rows: Row[]}>('/api/jobs/' + j.id + '/rows'),
        api<Review>('/api/jobs/' + j.id + '/review'),
      ])
      if (info.status !== 'complete') throw Error('文字起こしが完了していません')
      setSelected(info); selectedId.current=info.id; setRows(data.rows); setReview(checks)
      revision.current=0; setChanged(false); setQuery(''); setReviewOnly(false); setPage(0); setTime(0); setPlaying(false); setMobileMenu(false)
    } catch(e) { setNotice({message:'編集画面を開けません: '+String(e),error:true}) }
    finally { opening.current=false;setActionId(null) }
  }
  function closeJob() {
    if (!abandon()) return
    setSelected(null); selectedId.current=null; setRows([]);setChanged(false);setReview(null);setPlaying(false)
  }
  function pick(f: File | null) { if (f) setFile(f) }
  function onDrop(e: DragEvent<HTMLDivElement>) { e.preventDefault();setDragging(false);pick(e.dataTransfer.files.item(0)) }
  async function upload() {
    if (PREVIEW_ONLY) return
    if (!file || uploading) return
    if (session && file.size > session.limits.file_bytes) {setNotice({message:'ファイルサイズの上限は'+mb(session.limits.file_bytes)+'です',error:true});return}
    setNotice(null);setUploading(true);setUploadProgress(0)
    try {
      const job = await api<Job>('/api/jobs', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({filename:file.name,size:file.size,diarization:true,speakers:speakerCount})})
      for (let offset=0;offset<file.size;offset+=CHUNK) {
        await api<Job>('/api/jobs/'+job.id+'/chunks?offset='+offset,{method:'PUT',headers:{'Content-Type':'application/octet-stream'},
          body:file.slice(offset,Math.min(offset+CHUNK,file.size))})
        setUploadProgress(Math.round(100*Math.min(offset+CHUNK,file.size)/file.size))
      }
      const started=await api<Job>('/api/jobs/'+job.id+'/finish',{method:'POST'})
      setNotice({message:started.status==='failed'?'GPU処理の開始に失敗しました':'アップロード完了。AI処理を開始します。',error:started.status==='failed'})
      setFile(null);if(inputFile.current)inputFile.current.value=''
      await refresh()
    } catch(e) {
      setNotice({message:'アップロード失敗: '+String(e)+'。履歴の未完了ジョブを削除して再試行できます。',error:true})
      await refresh().catch(()=>{})
    } finally {setUploading(false)}
  }
  async function save() {
    if (PREVIEW_ONLY) return
    if (!selected || !changed || saving) return
    const copy=rows.map(r=>({...r})), savedRevision=revision.current
    setSaving(true)
    try {
      await api('/api/jobs/'+selected.id+'/rows',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:copy})})
      if (savedRevision===revision.current) {setChanged(false);setNotice({message:'修正を保存しました。ZIPを出力できます。'})}
      else setNotice({message:'保存中に新しい修正がありました。再度保存してください。'})
    } catch(e) {setNotice({message:'保存できません: '+String(e),error:true})}
    finally {setSaving(false)}
  }
  async function remove(j: Job) {
    if (PREVIEW_ONLY) return
    if (selected?.id===j.id && !abandon()) return
    if (!window.confirm('「'+j.filename+'」の録音と文字起こしを完全に削除しますか？')) return
    setActionId(j.id)
    try {
      await api('/api/jobs/'+j.id,{method:'DELETE'})
      if (selected?.id===j.id) {setSelected(null);selectedId.current=null;setRows([]);setChanged(false)}
      setNotice({message:'保存データを削除しました。'})
      await refresh()
    } catch(e) {setNotice({message:'削除できません: '+String(e),error:true})}
    finally {setActionId(null)}
  }
  async function logout() {
    if (PREVIEW_ONLY) { window.location.assign('/'); return }
    if (!abandon()) return
    try {await api('/logout',{method:'POST'});window.location.assign('/login')}
    catch(e) {setNotice({message:String(e),error:true})}
  }
  function seek(value: number) {if(player.current) {player.current.currentTime=value;setTime(value)}}
  function playFrom(index: number) {
    const row=rows[index]
    if (!row || !player.current) return
    seek(row.start)
    void player.current.play().catch(()=>setNotice({message:'音声を再生できません',error:true}))
  }
  function gotoRow(index: number) {
    if (index<0) return
    setQuery('');setPage(Math.floor(index/PAGE))
    window.setTimeout(()=>rowNodes.current.get(index)?.scrollIntoView({behavior:'smooth',block:'center'}),80)
  }
  function split(index: number) {
    const row=rows[index]
    const answer=window.prompt('分割位置（秒）',((row.start+row.end)/2).toFixed(2))
    if (answer===null) return
    const mid=Number(answer)
    if (!Number.isFinite(mid) || mid<=row.start || mid>=row.end) {setNotice({message:'開始秒と終了秒の間を指定してください',error:true});return}
    edit(before=>{const next=[...before];next.splice(index,1,{...row,end:mid},{...row,start:mid,text:''});return next})
  }
  function merge(index: number) {
    if (index>=rows.length-1) return
    edit(before=>{const next=[...before],a=next[index],b=next[index+1]
      next.splice(index,2,{...a,end:Math.max(a.end,b.end),text:(a.text+' '+b.text).trim()});return next})
  }
  function renameSpeaker(previous: string) {
    const answer = window.prompt('「' + previous + '」の発言をすべて変更する新しい話者名', previous)
    if (answer === null) return
    const next = answer.trim()
    if (!next || next.length > 80) {
      setNotice({message:'話者名は1〜80文字で入力してください',error:true})
      return
    }
    if (next === previous) return
    if (speakers.includes(next) && !window.confirm('既存の「' + next + '」と統合しますか？')) return
    edit(before => before.map(r => r.speaker === previous ? {...r,speaker:next} : r))
    setNotice({message:'話者名を一括変更しました。保存すると反映されます。'})
  }
  function addRow() {
    edit(before=>[...before,{start:time,end:time+1,speaker:speakers[0]||'話者未設定',text:''}].sort((a,b)=>a.start-b.start))
    setQuery('');setPage(Math.floor(rows.length/PAGE))
  }
  async function checkReview(id: string, checked: boolean) {
    if (!selected || !review) return
    const previous=review, reviewed_ids=checked?[...new Set([...review.reviewed_ids,id])]:review.reviewed_ids.filter(x=>x!==id)
    setReview({...review,reviewed_ids})
    try {await api('/api/jobs/'+selected.id+'/review/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({reviewed:checked})})}
    catch(e) {setReview(previous);setNotice({message:'確認状態の保存に失敗: '+String(e),error:true})}
  }

  return <div className="app-shell">
    <aside className={'sidebar'+(mobileMenu?' sidebar-open':'')}>
      <div className="brand"><div className="brand-symbol"><Activity size={26}/></div>
        <div><strong>Kiroku<span>.</span></strong><small>MEETING INTELLIGENCE</small></div>
        <button className="mobile-close" onClick={()=>setMobileMenu(false)} aria-label="メニューを閉じる"><X size={20}/></button></div>
      <p className="sidebar-caption">WORKSPACE</p>
      <button className={'nav-item'+(!selected?' nav-active':'')} onClick={()=>{if(selected)closeJob();setMobileMenu(false)}}><CloudUpload size={18}/> 新しい文字起こし</button>
      <div className="sidebar-caption sidebar-history"><span>RECENT FILES</span><span>{jobs.length}</span></div>
      <div className="side-list">{jobs.length===0&&<span className="side-empty">ファイルがありません</span>}
        {jobs.map(j=><button className={'side-item'+(selected?.id===j.id?' side-current':'')} key={j.id}
          onClick={()=>j.status==='complete'?void openJob(j):setNotice({message:'現在の状態: '+statuses[j.status].label})} disabled={actionId!==null}>
          <FileAudio2 size={18}/><span><strong title={j.filename}>{j.filename}</strong><small>{statuses[j.status]?.label||j.status}</small></span>
          {j.status==='complete'&&<ChevronRight size={14}/>}</button>)}</div>
      <div className="sidebar-footer">
        <div className="sidebar-privacy"><ShieldCheck size={18}/><div>{PREVIEW_ONLY ? 'UIデモ（実データなし）' : session?.anonymous ? 'あなた専用の一時作業領域' : '非公開ワークスペース'}<small>{PREVIEW_ONLY ? 'アップロード・保存は無効' : session?.anonymous ? '録音は24時間経過後に順次削除・非機密音声のみ' : '非機密音声のみ'}</small></div></div>
        {!PREVIEW_ONLY&&!session?.anonymous&&<button onClick={()=>void logout()}><LogOut size={17}/> ログアウト</button>}
      </div>
    </aside>
    {mobileMenu&&<div className="sidebar-shade" onClick={()=>setMobileMenu(false)}/>}
    <div className="app-content">
      <header className="topbar"><div className="breadcrumbs">
        <button className="menu-button" onClick={()=>setMobileMenu(true)} aria-label="メニューを開く"><Menu size={21}/></button>
        <span>ワークスペース</span><ChevronRight size={15}/><strong>{selected?'文字起こし編集':'ダッシュボード'}</strong>
      </div><div className="topbar-side"><span className="private-tag"><i/> {PREVIEW_ONLY ? 'PUBLIC UI PREVIEW' : session?.anonymous ? 'ANONYMOUS SESSION' : 'PRIVATE ALPHA'}</span><span className="avatar">K</span></div></header>
      <main className="workspace">
        {PREVIEW_ONLY&&<div className="preview-warning" role="status"><ShieldCheck size={19}/><span><strong>パスワード不要のデザインプレビュー</strong>　サンプル会議だけを表示しています。音声アップロード・AI推論・保存・ダウンロードは無効です。</span></div>}
        {!ready?<div className="loading"><LoaderCircle size={30} className="spin"/> 認証状態を確認しています…</div>:
        selected?<div className="editor-page">
          <div className="editor-heading"><div>
            <div className="studio-kicker"><span/> TRANSCRIPT STUDIO</div>
            <button className="back-button" onClick={closeJob}><ChevronLeft size={16}/> ワークスペースに戻る</button>
            <div className="document-title"><span className="document-icon"><FileAudio2 size={25}/></span><div><h1>{selected.filename}</h1><p>{hhmmss(selected.duration)} · {rows.length} 発言 · {speakers.length} 話者</p></div></div>
          </div><div className="editor-actions">
            <span className={'save-state'+(changed?' unsaved':'')}>{changed?<AlertCircle size={16}/>:<CheckCheck size={16}/>} {changed?'未保存':'保存済み'}</span>
            <button id="save-transcript" className="primary-button" disabled={PREVIEW_ONLY||!changed||saving} onClick={()=>void save()}>{saving?<LoaderCircle size={17} className="spin"/>:<Save size={17}/>} 保存する</button>
            {PREVIEW_ONLY||changed||saving?<button className="outlined-button" disabled title={PREVIEW_ONLY?'公開プレビューでは出力できません':'先に変更を保存してください'}><Download size={17}/> ZIP出力</button>:
              <a className="outlined-button" href={'/api/jobs/'+selected.id+'/download'}><Download size={17}/> ZIP出力</a>}
          </div></div>
          <div className="editing-grid"><section className="transcript-panel">
            <div className="panel-header studio-header"><div><h2>文字起こし</h2><p>音声を聞きながら、発言を確認・編集</p></div>
              <div className="panel-tools"><label className="search-field"><Search size={17}/><input placeholder="発言を検索…" aria-label="発言を検索" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}}/>
                {query&&<button onClick={()=>{setQuery('');setPage(0)}} aria-label="検索をクリア"><X size={14}/></button>}</label>
                <button className="add-button" onClick={addRow}><Plus size={17}/> 発言を追加</button></div></div>
            <div className="studio-subtoolbar">
              <div className="studio-tabs" role="group" aria-label="発言の表示条件">
                <button type="button" aria-pressed={!reviewOnly} className={!reviewOnly?'active':''} onClick={()=>{setReviewOnly(false);setPage(0)}}><FileText size={14}/> 全文 <span>{rows.length}</span></button>
                <button type="button" aria-pressed={reviewOnly} className={reviewOnly?'active':''} onClick={()=>{setReviewOnly(true);setPage(0)}}><ListChecks size={14}/> 重複要確認 <span>{pendingWindows.length}</span></button>
              </div>
              <button className={'follow-toggle'+(followAudio?' enabled':'')} type="button" aria-pressed={followAudio} onClick={()=>setFollowAudio(value=>!value)}><Volume2 size={14}/> 自動追従 {followAudio?'ON':'OFF'}</button>
            </div>
            <div className="transcript-list">{visible.length===0?<div className="empty-list">{reviewOnly ? '未確認の重複発話候補はありません' : '一致する発言がありません'}</div>:visible.map(({row,index})=>
              <div className={'transcript-item'+(activeIndex===index?' transcript-active':'')} key={index}
                ref={el=>{if(el)rowNodes.current.set(index,el);else rowNodes.current.delete(index)}}>
                <button className="utterance-play" onClick={()=>playFrom(index)} title="この発言から再生" aria-label={'発言'+(index+1)+'を再生'}><Play size={15} fill="currentColor"/></button>
                <div className="utterance-content">
                  <div className="utterance-meta"><span className="sequence">{String(index+1).padStart(3,'0')}</span>
                    <input className={'speaker-name '+speakerColor(row.speaker)} value={row.speaker} aria-label={'発言'+(index+1)+'の話者名'} onChange={e=>changeField(index,'speaker',e.target.value)}/>
                    <label className="time-field"><span className="visually-hidden">開始秒</span><input type="number" min="0" step=".01" aria-label="開始秒" value={row.start} onChange={e=>changeField(index,'start',Number(e.target.value))}/></label>
                    <span className="time-dash">–</span>
                    <label className="time-field"><span className="visually-hidden">終了秒</span><input type="number" min="0" step=".01" aria-label="終了秒" value={row.end} onChange={e=>changeField(index,'end',Number(e.target.value))}/></label>
                    <div className="row-actions"><TinyButton icon={<SlidersHorizontal size={15}/>} title="発言を分割" onClick={()=>split(index)}/>
                      <TinyButton icon={<ChevronDown size={15}/>} title="次と結合" disabled={index>=rows.length-1} onClick={()=>merge(index)}/>
                      <TinyButton icon={<Trash2 size={15}/>} title="発言を削除" onClick={()=>{if(window.confirm('この発言を削除しますか？'))edit(before=>before.filter((_,i)=>i!==index))}}/></div></div>
                  <textarea value={row.text} aria-label={'発言'+(index+1)+'のテキスト'} rows={Math.max(2,Math.min(6,Math.ceil(row.text.length/62)))} spellCheck={false} onChange={e=>changeField(index,'text',e.target.value)}/>
                </div>
              </div>)}</div>
            <div className="pagination"><span>{matches.length} 件中 {matches.length?currentPage*PAGE+1:0}–{Math.min(matches.length,(currentPage+1)*PAGE)} 件</span>
              <div><TinyButton title="前のページ" disabled={currentPage===0} icon={<ChevronLeft size={17}/>} onClick={()=>setPage(Math.max(0,currentPage-1))}/>
                <span>{currentPage+1} / {pages}</span>
                <TinyButton title="次のページ" disabled={currentPage>=pages-1} icon={<ChevronRight size={17}/>} onClick={()=>setPage(Math.min(pages-1,currentPage+1))}/></div></div>
          </section>
          <aside className="inspector"><div className="inspector-title"><h3><SlidersHorizontal size={18}/> 編集インスペクター</h3></div>
            <div className="inspector-group-heading"><span>話者を管理</span><span>{speakers.length}人</span></div>
            <p>話者をクリックすると、該当するすべての発言の名前を一括変更できます。</p>
            <div className="speaker-list">{speakers.map(name=><div className="speaker-entry" key={name}><span className={'speaker-avatar '+speakerColor(name)}><Mic2 size={16}/></span><strong title={name}>{name||'未設定'}</strong><small>{rows.filter(r=>r.speaker===name).length}件</small>
              <TinyButton icon={<Pencil size={14}/>} title={name+'を一括変更'} onClick={()=>renameSpeaker(name)}/></div>)}</div>
            {review?.available&&review.windows.length>0&&<><div className="inspector-title inspector-divider"><h3><Volume2 size={18}/> 重複発話を確認</h3><span>{review.reviewed_ids.length}/{review.windows.length}</span></div>
              <p>同時発話の可能性がある区間です。原音声を確認してください。</p>
              <div className="review-list">{review.windows.map(w=><div className="review-item" key={w.id}>
                <button onClick={()=>{seek(w.start);void player.current?.play().catch(()=>{})}}><Play size={13}/> {hhmmss(w.start)}–{hhmmss(w.end)}</button>
                <button onClick={()=>gotoRow(rows.findIndex(r=>r.start<w.end && w.start<r.end))}>発言へ</button>
                <label><input type="checkbox" checked={review.reviewed_ids.includes(w.id)} onChange={e=>void checkReview(w.id,e.target.checked)}/> 確認済</label>
              </div>)}</div></>}
            <div className="inspector-group-heading shortcuts-heading"><span>キーボード操作</span></div>
            <div className="shortcut-list"><div><kbd>Space</kbd><span>再生 / 一時停止</span></div><div><kbd>←</kbd><kbd>→</kbd><span>3秒移動</span></div><div><kbd>⌘ / Ctrl + S</kbd><span>修正を保存</span></div></div>
            <div className="inspector-warning"><ShieldCheck size={18}/><span>話者ラベルはAIの推定です。音声との照合が必要です。</span></div>
          </aside></div>
          <div className="audio-dock"><audio key={selected.id} ref={player} src={'/api/jobs/'+selected.id+'/audio'} preload="metadata"
              onTimeUpdate={e=>setTime(e.currentTarget.currentTime)} onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} onEnded={()=>setPlaying(false)}/>
            <div className="dock-file"><div className="dock-file-icon"><Headphones size={22}/></div><div><strong title={selected.filename}>{selected.filename}</strong><span>オリジナル音声</span></div></div>
            <div className="dock-player"><button className="skip-button" aria-label="3秒戻る" title="3秒戻る (←)" onClick={()=>seek(Math.max(0,time-3))}><RotateCcw size={18}/><span>3秒</span></button><button className="play-button" aria-label={playing?'一時停止':'再生'} onClick={()=>{if(!player.current)return;if(playing)player.current.pause();else void player.current.play().catch(()=>setNotice({message:'再生に失敗しました',error:true}))}}>{playing?<Pause size={20} fill="currentColor"/>:<Play size={20} fill="currentColor"/>}</button>
              <span className="clock">{hhmmss(time)}</span><input className="audio-range" type="range" aria-label="音声の再生位置" min={0} max={selected.duration||1} step={0.1} value={Math.min(time,selected.duration||1)} onChange={e=>seek(Number(e.target.value))}/>
              <span className="clock">{hhmmss(selected.duration)}</span></div>
            <div className="dock-rate"><Volume2 size={17}/><select value={speed} aria-label="再生速度" onChange={e=>{const v=Number(e.target.value);setSpeed(v);if(player.current)player.current.playbackRate=v}}>
              <option value=".75">0.75×</option><option value="1">1.0×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2.0×</option>
            </select></div>
          </div>
        </div>:<div className="dashboard">
          <div className="dashboard-heading"><div className="eyebrow"><WandSparkles size={14}/> AI-POWERED WORKSPACE</div><h1>会議の記録を、もっとスマートに。</h1>
            <p>音声をアップロードするだけ。AIが話者ごとに文字起こしし、確認と編集をひとつの画面で。</p></div>
          <div className="stats"><div className="stat-card"><span><FileText size={18}/> 完了した文字起こし</span><strong>{String(completedCount).padStart(2,'0')}</strong><small>保存中のファイル</small></div>
            <div className="stat-card"><span><Clock3 size={18}/> 現在の処理</span><strong className="stat-text">{running?statuses[running.status]?.label:'待機中'}</strong><small>同時実行は1件まで</small></div>
            <div className="stat-card stat-secure"><span><ShieldCheck size={18}/> データの保護</span><strong className="stat-text">{session?.anonymous ? '利用者別に分離' : '非公開'}</strong><small>{session?.anonymous ? '登録・パスワード不要' : 'パスワード認証・24時間保持'}</small></div></div>
          <section className="upload-panel"><div className="section-heading"><div><h2>新しい文字起こし</h2><p>会議音声をアップロードして、AI処理を開始します。</p></div><span className="step-mark">STEP 01 / 02</span></div>
            <div className={'drop-area'+(dragging?' is-dragging':'')+(file?' has-file':'')} role="button" tabIndex={0} aria-label="音声を選択"
              onDragOver={e=>{e.preventDefault();setDragging(true)}} onDragLeave={()=>setDragging(false)} onDrop={onDrop}
              onClick={()=>!uploading&&inputFile.current?.click()} onKeyDown={e=>{if((e.key==='Enter'||e.key===' ')&&!uploading){e.preventDefault();inputFile.current?.click()}}}>
              <input ref={inputFile} disabled={PREVIEW_ONLY} hidden type="file" accept=".mp3,.m4a,.wav,.flac,.ogg,.mp4,.webm,audio/*" onChange={(e:ChangeEvent<HTMLInputElement>)=>pick(e.target.files?.item(0)||null)}/>
              <div className="drop-symbol">{file?<FileAudio2 size={29}/>:<CloudUpload size={29}/>}</div>
              <strong>{file?file.name:'ここに音声ファイルをドラッグ＆ドロップ'}</strong>
              <p>{file?mb(file.size)+' · クリックして変更':'またはクリックしてファイルを選択'}</p>
              <span>MP3, WAV, M4A, FLAC, OGG, MP4, WEBM · 最大180 MB / 60分</span></div>
            <div className="upload-footer"><div className="speaker-setting"><label htmlFor="speakers">話者数</label><div><Mic2 size={18}/><select id="speakers" value={speakerCount} disabled={uploading} onChange={e=>setSpeakerCount(Number(e.target.value))}>
              <option value={0}>自動推定</option><option value={2}>2人</option><option value={3}>3人</option><option value={4}>4人</option>
            </select><ChevronDown size={16}/></div></div>
              <span className="diar-setting"><Check size={16}/> {PREVIEW_ONLY?'デザインプレビュー（AI処理は無効）':'話者分離・重複発話検出を有効化'}</span>
              <button className="primary-button upload-submit" disabled={PREVIEW_ONLY||!file||uploading} onClick={()=>void upload()}>{uploading?<LoaderCircle size={19} className="spin"/>:<WandSparkles size={19}/>} {uploading?'転送中':'文字起こしを開始'} <ArrowRight size={17}/></button></div>
            {uploading&&<div className="upload-progress"><div><span style={{width:uploadProgress+'%'}}/></div><p>アップロード中… {uploadProgress}%</p></div>}
          </section>
          <section className="recent"><div className="section-heading"><div><h2>最近の文字起こし</h2><p>処理結果を確認したり、作業を再開できます。</p></div>
            <button className="refresh-button" onClick={()=>void refresh()}><RotateCw size={16}/> 更新</button></div>
            {jobs.length===0?<div className="empty-records"><FileAudio2 size={28}/><strong>まだファイルがありません</strong><p>最初の音声をアップロードしてください。</p></div>:
              <div className="record-list">{jobs.map(j=><div className="record" key={j.id}><div className="record-icon"><FileAudio2 size={22}/></div>
                <div className="record-name"><strong title={j.filename}>{j.filename}</strong><small>{new Date(j.created*1000).toLocaleString('ja-JP')} · {j.duration?hhmmss(j.duration):mb(j.received||0)}</small></div>
                <span className={'status status-'+(statuses[j.status]?.style||'neutral')}><i/>{statuses[j.status]?.label||j.status}</span>
                <div className="record-actions">{j.status==='complete'&&<button className="outlined-button" disabled={actionId!==null} onClick={()=>void openJob(j)}>編集する <ArrowRight size={16}/></button>}
                  {['uploading','complete','failed'].includes(j.status)&&<TinyButton icon={<Trash2 size={17}/>} title="録音と結果を削除" disabled={actionId!==null} onClick={()=>void remove(j)}/>}</div>
              </div>)}</div>}
          </section>
          <div className="safety-banner"><ShieldCheck size={21}/><p><strong>音声とデータの取り扱い</strong> 許諾済みの非機密音声のみを使用し、文字起こし結果は原音声と照合してください。</p></div>
        </div>}
      </main>
      <footer className="app-footer"><span>Kiroku · Private Alpha v0.1</span><span>音声は24時間経過後に順次削除 · AIの出力には誤りが含まれる場合があります</span></footer>
    </div>
    {notice&&<div className={'toast'+(notice.error?' toast-error':'')} role="status">{notice.error?<AlertCircle size={18}/>:<Check size={18}/>}<span>{notice.message}</span><button onClick={()=>setNotice(null)} aria-label="通知を閉じる"><X size={17}/></button></div>}
  </div>
}
