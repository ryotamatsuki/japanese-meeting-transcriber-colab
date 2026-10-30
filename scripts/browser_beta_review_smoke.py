"""Headless Chromium interaction test for the private-beta overlap review UI.

The local server uses generated non-sensitive WAV audio and fake review metadata;
it never calls Modal, Hugging Face, or any real recording service.
"""
from __future__ import annotations
import io
import json
import socket
import tempfile
import threading
import time
import wave
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

from beta.backend import FileBackend
from beta.server import create_app


def synthetic_wave():
    with io.BytesIO() as stream:
        with wave.open(stream,'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b'\x00\x00'*16000*4)
        return stream.getvalue()


def main():
    with tempfile.TemporaryDirectory() as directory:
        state={}
        backend=FileBackend(directory,state,launch=lambda *args:None,probe=lambda p:4)
        audio=synthetic_wave()
        job=backend.new_job('synthetic-public.wav',len(audio),True,2)
        backend.append_chunk(job['id'],0,audio)
        backend.finish(job['id'])
        state['job:'+job['id']]={**state['job:'+job['id']],'status':'complete'}
        folder=Path(directory)/job['id']
        (folder/'results.json').write_text(json.dumps([
            {'start':0.2,'end':1.6,'speaker':'話者1','text':'これはテストです。'},
            {'start':1.5,'end':3.0,'speaker':'話者2','text':'はい。'}],ensure_ascii=False))
        (folder/'review_candidates.json').write_text(json.dumps({
            'available':True,'total_candidates':2,
            'windows':[{'id':'ov-00000','start':1.4,'end':1.9,'speaker_count':2},
                       {'id':'ov-00001','start':2.5,'end':2.9,'speaker_count':2}],
            'warning':'Synthetic test candidates'}))
        pw='integration-only-password-123'
        app=create_app(backend,password=pw,session_secret='integration-signed-secret-0123456789abcdef')
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        config=uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error')
        server=uvicorn.Server(config)
        thread=threading.Thread(target=server.run,daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        assert server.started,'Local ASGI server did not start'
        try:
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True)
                context=browser.new_context(ignore_https_errors=True)
                page=context.new_page()
                errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://localhost:{port}/login')
                page.locator('input[name=password]').fill(pw)
                page.get_by_role('button',name='ログイン').click()
                page.wait_for_url(f'http://localhost:{port}/')
                page.get_by_role('button',name='編集する').click()
                review=page.locator('#overlapReview')
                review.wait_for(state='visible')
                assert review.locator('.overlap-candidate').count()==2
                assert '要確認 2区間 / 確認済み 0区間' in page.locator('#overlapSummary').inner_text()
                check=review.locator('input[type=checkbox]').first
                check.check()
                page.wait_for_function("document.querySelector('#overlapSummary').innerText.includes('確認済み 1区間')")
                assert check.is_checked()
                page.reload()
                page.get_by_role('button',name='編集する').click()
                page.locator('#overlapReview').wait_for(state='visible')
                check=page.locator('#overlapReview input[type=checkbox]').first
                assert check.is_checked(),'Review checked state did not survive browser reload'
                page.locator('.overlap-candidate').first.get_by_role('button',name='発言行へ').click()
                page.wait_for_function("document.activeElement?.getAttribute('aria-label')==='発話テキスト'")
                field=page.locator('.utterance textarea').first
                field.fill('ブラウザで修正しました。')
                page.get_by_role('button',name='修正を保存').click()
                page.wait_for_function("document.querySelector('#editstatus').innerText.includes('保存しました')")
                check.uncheck()
                page.wait_for_function("document.querySelector('#overlapSummary').innerText.includes('確認済み 0区間')")
                page.reload()
                page.get_by_role('button',name='編集する').click()
                page.locator('#overlapReview').wait_for(state='visible')
                assert not page.locator('#overlapReview input[type=checkbox]').first.is_checked()
                assert page.locator('.utterance textarea').first.input_value()=='ブラウザで修正しました。'
                assert not errors,'Browser JavaScript errors: '+repr(errors)
                print('BETA_BROWSER_OVERLAP_REVIEW_PASS: login, review visibility, mark, persistence, text edit and re-open')
                browser.close()
        finally:
            server.should_exit=True
            thread.join(timeout=6)


if __name__=='__main__':
    main()
