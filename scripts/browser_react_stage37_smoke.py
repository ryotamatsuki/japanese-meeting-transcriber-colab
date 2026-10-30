"""Browser smoke test for Stage37 built React frontend, using synthetic fixtures only."""
from __future__ import annotations
import json
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
            assert desktop.locator("textarea").count()>0
            desktop.screenshot(path=str(OUT/"editor.png"),full_page=True)
            desktop.get_by_label("発言1のテキスト").fill("UIテストのための編集です。")
            desktop.get_by_text("未保存",exact=True).wait_for()
            assert desktop.get_by_role("button",name="ZIP出力").is_disabled()
            desktop.get_by_role("button",name="保存する").click()
            desktop.get_by_text("保存済み",exact=True).wait_for()
            assert desktop.get_by_role("link",name="ZIP出力").count()==1
            desktop.get_by_label("発言を検索").fill("存在しない文字列")
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
            assert not mobile_errors,mobile_errors
            browser.close()
    finally: http.shutdown()
    print("STAGE37_REACT_BROWSER_DESKTOP_MOBILE_AND_EDITOR_PASS")
    print("STAGE37_PREVIEW_FIXTURES_ARE_SYNTHETIC_NOT_REAL_TRANSCRIPT_DATA")

if __name__=="__main__":main()
