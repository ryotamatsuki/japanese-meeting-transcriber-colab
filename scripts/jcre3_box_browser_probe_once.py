"""Official J-CRe3 Box preview accessibility probe using normal browser UI.

Official public README supplies the share link and password. This only uses the
visible password form; never bypass download restrictions. No media, login
tokens, cookies or private text are logged or archived.
"""
import asyncio
import json
import re

from playwright.async_api import async_playwright

SHARE="25vjhsccliimse0q74z35nv8j5bz31is"
FILE_ID="1485152795713"
URL=f"https://riken-share.box.com/s/{SHARE}"
FILE_URL=f"https://riken-share.ent.box.com/s/{SHARE}/file/{FILE_ID}"


async def probe():
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch(headless=True)
        context=await browser.new_context(accept_downloads=False)
        page=await context.new_page()
        events=[]
        def capture(response):
            if len(events)>=25:
                return
            mime=response.headers.get("content-type","").lower().split(";")[0]
            if "audio" in mime or "mpeg" in mime or "mp3" in response.url.lower():
                events.append({"content_type":mime,"status":response.status,
                               "hostname":response.url.split("/")[2][:100]})
        page.on("response",capture)
        out={}
        try:
            resp=await page.goto(URL,wait_until="domcontentloaded",timeout=25000)
            await page.wait_for_timeout(2500)
            out["initial_http_status"]=resp.status if resp else None
            out["visible_password_field"]=await page.locator('input[type="password"]').count()
            out["browser_title_category"]=(
                "Box" if "box" in (await page.title()).lower() else "other")
            if out["visible_password_field"]>0:
                password=page.locator('input[type="password"]').first
                await password.fill("riken-grp")
                # Use the normal password dialog's submit (not a hidden API).
                submit=page.locator('button[type="submit"],input[type="submit"]').first
                if await submit.count():
                    await submit.click(timeout=10000)
                    out["password_submitted_via_UI"]=True
                    await page.wait_for_timeout(4500)
                else:
                    await password.press("Enter")
                    out["password_submitted_via_UI"]=True
                    await page.wait_for_timeout(4500)
            else:
                out["password_submitted_via_UI"]=False
            out["password_still_visible"]=await page.locator('input[type="password"]').count()>0
            # On a normally authorized shared folder, navigate to the cited
            # file preview using the same session and browser UI.
            if not out["password_still_visible"]:
                next_response=await page.goto(FILE_URL,wait_until="domcontentloaded",timeout=25000)
                await page.wait_for_timeout(3500)
                out["file_http_status_after_folder_visit"]=(
                    next_response.status if next_response else None)
            text=(await page.locator("body").inner_text(timeout=3000)).lower()[:10000]
            out["page_indicators"]={
                "not_found":("not found" in text or "見つかりません" in text),
                "restricted":("access denied" in text or "アクセスできません" in text),
                "password":("password" in text or "パスワード" in text),
                "file_audio_wav":("audio.wav" in text),
                "preview":("preview" in text or "プレビュー" in text),
            }
            out["audio_element_count"]=await page.locator("audio,video").count()
            out["player_visible"]=await page.locator(
                '[aria-label*="Play"],[aria-label*="再生"],button[title*="Play"]').count()>0
            out["audio_responses"]=events
        except Exception as exc:
            out["failure_class"]=type(exc).__name__
        finally:
            await browser.close()
        print("JCRE3_BROWSER_UI_DIAGNOSTIC "+json.dumps(out,sort_keys=True))


if __name__=="__main__":
    asyncio.run(probe())
