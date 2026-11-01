"""Re-acquire exactly the previous J-CRe3 three audio previews via normal Box UI.

Publicly documented CC BY-SA 4.0 and the folder password are used.
Every audio/reference byte must match the previously pinned SHA256.
No audio or transcripts go to git or GitHub Actions artifacts/logs.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
import zipfile
from playwright.async_api import async_playwright

SHARE="25vjhsccliimse0q74z35nv8j5bz31is"
SOURCE="https://raw.githubusercontent.com/riken-grp/J-CRe3/"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_reference(record,revision):
    url=SOURCE+revision+"/"+record["reference_path"]
    with urlopen(Request(url,headers={"User-Agent":"KirokuBoundaryResearch/1.0"}),timeout=25) as r:
        data=r.read(1024*1024+1)
    if digest(data)!=record["reference_sha256"]:
        raise ValueError("Human reference SHA changed")
    return data


async def reacquire(manifest, dest):
    records=manifest["records"]
    if (manifest["license"]!="CC BY-SA 4.0" or len(records)!=3 or
        any(not r["box_file_url"].startswith("https://riken-share.ent.box.com/s/"+SHARE+"/file/")
            for r in records)):
        raise ValueError("Unexpected official pinned corpus")
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        ctx=await browser.new_context(accept_downloads=False)
        page=await ctx.new_page()
        # Box root login is the normal, documented password page.
        await page.goto("https://riken-share.box.com/s/"+SHARE,
                        wait_until="domcontentloaded",timeout=35000)
        await page.wait_for_timeout(1200)
        passwd=page.locator('input[type="password"]')
        if await passwd.count():
            await passwd.first.fill("riken-grp")
            submit=page.locator('button[type="submit"],input[type="submit"]').first
            if await submit.count():
                await submit.click(timeout=12000)
            else:
                await passwd.first.press("Enter")
            await page.wait_for_timeout(3000)
        audio_parts=[]
        for record in records:
            captured=[]
            pending=[]
            async def receive(response):
                try:
                    ctype=response.headers.get("content-type","").lower()
                    if (response.status not in (200,206) or
                            not ctype.startswith(("audio/mp3","audio/mpeg")) or
                            not response.url.startswith("https://") or
                            "boxcloud.com/" not in response.url):
                        return
                    content=await response.body()
                    if 10000<len(content)<=8*1024*1024:
                        captured.append(content)
                except Exception:
                    return
            def listener(response):
                task=asyncio.create_task(receive(response))
                pending.append(task)
            page.on("response",listener)
            await page.goto(record["box_file_url"],wait_until="domcontentloaded",
                            timeout=35000)
            await page.wait_for_timeout(2500)
            if not any(digest(b)==record["audio_sha256"] for b in captured):
                play=page.locator('[aria-label*="Play"],button[title*="Play"],audio')
                if await play.count():
                    try:
                        await play.first.click(timeout=2500)
                        await page.wait_for_timeout(2000)
                    except Exception:
                        pass
            if pending:
                await asyncio.gather(*pending,return_exceptions=True)
            page.remove_listener("response",listener)
            good=[v for v in captured if digest(v)==record["audio_sha256"]]
            if not good:
                raise ValueError("Box preview audio not complete or SHA mismatch: "+record["id"])
            audio_parts.append(good[0])
        await browser.close()
    references=[read_reference(r,manifest["revision"]) for r in records]
    dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        archive.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False))
        archive.writestr("ATTRIBUTION.txt",
                         "J-CRe3 (Ueda et al., LREC-COLING 2024), CC BY-SA 4.0. "
                         "Official Box preview MP3; original WAV not obtained.")
        for record,audio,ref in zip(records,audio_parts,references):
            archive.writestr(record["id"]+"/preview.mp3",audio)
            archive.writestr(record["id"]+"/reference.txt",ref)
    return {"recordings":len(records),
            "verified_audio_files":len(audio_parts),
            "verified_reference_files":len(references),
            "package_bytes":dest.stat().st_size,
            "package_sha256":digest(dest.read_bytes())}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding="utf-8"))
    info=asyncio.run(reacquire(manifest,args.out))
    print("JCRE3_REACQUIRED_VERIFIED "+json.dumps(info,sort_keys=True))


if __name__=="__main__":
    main()
