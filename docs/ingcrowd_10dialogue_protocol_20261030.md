# v0.1 日本語10対話ベンチマーク評価プロトコル（2026-10-30）

## 目的
同じ一つの短い音声や字幕だけで推論性能を判断しないため、10本の独立した自然日本語対話と、**人手で付与された話者区間・逐語的発話**で評価する。60分WebアプリE2E・APIテストとは分離する。

## 出典・利用許諾

- コーパス: IngCrowd, Japanese Themed Casual Conversation Corpus: https://huggingface.co/datasets/IngCrowd/japanese-themed-dialogue
- 公開10対話（合計120分52秒）、16kHz/16bitモノラルの混合音声10本、2話者分離音声20本、各回人手ELAN `.eaf` 10本。
- **CC BY-NC 4.0**。評価実験は非商用に限定し、再配布や商用製品向けの権利を当然に認めるものではない。公開版配布と運用要件は別途ライセンス確認が必要。
- 元コーパスと人手発話、音声、推論全文をGitHubに追加しない。GitHub Actionsの結果Artifactは計測結果・ハッシュ・失敗IDだけ。
- Zoom対話という特性は会議に近いが、行政会議でも5人以上の会議でもない。10録音には話者ペアの重なりがあり、10組の独立話者という意味ではない。

## 固定モデル・設定

- 音声認識: Whisper large-v3 / faster-whisper、元ベースラインbeam=5。
- 話者分離: pyannote Community-1、**oracle `expected_speakers=2`**、個別音声で話者IDの時系列対応を決めない。
- GPU: Modal A10。CLIから独立した各混合音声を全長で実行。ASR・diar両方ON。
- 元音声は16kHz/mono、mp3 48kbpsに変換する。転送・デコードの影響があるため、原WAVとの比較可能性を記録する。
- 最初のモデルとCLI実行コード参照コミットをワークフローに固定する。

## 人手ELAN→採点

- `TIME_ORDER/TIME_SLOT` のミリ秒時刻を秒へ変換。
- `TIER_ID=speaker_1`, `speaker_2` の `ALIGNABLE_ANNOTATION` を抽出。注釈の非言語タグ `<la>` 等をCER参照から除外。
- **CER**: 参照発話を開始時刻順に連結し、モデルASR出力を連結する。NFKC, casefold、空白・句読点・記号除去後の文字単位Levenshtein距離÷参照文字数。重複発話が含まれるため、これは大まかな会議全文CERであり正規のcpCERではない。
- **DER**: `pyannote.metrics.DiarizationErrorRate`、collar=0.0秒、skip_overlap=False。各試行独立して最適なID対応。FA・Miss・Confusion別に計測。
- **JER**: `pyannote.metrics.JaccardErrorRate`、collar=0.0秒、skip_overlap=False。
- 10録音すべてのGPU・出力形式・メタデータ検証を完了したときのみ「安定性10/10 PASS」。中断・欠落・失敗が1件でもあれば未達。
- 品質目標（暫定）：CER中央値15%以下、DER中央値30%以下。ただし公式の標準化評価値ではなく、本アプリの限定ベータ目標。
- 品質ゲートと安定性ゲートを混同しない。いずれも必要。性能が高くても人手確認とデータ保護の実証は別途必要。

## 再現・出力

- `scripts/eval_elan_ja.py` は外部ELANとオリジナル推論ZIPを受け取り数値をJSONへ出力。
- `tests/test_eval_elan.py` でタグ・話者区間・XMLの拒否条件をテスト。
- 隔離したGPU評価ワークフロー：`ryotamatsuki/ehime-kokubunsai-ai-poc/.github/workflows/transcriber-10-dialogue.yml`
- 個人・組織の実録音や機密性のある情報は使用しない。結果に疑義がある場合、参照の逐語表記・重複発話・時間整列を監査する。

## 判定時の注意
このベンチマークの結果を唯一の一般性能値として広告したり、日本語実会議全般での成功保証として用いない。日本語のアクセント、話者条件、雑音、部屋の音響、録音機材が異なる独立サンプルが追加で必要。
