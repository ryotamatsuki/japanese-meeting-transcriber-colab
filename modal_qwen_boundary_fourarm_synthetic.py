"""One-shot A10 FOUR-ARM experiment on explicitly synthetic text+waveform.

This does NOT use human-recorded speech or J-CRe3 annotations.
No deployment or persistent endpoint. Numeric-only logs.
"""
import json
import modal

app = modal.App("kiroku-qwen-fourarm-synthetic-probe-20261031")
image=(modal.Image.debian_slim(python_version="3.11")
       .pip_install("torch==2.7.1","transformers==4.57.1",
                    "accelerate==1.10.1","safetensors==0.6.2")
       .add_local_python_source("scripts"))


@app.function(image=image,gpu="A10",cpu=2,memory=12288,
              timeout=600,max_containers=1,retries=0,
              single_use_containers=True)
def study():
    import time
    from array import array
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from scripts.qwen_boundary_fourarm import (
        MODEL,audio_features,evaluate_four_arms,score_four_arms)
    start=time.perf_counter()
    tokenizer=AutoTokenizer.from_pretrained(MODEL,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(
        MODEL,torch_dtype=torch.bfloat16,device_map="auto",trust_remote_code=False)
    model.eval()
    load_sec=time.perf_counter()-start

    # Human-designed synthetic diagnostic labels, not held-out human recordings.
    specs=[
      ("join_budget","来年度の予算については、","説明を続けます。","merge",.08),
      ("join_project","今回の取組を","開始します。","merge",.11),
      ("join_material","資料の内容に","沿って進めます。","merge",.14),
      ("join_participants","参加者の皆様へ","ご案内します。","merge",.09),
      ("join_report","事業報告書を","提出します。","merge",.06),
      ("join_financial","1億2,300万円を","計上します。","merge",.10),
      ("keep_topic","確認したい点は","それでは休憩に入ります。","keep",.18),
      ("keep_next","次の事項については","本日の会議を終了します。","keep",.22),
      ("keep_repair","今の説明は","すみません、別の案件です。","keep",.15),
      ("keep_abandon","来年度の計画については","いや、次の議題に移ります。","keep",.29),
      ("keep_restart","質問を一つ","そうですね、後ほど回答します。","keep",.12),
      ("keep_misleading","資料を","えっと、会議を閉会します。","keep",.25),
      ("keep_short","今回は","その件は取り下げます。","keep",.07),
      ("keep_independent","今後の検討は","それでは本日のまとめです。","keep",.36),
      ("keep_question","お伺いしたいのは","はい。次の件に進めます。","keep",.20),
      ("keep_nogap","確認したい事項は","報告は以上です。","keep",.03),
    ]

    def invoke(arm,messages):
        text=tokenizer.apply_chat_template(
            messages,tokenize=False,add_generation_prompt=True)
        inp=tokenizer(text,return_tensors="pt").to(model.device)
        with torch.inference_mode():
            ids=model.generate(**inp,max_new_tokens=110,do_sample=False,
                               pad_token_id=tokenizer.eos_token_id)
        return tokenizer.decode(ids[0][inp["input_ids"].shape[-1]:],
                                skip_special_tokens=True)

    out=[]
    for name,left,right,label,gap in specs:
        # This is a deliberately artificial waveform with no human prosody.
        # The only meaningful acoustic observation here is the programmed gap.
        sample_rate=16000
        a_end=1.0
        b_start=a_end+gap
        b_end=b_start+1.0
        signal=array("f",[0.0])*int((b_end+.2)*sample_rate)
        for j in range(0,int(.98*sample_rate)):
            signal[j]=.03
        for j in range(int(b_start*sample_rate),int(b_end*sample_rate)):
            signal[j]=.025
        rows=[{"start":0.0,"end":a_end,"speaker":"話者1","text":left},
              {"start":round(b_start,3),"end":round(b_end,3),
               "speaker":"話者1","text":right}]
        feats=audio_features(signal,sample_rate,rows,[0])
        result=evaluate_four_arms(rows,invoke,features=feats)
        metrics=score_four_arms(result,{"0":label})
        out.append({"id":name,"label":label,
                    "candidates":len(result["candidates"]),
                    "decisions":{arm:result["decisions"][arm].get("0","unavailable")
                                 for arm in result["decisions"]},
                    "counts":{arm:{k:metrics[arm][k] for k in
                              ("true_merges","false_merges","missed_merges","holds")}
                              for arm in metrics}})
    aggregates={}
    for arm in ("baseline","rules","text_qwen","audio_qwen"):
        aggregates[arm]={key:sum(x["counts"][arm][key] for x in out)
                          for key in ("true_merges","false_merges","missed_merges","holds")}
    return {"kind":"SYNTHETIC_ONLY","model":MODEL,"total_patterns":len(specs),
            "model_load_sec":round(load_sec,3),
            "gpu_function_sec":round(time.perf_counter()-start,3),
            "aggregate":aggregates,"patterns":out,
            "warning":"Not real audio, not J-CRe3, not independent, no production accuracy claim."}


@app.local_entrypoint()
def main():
    result=study.remote()
    print("FOUR_ARM_QWEN_SYNTHETIC " + json.dumps(result,sort_keys=True))
