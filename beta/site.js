'use strict';
let csrf='', current=null, edits=[];
const $=id=>document.getElementById(id);
async function call(url, options={}){
  const h=options.headers||{};
  if(options.method&&options.method!=='GET')h['X-CSRF']=csrf;
  const r=await fetch(url,{credentials:'same-origin',...options,headers:h});
  if(r.status===401){location.href='/login';throw Error('認証が切れました');}
  if(!r.ok){let detail='HTTP '+r.status;try{detail=(await r.json()).detail||detail;}catch(e){}throw Error(detail);}
  return r.status===204?null:r.json();
}
function fmt(x){return Number(x).toFixed(2)+' 秒';}
function button(text,callback,cls='subtle'){const el=document.createElement('button');el.textContent=text;el.className=cls;el.type='button';el.onclick=callback;return el;}
async function list(){
  try{const data=await call('/api/jobs');const root=$('jobs');root.replaceChildren();
    const labels={uploading:'アップロード中',queued:'GPU待機中',running:'文字起こし処理中',complete:'完了',failed:'失敗'};
    if(!data.jobs.length)root.textContent='まだ処理履歴がありません。';
    for(const job of data.jobs){const div=document.createElement('div');div.className='job';
      const label=document.createElement('div');const name=document.createElement('strong');name.textContent=job.filename;const meta=document.createElement('span');meta.textContent=`状態: ${labels[job.status]||job.status} / ${(job.received/1024/1024).toFixed(1)} MiB`;
      label.append(name,meta);div.append(label);
      if(job.status==='complete')div.append(button('編集する',()=>openEditor(job.id)));
      if(['failed','complete','uploading'].includes(job.status))div.append(button('削除',async()=>{if(!confirm('録音と結果を削除しますか？'))return;await call('/api/jobs/'+job.id,{method:'DELETE'});if(current===job.id){current=null;$('editor').hidden=true;}await list();}));
      root.append(div);
    }
  }catch(e){$('jobsstatus').textContent=e.message;}
}
$('upload').addEventListener('submit',async ev=>{
  ev.preventDefault();const file=$('audiofile').files[0];if(!file)return;
  const info=$('uploadinfo');$('bar').style.width='0%';
  try{info.textContent='アップロードを開始…';const job=await call('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,size:file.size,diarization:$('diar').checked,speakers:Number($('speakers').value)})});
    const chunk=4*1024*1024;
    for(let offset=0;offset<file.size;offset+=chunk){const data=file.slice(offset,Math.min(offset+chunk,file.size));await call('/api/jobs/'+job.id+'/chunks?offset='+offset,{method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:data});$('bar').style.width=Math.round(100*Math.min(offset+chunk,file.size)/file.size)+'%';info.textContent=`転送 ${Math.min(offset+chunk,file.size)} / ${file.size} バイト`;}
    const started=await call('/api/jobs/'+job.id+'/finish',{method:'POST'});info.textContent='アップロード完了。GPU処理を開始しました。';await list();
  }catch(e){info.textContent='エラー: '+e.message;await list();}
});
async function openEditor(id){
  try{const job=await call('/api/jobs/'+id), r=await call('/api/jobs/'+id+'/rows');current=id;edits=r.rows.map(x=>({...x}));
    $('editor').hidden=false;$('player').src='/api/jobs/'+id+'/audio';$('download').href='/api/jobs/'+id+'/download';
    renderRows();$('editor').scrollIntoView({behavior:'smooth'});
  }catch(e){$('editstatus').textContent=e.message;}
}
function renderRows(){const root=$('rows');root.replaceChildren();
 edits.forEach((r,i)=>{
  const card=document.createElement('div');card.className='utterance';card.dataset.index=i;
  const top=document.createElement('div');top.className='controls';
  const speak=document.createElement('input');speak.type='text';speak.value=r.speaker;speak.setAttribute('aria-label','話者名');speak.oninput=()=>r.speaker=speak.value;
  const start=document.createElement('input');start.type='number';start.step='.01';start.min='0';start.value=r.start;start.setAttribute('aria-label','開始秒');start.onchange=()=>r.start=Number(start.value);
  const end=document.createElement('input');end.type='number';end.step='.01';end.min='0';end.value=r.end;end.setAttribute('aria-label','終了秒');end.onchange=()=>r.end=Number(end.value);
  top.append(button('▶ 再生',()=>{$('player').currentTime=r.start;$('player').play();}),speak,start,end,
    button('分割',()=>{const mid=Number(prompt('分割する秒数を入力',((r.start+r.end)/2).toFixed(2)));if(!(r.start<mid&&mid<r.end))return;const before={...r,end:mid},after={...r,start:mid,text:''};edits.splice(i,1,before,after);renderRows();}),
    button('次と結合',()=>{if(i+1>=edits.length)return;r.end=Math.max(r.end,edits[i+1].end);r.text+=' '+edits[i+1].text;edits.splice(i+1,1);renderRows();}),
    button('削除',()=>{if(confirm('この行を削除しますか？')){edits.splice(i,1);renderRows();}}));
  const text=document.createElement('textarea');text.value=r.text;text.setAttribute('aria-label','発話テキスト');text.oninput=()=>r.text=text.value;
  card.append(top,text);root.append(card);
 });
}
$('player').addEventListener('timeupdate',()=>{let t=$('player').currentTime;for(const row of document.querySelectorAll('.utterance')){const r=edits[Number(row.dataset.index)];row.classList.toggle('active',r.start<=t&&t<r.end);}});
$('addrow').onclick=()=>{const t=$('player').currentTime||0;edits.push({start:t,end:t+1,speaker:'話者未設定',text:''});edits.sort((a,b)=>a.start-b.start);renderRows();};
$('save').onclick=async()=>{if(!current)return;try{await call('/api/jobs/'+current+'/rows',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows:edits})});$('editstatus').textContent='修正内容を保存しました。';}catch(e){$('editstatus').textContent='保存できません: '+e.message;}};
$('logout').onclick=async()=>{await call('/logout',{method:'POST'});location.href='/login';};
(async()=>{try{const data=await call('/api/session');csrf=data.csrf;await list();setInterval(list,12000);}catch(e){console.error('Session unavailable');}})();