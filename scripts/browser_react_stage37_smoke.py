"""Browser smoke test for Stage37 built React frontend, using synthetic fixtures only."""
from __future__ import annotations
import json
import io
import wave
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1] / "beta" / "react_dist"
OUT = Path(os.environ.get("REACT_PREVIEW_DIR", "local_runs/react_preview"))
OUT.mkdir(parents=True,exist_ok=True)
id_a="a"*32
id_b="b"*32
JOBS=[
    dict(id=id_a,filename="プロジェクト定例会議_サンプル.wav",status="complete",
         received=1234000,expected_size=1234000,duration=1803,speakers=3,created=1793398000,utterances=70),
    dict(id=id_b,filename="振り返りミーティング_サンプル.wav",status="complete",
         received=400000,expected_size=400000,duration=1250,speakers=2,created=1793387000,utterances=48),
]
SAMPLES=[
    "本日のミーティングでは、今月の進捗状況と次のアクションについて確認していきます。",
    "ありがとうございます。まず、各担当の作業状況について順番に共有していただけますか。",
    "はい。今週の対応事項はおおむね完了しました。来週に向けた準備も進めています。",
    "それでは、今後のスケジュールを確認し、必要な調整事項を整理しましょう。",
]
ROWS=[dict(start=i*13.5,end=i*13.5+12,speaker=("話者A","話者B","話者C")[i%3],
           text=SAMPLES[i%4]) for i in range(70)]

# Synthetic PCM fixture only: exercise real HTMLMediaElement metadata and rate.
_audio=io.BytesIO()
with wave.open(_audio,'wb') as _wav:
    _wav.setnchannels(1);_wav.setsampwidth(2);_wav.setframerate(16000)
    _wav.writeframes(b'\x00\x00'*32000)
SILENCE_WAV=_audio.getvalue()

