"""Live Chromium E2E with isolated desktop/mobile contexts and real GPU.
Only screenshots after replacing all transcript rows with test markers are saved.
No cookies, input audio, ZIPs or original transcript text are persisted as evidence.
"""
from __future__ import annotations
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import time
import zipfile
from playwright.async_api import async_playwright, expect

URL = os.environ['KIROKU_TEST_URL'].rstrip('/')
SOURCES = [Path(os.environ['KIROKU_TEST_AUDIO_A']), Path(os.environ['KIROKU_TEST_AUDIO_B'])]
OUT = Path(os.environ.get('KIROKU_BROWSER_EVIDENCE', 'local_runs/browser-anonymous'))

async def api(context, method, path, status=200, **kwargs):
    r = await context.request.fetch(URL + path, method=method, **kwargs)
    assert r.status == status, f'{method} protected endpoint expected {status}, got {r.status}'
    return r

async def client(context, index):
    page = await context.new_page()
    page.set_default_timeout(60000)
    errors=[]
    page.on('pageerror', lambda _: errors.append('pageerror'))
    await page.goto(URL, wait_until='networkidle')
    await expect(page.get_by_role('button', name='文字起こしを開始')).to_be_visible(timeout=60000)
    await page.screenshot(path=str(OUT / f'{index}-dashboard.png'), full_page=True)
    session = await (await api(context,'GET','/api/session')).json()
    assert session.get('anonymous') is True
    return page, session['csrf'], errors

async def upload(page, source):
    await page.locator('input[type=file]').set_input_files(str(source))
    async with page.expect_response(lambda r: r.request.method == 'POST' and r.url == URL+'/api/jobs') as created:
        await page.get_by_role('button',name='文字起こしを開始').click()
    response=await created.value
    assert response.status == 200, 'UI job creation failed'
    return (await response.json())['id']

async def wait_gpu(context, job):
    start=time.monotonic()
    while time.monotonic()-start<900:
        state=await (await api(context,'GET','/api/jobs/'+job)).json()
        assert state['status']!='failed', 'GPU pipeline failed'
        if state['status']=='complete': return state
        await asyncio.sleep(3)
    raise AssertionError('GPU completion timed out')

async def edit_download(page, context, job, index, other_marker):
    await page.get_by_role('button',name='編集する',exact=True).click()
    fields=page.locator('textarea[aria-label$="のテキスト"]')
    await expect(fields.first).to_be_visible()
    count=await fields.count()
    assert count>0
    marker=f'KIROKU_BROWSER_{index}_EDIT'
    # Sanitise every visible transcript row before taking editor evidence.
    for i in range(count):
        await fields.nth(i).fill(f'{marker}_{i}')
    await page.get_by_label('発言1の話者名',exact=True).fill(f'利用者{index}')
    await page.get_by_role('button',name='保存する',exact=True).click()
    await expect(page.get_by_role('link',name='ZIP出力')).to_be_visible(timeout=30000)
    audio=await api(context,'GET','/api/jobs/'+job+'/audio')
    assert hashlib.sha256(await audio.body()).digest()==hashlib.sha256(SOURCES[index].read_bytes()).digest(), 'Audio belongs to another input'
    await page.get_by_role('button',name='再生',exact=True).click()
    await expect(page.get_by_role('button',name='一時停止',exact=True)).to_be_visible(timeout=15000)
    await page.get_by_role('button',name='一時停止',exact=True).click()
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'), 'Horizontal overflow'
    await page.screenshot(path=str(OUT/f'{index}-editor-sanitized.png'),full_page=True)
    async with page.expect_download() as event:
        await page.get_by_role('link',name='ZIP出力').click()
    download=await event.value
    path=await download.path()
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for suffix in ('txt','csv','srt','json'):
            payload=z.read('文字起こし.'+suffix).decode('utf-8-sig')
            assert marker in payload and other_marker not in payload, 'Export edit isolation failed'
    # Save/reload checks persisted edits rather than React local state.
    await page.reload(wait_until='networkidle')
    await page.get_by_role('button',name='編集する',exact=True).click()
    await expect(page.get_by_label('発言1のテキスト',exact=True)).to_have_value(marker+'_0')
    return count

async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    assert SOURCES[0].read_bytes()!=SOURCES[1].read_bytes(), 'Inputs must be distinct'
    jobs=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        contexts=[await browser.new_context(viewport={'width':1440,'height':1000}),
                  await browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=1)]
        clients=await asyncio.gather(*(client(c,i) for i,c in enumerate(contexts)))
        cookies=await asyncio.gather(*(c.cookies() for c in contexts))
        assert next(x['value'] for x in cookies[0] if x['name']=='beta_session')!=next(x['value'] for x in cookies[1] if x['name']=='beta_session')
        try:
            async def register(i):
                j=await upload(clients[i][0],SOURCES[i]);jobs.append((i,j));return j
            ids=await asyncio.gather(register(0),register(1))
            assert ids[0]!=ids[1]
            states=await asyncio.gather(*(wait_gpu(c,j) for c,j in zip(contexts,ids)))
            for i,c in enumerate(contexts):
                listing=await (await api(c,'GET','/api/jobs')).json()
                assert {j['id'] for j in listing['jobs']}=={ids[i]}
                csrf=clients[i][1]
                other='/api/jobs/'+ids[1-i]
                for suffix in ('','/audio','/rows','/review','/download'):
                    await api(c,'GET',other+suffix,404)
                await api(c,'PUT',other+'/rows',404,headers={'X-CSRF':csrf},data={'rows':[]})
                await api(c,'DELETE',other,404,headers={'X-CSRF':csrf})
            counts=await asyncio.gather(*(edit_download(clients[i][0],c,ids[i],i,f'KIROKU_BROWSER_{1-i}_EDIT') for i,c in enumerate(contexts)))
            for i,j in jobs:
                page,csrf,errors=clients[i]
                assert not errors,'React browser exception'
                await page.get_by_role('button',name='ワークスペースに戻る').click()
                page.once('dialog',lambda dialog:dialog.accept())
                await page.get_by_role('button',name='録音と結果を削除',exact=True).click()
                await expect(page.get_by_text('まだファイルがありません',exact=True)).to_be_visible()
                for suffix in ('','/audio','/rows','/download'):
                    await api(contexts[i],'GET','/api/jobs/'+j+suffix,404)
            result={'pass':True,'real_gpu_jobs':2,'independent_browser_contexts':2,'physical_devices':0,
                    'viewports':['1440x1000','390x844'],'utterance_counts':counts,
                    'elapsed_seconds':round(time.monotonic()-start,3),
                    'pipeline_seconds':[s.get('pipeline_seconds') for s in states],
                    'gpu_task_seconds':[s.get('gpu_task_seconds') for s in states],
                    'audio_duration_seconds':[s.get('duration') for s in states]}
            (OUT/'summary.json').write_text(json.dumps(result,indent=2))
            print('KIROKU_ANONYMOUS_BROWSER_LIVE_PASS '+json.dumps(result))
        finally:
            for i,j in jobs:
                try: await api(contexts[i],'DELETE','/api/jobs/'+j,headers={'X-CSRF':clients[i][1]})
                except Exception: pass
            await browser.close()

if __name__=='__main__': asyncio.run(main())
