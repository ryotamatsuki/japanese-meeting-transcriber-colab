# Stage 1 A10 GPU実証結果・出力品質監査（2026-10-30）

## 判定

**実GPU・文字起こし・話者分離・統合・キャッシュの実行およびファイル構造はPASS。ただし2話者音声を1話者と推定する品質上の不具合がある。L4でのTest 3〜6は未実施で、Stage 1の全面完了とは判定しない。**

## 証拠と保全

- GitHub Actions: https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41006199679
- Artifact: `12955558077` / `transcriber-stage1-a10-41006199679.zip`
- Artifact SHA-256: `dcdf737295bbc5da614cc75958f33af29607806e50b969a7463f951844cceb27`（GitHub APIのdigestとダウンロードZIPの独立計算が一致）
- GitHub Actions上のexpiry: 2026-11-06 05:05:31 UTC（日本時間14:05:31）
- 固定checkout SHA: `719c296daa642d5f52e853cdcb5e7753419fb9a8`
- 元の未改変Artifact、個別ファイルSHA-256マニフェスト、独立監査レポート・コードはChatGPT Library `/AI開発/日本語会議文字起こし/Stage1_A10_20261030/stage1_a10_evidence_preserved_20261030.zip` に保存。元Artifactや認識内容はGitHubへコミットしていない。

音声原典は[Wikimedia Commons「Kyoto women conversation in 1964」](https://commons.wikimedia.org/wiki/File:Kyoto_women_conversation_in_1964.ogg)（CC BY 4.0、原資料：国立国語研究所「方言録音資料シリーズ11 京都市方言」）。元ファイルSHA-256: `9f6a382ddeffc9e74d9a94954b66c6ed43ae3a3ae1d2fede03747845c2e10124`。Commonsの資料説明は20代女性2名の会話と明記。音声長34.579375秒。公開音声自体はArtifactに含まない。

## 監査結果

| Stage | GPU | pipeline（秒） | GPUメモリ観測最大 | 形式・証拠検査 |
|---|---|---:|---:|---|
| Test 3 Community-1 | NVIDIA A10G | 13.616 | 11665 MiB | PASS |
| Test 4 large-v3＋Community-1統合 | NVIDIA A10G | 13.864 | 11671 MiB | PASS |
| Test 5 話者分離OFF | NVIDIA A10 | 6.895 | 4265 MiB | PASS |
| Test 6a モデル重み再ロード・推論 | NVIDIA A10 | 10.752 → 8.978 | 11645 MiB | PASS |
| Test 6b 同一結果JSON再利用 | NVIDIA A10 | 11.085 → 0.003386 | 11646→328 MiB | PASS |

- ZIPのCRC、格納18ファイルの個別SHA-256、内部推論ZIP 7件のCRC/パス安全性を確認。
- CUDA 12.8、cuDNN 91002、CTranslate2 GPU、torch 2.9.1+cu128、faster-whisper 1.2.1、pyannote.audio 4.0.7を記録。
- ASRは13セグメント・184単語。時刻は34.58秒の音声内。統合ZIPはTXT/CSV/SRT/JSON/話者区間等を出力。
- OFFの場合、話者区間出力なし・CSVに「話者未設定」。
- 6aの2回目はHF Hubオフライン設定true、ASR/話者分離の実推論時間が正で、結果JSONキャッシュヒットなし。
- 6bの2回目はASR・話者分離結果キャッシュヒットtrue、推論省略を記録。出力ZIPは1回目とSHA-256完全一致。
- 既存Modal Volumeを使用しており、モデル初回ダウンロードを含むコールド起動費用は今回の値から推定しない。pipeline時間は請求秒数ではなく、GPUメモリはサンプル最大。

## QA-01（高優先）：2話者が1話者に統合された

- 自動人数推定の設定：`expected_speakers=0`, `min_speakers=0`, `max_speakers=0`。
- Test 3/4/6a/6bともCommunity-1の出力は6話者区間すべてが`SPEAKER_00`、推定話者数1。
- Test 4統合CSVは3発言行すべて「話者1」。**モデル推論成功・形式PASSを、話者分離精度PASSと解釈してはいけない。**
- 原音声を聞き比べたground truth発話区間はまだなく、DERなどの定量精度は未認定。

## 次の検証

1. 同一34.58秒音声に対し`--expected-speakers 2`を指定してA10で再実行し、自動推定と比較。成功しても人数固定だけで精度保証とはしない。
2. 公開可能な会議音声で、正解話者区間・短い相づちを含む品質評価を実施。
3. L4空き確保後にTest 3〜6を再実行し、機種別の再現性、メモリ、処理時間、費用を検証。

この文書はユーザーの元のワークフロー成功後に行った独立した出力監査の記録。元の実行における結果や音声、秘密情報は改変・再コミットしていない。