class MockBackend(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def json(self,obj):
        body=json.dumps(obj,ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_PUT(self): self.json(dict(rows=ROWS))
    def do_GET(self):
        path=self.path.split("?")[0]
        if path=="/api/session":
            return self.json(dict(csrf="synthetic-preview",limits=dict(file_bytes=188743680,duration_seconds=3600,gpu_jobs_24h=4)))
        if path=="/api/jobs":return self.json(dict(jobs=JOBS))
        if path=="/api/jobs/"+id_a:return self.json(JOBS[0])
        if path=="/api/jobs/"+id_b:return self.json(JOBS[1])
        if path in ("/api/jobs/"+id_a+"/audio","/api/jobs/"+id_b+"/audio"):
            self.send_response(200)
            self.send_header("Content-Type","audio/wav")
            self.send_header("Content-Length",str(len(SILENCE_WAV)))
            self.end_headers();self.wfile.write(SILENCE_WAV)
            return
        if path.endswith("/rows"):return self.json(dict(rows=ROWS))
        if path.endswith("/review"):
            return self.json(dict(available=True,total_candidates=2,
              windows=[dict(id="w1",start=80,end=92),dict(id="w2",start=190,end=205)],reviewed_ids=[]))
        if path=="/": target=ROOT/"index.html"
        elif path.startswith("/ui/assets/"):target=ROOT/path.removeprefix("/ui/")
        else:return self.send_error(404)
        if not target.is_file():return self.send_error(404)
        data=target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",mimetypes.guess_type(target)[0] or "application/octet-stream")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

def main():
    assert (ROOT/"index.html").is_file(),"Build the React UI before browser smoke"
    http=ThreadingHTTPServer(("127.0.0.1",0),MockBackend)
    thread=threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    url="http://127.0.0.1:"+str(http.server_port)+"/"
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            desktop=browser.new_page(viewport={"width":1440,"height":900},device_scale_factor=1)
            errors=[]
            desktop.on("pageerror",lambda error:errors.append(str(error)))
            desktop.goto(url,wait_until="networkidle")
            desktop.get_by_text("会議の記録を、もっとスマートに。").wait_for()
            desktop.get_by_text("プロジェクト定例会議_サンプル.wav").first.wait_for()
            desktop.screenshot(path=str(OUT/"dashboard.png"),full_page=True)
            desktop.get_by_role("button",name="編集する").first.click()
            desktop.get_by_role("heading",name="文字起こし",exact=True).wait_for()
            desktop.wait_for_function("() => document.querySelector('audio')?.readyState >= 1")
            desktop.get_by_label("再生速度").select_option("1.5")
            assert desktop.locator("audio").evaluate("e => e.playbackRate")==1.5
            for job_id,filename in ((id_b,JOBS[1]['filename']),(id_a,JOBS[0]['filename'])):
                desktop.locator(".side-item").filter(has_text=filename).click()
                desktop.wait_for_function("id => {const a=document.querySelector('audio');"
                    "return a && a.src.includes(id) && a.readyState>=1}",arg=job_id)
                assert desktop.get_by_label("再生速度").input_value()=="1.5"
                assert desktop.locator("audio").evaluate("e => e.playbackRate")==1.5, \
                    "Selected playback speed must survive a job switch"
            print("PLAYBACK_RATE_JOB_SWITCH_PASS")
            # Stub only the OS clipboard; keep the actual React copy handler.
            desktop.evaluate("""() => {
                window.__lastCopiedTranscript = '';
                Object.defineProperty(navigator, 'clipboard', {configurable: true,
                    value: {writeText: async text => {window.__lastCopiedTranscript = text}}});
            }""")
            assert desktop.locator("textarea").count()>0
            assert desktop.locator(".audio-dock").evaluate(
                "(element) => {const b=element.getBoundingClientRect();"
                "return getComputedStyle(element).position==='fixed'"
                " && b.top>=0 && b.bottom<=window.innerHeight}"
            ),"Studio audio player must remain fixed and visible"
            desktop.screenshot(path=str(OUT/"editor.png"),full_page=False)
            # Studio tabs show only outstanding overlap candidates; no false claim
            # that every ordinary row has been human-reviewed.
            assert desktop.get_by_role("button",name="3秒戻る").count()==1
            desktop.locator(".studio-tabs button").nth(1).click()
            assert desktop.locator(".transcript-item").count()>0
            assert desktop.locator(".transcript-item").count()<70
            desktop.locator(".studio-tabs button").nth(0).click()
            assert desktop.locator(".transcript-item").count()==60
            # Speaker renaming is a bulk edit, not a per-row visual label.
            desktop.once("dialog",lambda dialog:dialog.accept("司会者"))
            desktop.get_by_role("button",name="話者Aを一括変更").click()
            assert desktop.get_by_label("発言1の話者名").input_value()=="司会者"
            desktop.get_by_label("発言1のテキスト").fill("UIテストのための編集です。")
            desktop.get_by_text("未保存",exact=True).wait_for()
            assert desktop.get_by_role("button",name="ZIP出力").is_disabled()
            desktop.get_by_role("button",name="保存する").click()
            desktop.get_by_text("保存済み",exact=True).wait_for()
            assert desktop.get_by_role("link",name="ZIP出力").count()==1
            # One-tap default: whole transcript with speaker labels and no times.
            desktop.get_by_role("button",name="全文コピー").click()
            copied=desktop.evaluate("window.__lastCopiedTranscript")
            assert copied.startswith("司会者：UIテストのための編集です。"),copied[:100]
            assert copied.count("\n\n")==69,"Copy must include all 70 rows, not only current page"
            desktop.get_by_label("コピー形式").select_option("plain")
            desktop.get_by_role("button",name="全文コピー").click()
            copied=desktop.evaluate("window.__lastCopiedTranscript")
            assert copied.startswith("UIテストのための編集です。")
            assert "司会者：" not in copied
            desktop.get_by_label("コピー形式").select_option("timed")
            desktop.get_by_role("button",name="全文コピー").click()
            assert desktop.evaluate("window.__lastCopiedTranscript").startswith("[00:00:00] 司会者：")
            desktop.get_by_label("発言を検索").fill("存在しない文字列")
            desktop.get_by_role("button",name="全文コピー").click()
            assert desktop.evaluate("window.__lastCopiedTranscript").count("\n\n")==69
            # Clipboard-denied path remains usable with a selectable textarea.
            desktop.evaluate("""() => {navigator.clipboard.writeText = async () => {
                throw Error('clipboard blocked in browser smoke');
            }}""")
            desktop.get_by_role("button",name="全文コピー").click()
            desktop.get_by_role("dialog",name="テキストを手動でコピー").wait_for()
            assert desktop.get_by_label("コピー用の全文テキスト").input_value().startswith("[00:00:00] 司会者：")
            desktop.get_by_role("button",name="コピー画面を閉じる").click()
            desktop.get_by_text("一致する発言がありません").wait_for()
            assert not errors,errors
            mobile=browser.new_page(viewport={"width":390,"height":844},device_scale_factor=1)
            mobile_errors=[]
            mobile.on("pageerror",lambda error:mobile_errors.append(str(error)))
            mobile.goto(url,wait_until="networkidle")
            mobile.get_by_text("会議の記録を、もっとスマートに。").wait_for()
            mobile.screenshot(path=str(OUT/"mobile.png"),full_page=True)
            mobile.get_by_role("button",name="メニューを開く").click()
            mobile.get_by_role("button",name="ログアウト").wait_for()
            mobile.get_by_role("button",name="メニューを閉じる").click()
            mobile.get_by_role("button",name="編集する").first.click()
            mobile.get_by_role("heading",name="文字起こし",exact=True).wait_for()
            mobile.evaluate("""() => {
                window.__lastCopiedTranscript = '';
                Object.defineProperty(navigator, 'clipboard', {configurable: true,
                    value: {writeText: async text => {window.__lastCopiedTranscript = text}}});
            }""")
            assert mobile.get_by_role("button",name="全文コピー").is_visible()
            mobile.get_by_label("コピー形式").select_option("plain")
            mobile.get_by_role("button",name="全文コピー").click()
            assert mobile.evaluate("window.__lastCopiedTranscript").startswith(SAMPLES[0])
            assert mobile.locator(".audio-dock").is_visible()
            mobile.screenshot(path=str(OUT/"studio_mobile.png"),full_page=False)
            assert not mobile_errors,mobile_errors
            browser.close()
    finally: http.shutdown()
    print("STAGE37_REACT_BROWSER_DESKTOP_MOBILE_AND_EDITOR_PASS")
    print("STAGE37_PREVIEW_FIXTURES_ARE_SYNTHETIC_NOT_REAL_TRANSCRIPT_DATA")

if __name__=="__main__":main()
