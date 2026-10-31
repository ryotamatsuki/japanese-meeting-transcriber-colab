"""Temporary, fixed-public-corpus intake. No retrieval or GPU invocation route."""
import hashlib
from pathlib import Path


def create_intake(volume, root, expected_sha, expected_size):
    from fastapi import FastAPI, Request, HTTPException
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)

    from fastapi.responses import HTMLResponse

    @app.get('/',response_class=HTMLResponse)
    def landing():
        return """<!doctype html><html lang="ja"><meta charset="utf-8"><title>評価入力受付</title>
        <h1>評価入力受付</h1><p>今回の評価用パッケージを選択してください。</p>
        <form><input type="file" accept=".zip" required aria-label="評価パッケージ"><button>送信</button></form>
        <p role="status"></p><script>document.querySelector('form').onsubmit=async e=>{
        e.preventDefault();const file=document.querySelector('input').files[0];
        const status=document.querySelector('[role=status]');status.textContent='送信中';
        try{const response=await fetch('/ingest',{method:'PUT',body:file});
        status.textContent=response.ok?'受付完了':'受付できませんでした';}
        catch(e){status.textContent='接続できませんでした';}};</script></html>"""

    @app.put('/ingest')
    async def ingest(request: Request):
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>expected_size:
                raise HTTPException(413,'Unexpected input size')
            chunks.append(chunk)
        data=b''.join(chunks)
        if size!=expected_size or hashlib.sha256(data).hexdigest()!=expected_sha:
            raise HTTPException(422,'Unexpected corpus identity')
        target=Path(root)/'eval.zip'
        target.parent.mkdir(parents=True,exist_ok=True)
        # One HTTP input per container; same fixed bytes are idempotent.
        target.write_bytes(data)
        volume.commit()
        return {'accepted':True,'bytes':size,'sha256':expected_sha}

    return app
