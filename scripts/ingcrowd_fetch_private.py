"""Acquire ONLY preselected CC BY-NC 4.0 data for transient noncommercial evaluation.

The ZIP is exclusively for a dedicated private Modal volume. No source WAV,
human EAF, or actual transcripts are attached to GitHub Actions artifacts.
"""
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from huggingface_hub import HfApi,hf_hub_download
from scripts.ingcrowd_eaf_reference import (
    ALLOWED_IDS,EXPECTED_LICENSE,load_ingcrowd_eaf)
import soundfile as sf

DATASET="IngCrowd/japanese-themed-dialogue"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--purpose",choices=["noncommercial-research"],required=True)
    opt=p.parse_args()
    info=HfApi().dataset_info(DATASET)
    license_data=info.card_data.license if info.card_data else None
    if license_data!=EXPECTED_LICENSE:
        raise ValueError("Dataset terms changed; cannot continue research download")
    if not info.sha or len(info.sha)!=40:
        raise ValueError("Dataset revision must be a pinned commit")
    rows=[]
    with ZipFile(opt.out,"w",compression=ZIP_DEFLATED,compresslevel=1) as z:
        for rid in ALLOWED_IDS:
            base=rid+"/"+rid
            paths={}
            for typ,suffix in (("audio","_audio.wav"),("reference",".eaf")):
                file=f"{base}{suffix}"
                pth=Path(hf_hub_download(DATASET,file,revision=info.sha,
                                         repo_type="dataset"))
                n=pth.stat().st_size
                if not 100 < n <= (30*1024*1024 if typ=="audio" else 2*1024*1024):
                    raise ValueError("Unexpected source file length")
                paths[typ]=(file,pth,hashlib.sha256(pth.read_bytes()).hexdigest())
            info_wav=sf.info(paths["audio"][1])
            if (info_wav.samplerate!=16000 or info_wav.channels!=1 or
                not 120<=info_wav.duration<=900):
                raise ValueError("Dataset is no longer 16k mono conversational WAV")
            eaf=paths["reference"][1].read_bytes()
            ref,meta=load_ingcrowd_eaf(eaf,duration=info_wav.duration)
            for k,(name,path,_) in paths.items():
                z.write(path,name)
            rows.append({"id":rid,"audio_sha256":paths["audio"][2],
                         "reference_sha256":paths["reference"][2],
                         "duration_seconds":round(info_wav.duration,3),
                         "eaf_rows":meta["turns"],
                         "has_overlap":meta["has_overlap"]})
        z.writestr("manifest.json",json.dumps({
            "dataset":DATASET,"revision":info.sha,"license":EXPECTED_LICENSE,
            "use":"noncommercial_research_only",
            "records":rows},ensure_ascii=False))
    if opt.out.stat().st_size>100*1024*1024:
        opt.out.unlink(missing_ok=True)
        raise ValueError("Source package larger than experiment budget")
    print("NONCOMMERCIAL_SOURCE_VERIFIED",json.dumps({
        "dataset":DATASET,"revision":info.sha,
        "record_count":len(rows),
        "total_audio_seconds":round(sum(r["duration_seconds"] for r in rows),3),
        "turn_counts":[r["eaf_rows"] for r in rows],
        "source_SHA256_checked":True
    }))

if __name__=="__main__":main()
