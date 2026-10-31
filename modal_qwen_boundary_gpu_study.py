"""One-shot, synthetic-text-only, bounded Qwen second-pass GPU research.

This app is NOT a production endpoint and accepts no user recordings.
Run via: modal run modal_qwen_boundary_gpu_study.py
No persistent model volume or transcript artifacts. App ends on exit.
"""
import json
import modal

app = modal.App("kiroku-qwen-text-boundary-synthetic-one-shot-20261031")
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("torch==2.7.1", "transformers==4.57.1",
                      "accelerate==1.10.1", "safetensors==0.6.2")
         .add_local_python_source("scripts"))


@app.function(image=image, gpu="A10", cpu=2, memory=12288,
              timeout=600, retries=0, max_containers=1,
              single_use_containers=True)
def run_synthetic():
    import time
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from scripts.qwen_text_boundary_postprocess import MODEL, run_second_pass

    started = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, torch_dtype=torch.bfloat16, device_map="auto", trust_remote_code=False)
    model.eval()
    loaded_seconds = time.monotonic() - started

    def row(a, b, who, content):
        return {"start": a, "end": b, "speaker": who, "text": content}

    cases = [
        ("fragment_1", [row(0, 1, "話者1", "今回の事業については、"),
                         row(1.1, 2.5, "話者1", "来年度から開始します。")], [0]),
        ("fragment_2", [row(0, 1, "話者1", "予算は1億2,345万円を"),
                         row(1.1, 2.3, "話者1", "予定しています。")], [0]),
        ("different_speaker", [row(0, 1, "話者1", "事業については"),
                               row(1.1, 2, "話者2", "来年度からです。")], []),
        ("backchannel", [row(0, .3, "話者1", "はい。"),
                         row(.7, 1.8, "話者1", "次は予算です。")], []),
        ("completed_sentence", [row(0, 1, "話者1", "終了しました。"),
                                row(2, 3, "話者1", "次に進みます。")], []),
        ("long_pause", [row(0, 1, "話者1", "資料を"),
                        row(5, 6, "話者1", "確認します")], []),
        ("overlap", [row(0, 3, "話者1", "その件について説明します"),
                     row(2, 4, "話者1", "承知しています")], []),
        ("different_speaker_interruption",
         [row(0, .7, "話者1", "県の計画は"),
          row(.8, 1.3, "話者2", "はい"),
          row(1.4, 2.5, "話者1", "来年度からです。")], []),
        ("fragment_3",
         [row(0, .7, "話者1", "議案の説明を"),
          row(.8, 1.9, "話者1", "続けます。")], [0]),
        ("finished_immediate",
         [row(0, .7, "話者1", "確認しました。"),
          row(.8, 1.9, "話者1", "次の議題です。")], []),
        ("rapid_backchannel",
         [row(0, .2, "話者1", "はい"),
          row(.25, .6, "話者1", "はい")], []),
        ("ambiguous_continuation",
         [row(0, .9, "話者1", "次の方は"),
          row(1.0, 1.9, "話者1", "はい、こちらです。")], []),
        # Newly selected synthetic patterns were not used in earlier GPU prompt tuning.
        ("holdout_fragment_budget",
         [row(0, .8, "話者1", "来年度の財源について"),
          row(.9, 1.8, "話者1", "説明します。")], [0]),
        ("holdout_fragment_notice",
         [row(0, .8, "話者1", "対象となる県民の方へ"),
          row(.9, 1.8, "話者1", "お知らせします。")], [0]),
        ("holdout_question_without_stop",
         [row(0, .7, "話者1", "参加人数は何名でしょうか"),
          row(.8, 1.9, "話者1", "それでは次に進みます")], []),
        ("holdout_two_topics",
         [row(0, .8, "話者1", "計画は進行中です"),
          row(.9, 1.8, "話者1", "別の案件を紹介します")], []),
        ("holdout_repeated_statement",
         [row(0, .8, "話者1", "実施する予定です"),
          row(.9, 1.8, "話者1", "実施する予定です")], []),
        ("holdout_short_ack",
         [row(0, .2, "話者1", "うん"),
          row(.25, .9, "話者1", "了解しました")], []),
        # A later probe set, chosen after observing over-merging in the first
        # 18 synthetic cases. These probe examples are also development data.
        ("probe_fragment_policy",
         [row(0, .7, "話者1", "現行の制度については"),
          row(.8, 1.8, "話者1", "見直しを行います。")], [0]),
        ("probe_fragment_assembly",
         [row(0, .7, "話者1", "会議の議事録を"),
          row(.8, 1.8, "話者1", "作成してください。")], [0]),
        ("probe_topic_discontinuity",
         [row(0, .7, "話者1", "確認したい点は"),
          row(.8, 1.8, "話者1", "それでは休憩に入ります")], []),
        ("probe_new_topic",
         [row(0, .7, "話者1", "次の案件を"),
          row(.8, 1.8, "話者1", "今日はここまでにします")], []),
    ]
    output = []
    def infer(messages):
        template = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(template, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            output_ids = model.generate(**inputs, max_new_tokens=320,
                                        do_sample=False,
                                        pad_token_id=tokenizer.eos_token_id)
        return tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)

    for name, rows, expected in cases:
        t0 = time.monotonic()
        inference_calls = [0]
        def measured_infer(messages):
            inference_calls[0] += 1
            return infer(messages)
        result = run_second_pass(rows, measured_infer)
        actual = [r["source_indices"][0]
                  for r in result["rows"]
                  if len(r.get("source_indices", [])) > 1]
        # Each case includes at most one eligible join.
        output.append({"case": name, "status": result["status"],
                       "merges": result["merge_count"],
                       "expected_merges": len(expected),
                       "inference_calls": inference_calls[0],
                       "matched": (result["merge_count"] == len(expected)
                                   and (not expected or actual == expected)),
                       "seconds": round(time.monotonic() - t0, 3)})
    return {"model": MODEL, "synthetic_cases": len(cases),
            "model_load_seconds": round(loaded_seconds, 3),
            "gpu_function_seconds": round(time.monotonic()-started, 3),
            "results": output,
            "warning": "Synthetic text only. No audio, human truth or quality acceptance."}


@app.local_entrypoint()
def main():
    result = run_synthetic.remote()
    # Synthetic case IDs, numeric-only results; no raw text, audio or token.
    print("QWEN_BOUNDARY_SYNTHETIC_GPU_RESULTS " +
          json.dumps(result, ensure_ascii=False, sort_keys=True))
