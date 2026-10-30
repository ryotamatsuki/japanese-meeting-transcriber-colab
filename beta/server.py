"""Authenticated, same-origin FastAPI UI for a private single-user transcription beta."""
from __future__ import annotations
import asyncio
import html
import os
import time
import secrets
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from .backend import StoreError
from .core import make_session, verify_session, csrf_for, CHUNK_BYTES, MAX_AUDIO_BYTES

BASE = Path(__file__).parent
REACT_DIST = BASE / 'react_dist'


def create_app(backend, *, password: str, session_secret: str):
    if len(password)<16 or len(session_secret)<32:
        raise ValueError('Provide a strong BETA_PASSWORD (16+ chars) and BETA_SESSION_SECRET (32+ chars)')
    app=FastAPI(title='Meeting Transcriber Private Beta', docs_url=None,
                redoc_url=None,openapi_url=None)
    lock=asyncio.Lock()

    @app.middleware('http')
    async def headers(req, call_next):
        result=await call_next(req)
        result.headers['Cache-Control']='no-store, private'
        result.headers['Pragma']='no-cache'
        result.headers['X-Content-Type-Options']='nosniff'
        result.headers['Referrer-Policy']='no-referrer'
        result.headers['X-Frame-Options']='DENY'
        result.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
        result.headers['Content-Security-Policy']=(
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "media-src 'self' blob:; connect-src 'self'; img-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        return result

    def require_auth(req):
        tok=req.cookies.get('beta_session','')
        if not verify_session(session_secret,tok):
            raise HTTPException(401,'Authentication required')
        return tok

    def require_write(req):
        tok=require_auth(req)
        if not secrets.compare_digest(req.headers.get('X-CSRF',''),csrf_for(session_secret,tok)):
            raise HTTPException(403,'CSRF token missing or invalid')
        # Defense in depth; cookie with SameSite=Strict also enforced.
        origin=req.headers.get('origin')
        if origin:
            from urllib.parse import urlparse
            base=urlparse(str(req.base_url)); actual=urlparse(origin)
            if (base.scheme,base.netloc)!=(actual.scheme,actual.netloc):
                raise HTTPException(403,'Origin mismatch')

    def safe(fn,*args,**kwargs):
        try:
            return fn(*args,**kwargs)
        except StoreError as exc:
            raise HTTPException(exc.code,str(exc)) from None
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from None

    @app.get('/healthz')
    def health():
        return {'status':'running','public':False}

    @app.get('/login',response_class=HTMLResponse)
    def login_page():
        return HTMLResponse('''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ログイン</title></head><body style="font-family:sans-serif;max-width:400px;margin:10vh auto;padding:2rem"><h1>会議文字起こし・限定ベータ</h1><p>許可された利用者のみ利用できます。</p><form method="post" action="/login"><label>アクセス用パスワード <input type="password" name="password" autocomplete="current-password" required style="display:block;width:100%;margin:.8rem 0;padding:.6rem"></label><button type="submit">ログイン</button></form></body></html>''')

    @app.post('/login')
    async def login(req:Request):
        import urllib.parse
        ip=req.client.host if req.client else 'unknown'
        key='login_attempts:'+ip
        record=backend.state.get(key,{'count':0,'until':0})
        if record['until']<time.time():
            record={'count':0,'until':time.time()+900}
        if record['count']>=5 and time.time()<record['until']:
            raise HTTPException(429,'Too many login attempts')
        payload=await req.body()
        if len(payload)>4096:
            raise HTTPException(413,'Payload too large')
        form=urllib.parse.parse_qs(payload.decode('utf-8','replace'))
        supplied=form.get('password',[''])[0]
        if not secrets.compare_digest(supplied,password):
            backend.state[key]={'count':record['count']+1,'until':record['until']}
            raise HTTPException(401,'Invalid password')
        backend.state.pop(key,None)
        tok=make_session(session_secret)
        response=RedirectResponse('/',status_code=303)
        response.set_cookie('beta_session',tok,max_age=12*3600,httponly=True,
                            secure=True,samesite='strict',path='/')
        return response

    @app.post('/logout')
    async def logout(req:Request):
        require_write(req)
        response=JSONResponse({'ok':True})
        response.delete_cookie('beta_session',path='/')
        return response

    @app.get('/')
    def home(req:Request):
        if not verify_session(session_secret,req.cookies.get('beta_session','')):
            return RedirectResponse('/login',status_code=303)
        ui = REACT_DIST/'index.html'
        if not ui.is_file():
            ui = BASE/'site.html'  # Legacy UI retained until a production React build exists.
        return HTMLResponse(ui.read_text(encoding='utf-8'))

    @app.get('/ui/{asset_path:path}')
    def react_assets(req:Request,asset_path:str):
        # Production Vite bundle: authenticated, same-origin and CSP-compatible.
        # Do not allow an arbitrary file server or an unauthenticated static mount.
        require_auth(req)
        if not asset_path.startswith('assets/'):
            raise HTTPException(404,'Not found')
        suffix=Path(asset_path).suffix.lower()
        if suffix not in ('.js','.css','.svg','.png','.ico','.woff2'):
            raise HTTPException(404,'Not found')
        root=REACT_DIST.resolve()
        path=(root/asset_path).resolve()
        if root not in path.parents or not path.is_file():
            raise HTTPException(404,'Not found')
        import mimetypes
        return FileResponse(path,media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')

    @app.get('/assets/{name}')
    def assets(req:Request,name:str):
        require_auth(req)
        if name not in ('site.css','site.js'):
            raise HTTPException(404,'Not found')
        return FileResponse(BASE/name,media_type='text/css' if name.endswith('.css') else 'application/javascript')

    @app.get('/api/session')
    def session(req:Request):
        tok=require_auth(req)
        return {'csrf':csrf_for(session_secret,tok),'limits':{'file_bytes':MAX_AUDIO_BYTES,
            'chunk_bytes':CHUNK_BYTES,'duration_seconds':3600,'saved_jobs':2,'gpu_jobs_24h':4},
            'beta_note':'Machine output; human verification required. Do not upload confidential audio.'}

    @app.get('/api/jobs')
    def jobs(req:Request):
        require_auth(req)
        return {'jobs':safe(backend.list_jobs)}

    @app.post('/api/jobs')
    async def create(req:Request):
        require_write(req)
        body=await req.body()
        if len(body)>2048:
            raise HTTPException(413,'Payload too large')
        try:
            data=__import__('json').loads(body)
            async with lock:
                return safe(backend.new_job,data['filename'],data['size'],
                            data.get('diarization',True),data.get('speakers',0))
        except (ValueError,KeyError,TypeError):
            raise HTTPException(400,'Invalid job details') from None

    @app.put('/api/jobs/{id}/chunks')
    async def chunks(req:Request,id:str,offset:int):
        require_write(req)
        # Stream with strict limit; never materialize an arbitrary body in RAM.
        body=bytearray()
        async for part in req.stream():
            body.extend(part)
            if len(body)>CHUNK_BYTES:
                raise HTTPException(413,'Chunk exceeds 4 MiB')
        async with lock:
            return safe(backend.append_chunk,id,offset,bytes(body))

    @app.post('/api/jobs/{id}/finish')
    async def finish(req:Request,id:str):
        require_write(req)
        async with lock:
            return safe(backend.finish,id)

    @app.get('/api/jobs/{id}')
    def status(req:Request,id:str):
        require_auth(req)
        return safe(backend.info,id)

    @app.get('/api/jobs/{id}/audio')
    def audio(req:Request,id:str):
        require_auth(req)
        path=safe(backend.source,id)
        import mimetypes
        return FileResponse(path,media_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')

    @app.get('/api/jobs/{id}/rows')
    def rows(req:Request,id:str):
        require_auth(req)
        return {'rows':safe(backend.read_rows,id)}

    @app.put('/api/jobs/{id}/rows')
    async def save(req:Request,id:str):
        require_write(req)
        content=await req.body()
        if len(content)>2*1024*1024:
            raise HTTPException(413,'Edited transcript too large')
        try:
            data=__import__('json').loads(content)
            async with lock:
                return {'rows':safe(backend.save_rows,id,data['rows'])}
        except (KeyError,ValueError,TypeError):
            raise HTTPException(400,'Invalid transcript payload') from None

    @app.get('/api/jobs/{id}/review')
    def get_review(req:Request,id:str):
        require_auth(req)
        return safe(backend.review_windows,id)

    @app.put('/api/jobs/{id}/review/{window_id}')
    async def set_review(req:Request,id:str,window_id:str):
        require_write(req)
        payload=await req.body()
        if len(payload)>128:
            raise HTTPException(413,'Review update too large')
        try:
            body=__import__('json').loads(payload)
            if set(body)!={'reviewed'} or type(body['reviewed']) is not bool:
                raise ValueError('Invalid review flag')
        except (ValueError,TypeError,KeyError):
            raise HTTPException(400,'Invalid review flag') from None
        async with lock:
            return safe(backend.set_reviewed,id,window_id,body['reviewed'])

    @app.get('/api/jobs/{id}/download')
    def download(req:Request,id:str):
        require_auth(req)
        payload=safe(backend.get_download,id)
        return Response(payload,media_type='application/zip',headers={
            'Content-Disposition':'attachment; filename="transcript_edits.zip"'})

    @app.delete('/api/jobs/{id}')
    async def delete(req:Request,id:str):
        require_write(req)
        async with lock:
            safe(backend.delete,id)
        return {'ok':True}

    return app