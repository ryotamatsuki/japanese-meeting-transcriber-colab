"""Bounded public-source diagnostic for the existing J-CRe3 pilot.

Only test the previously cited official Box shared file and official GitHub
ELAN reference. No login bypass, no third-party mirrors, no transcripts logged.
"""
import hashlib
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

REF = ("https://raw.githubusercontent.com/riken-grp/J-CRe3/"
       "61814236abf16258c7fb9778e32e660c1602ecfa/"
       "transcriptions/20220302-56130322-0/20220302-56130322-0-hh-20220405.txt")
SHARE = "25vjhsccliimse0q74z35nv8j5bz31is"
FILE_ID = "1485152795713"
AUDIO_SHA = "f77a1ce6ae752db0977cf891c69408cdbfee56a293146f3d46b0f2a31707fcbd"
REF_SHA = "be192142f857609d870dd50d8ca361efc8ff3824db00140bd89223267a30daa2"
URLS = {
    "official_reference": REF,
    "official_box_file_page": f"https://riken-share.ent.box.com/s/{SHARE}/file/{FILE_ID}",
    "official_box_download_link": (
        "https://riken-share.ent.box.com/index.php"
        f"?rm=box_download_shared_file&shared_name={SHARE}&file_id={FILE_ID}"),
}


def probe():
    result = {}
    for key, url in URLS.items():
        entry = {}
        try:
            request = Request(url, headers={"User-Agent":"KirokuResearchValidation/1.0"})
            with urlopen(request, timeout=18) as response:
                chunk = response.read(8 * 1024 * 1024 + 1)
                entry = {"status": response.status,
                         "content_type": response.headers.get("Content-Type","").split(";")[0],
                         "bytes_read": len(chunk), "truncated": len(chunk) > 8*1024*1024,
                         "ref_sha_match": (hashlib.sha256(chunk).hexdigest()==REF_SHA if key=="official_reference" else None),
                         "audio_sha_match": (hashlib.sha256(chunk).hexdigest()==AUDIO_SHA if key!="official_reference" else None)}
        except (HTTPError, URLError, TimeoutError) as exc:
            entry = {"error_type":type(exc).__name__,
                     "status":getattr(exc,"code",None)}
        result[key] = entry

    # The official README publicly supplies a shared-link password. Inspect
    # only form field names and authorization state, never cookies/tokens.
    from html.parser import HTMLParser
    class Forms(HTMLParser):
        def __init__(self):
            super().__init__()
            self.forms = []
            self.inputs = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "form":
                self.forms.append({"method":attrs.get("method","GET"),
                                   "action_path":attrs.get("action","").split("?")[0][-100:]})
            if tag == "input":
                self.inputs.append(attrs.get("name",""))
    try:
        with urlopen(Request(URLS["official_box_file_page"],
                     headers={"User-Agent":"Mozilla/5.0"}), timeout=18) as response:
            page = response.read(200000).decode("utf-8","ignore")
        parser=Forms()
        parser.feed(page)
        result["box_login_form_diagnostic"]={
            "forms":parser.forms[:5],
            "input_names":[n for n in parser.inputs if n][:16],
            "mentions_password":("password" in page.lower()),
            "mentions_previews":("preview" in page.lower()),
            "mentions_shared_link":("shared_link" in page.lower()),
            "mentions_download":("download" in page.lower()),
        }
    except (HTTPError, URLError, TimeoutError) as exc:
        result["box_login_form_diagnostic"]={"error_type":type(exc).__name__}
    print("JCRE3_PUBLIC_ACCESS_DIAGNOSTIC " + json.dumps(result,sort_keys=True))
    return result


if __name__=="__main__":
    probe()
