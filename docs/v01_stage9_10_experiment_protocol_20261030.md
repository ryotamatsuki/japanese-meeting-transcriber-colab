# Stage v0.1-9・10：重複発話と日本語ASR精度の実験計画

作成日：2026-10-30。研究段階、**v0.1限定公開はNo-Go**。ベータの既定処理は一切変更しない。

## 共通の固定条件

- 既存基準：Whisper large-v3、beam=5、16kHzモノラル音声、Community-1排他的話者帰属、Stage7の重複発話の要確認UI。既存の受入評価はCER中央値39.907%（単純連結）とcpCER中央値46.895%（最終話者付き）。
- 人手正解：IngCrowd Japanese Themed Casual Conversation Corpus、10本の2人対話＋人手ELAN、**CC BY-NC 4.0・非商用研究評価のみ**。人の実名、県職員の会議、業務機密は評価に使用しない。
- 実験はModal A10の隔離した評価コード・GitHub Actions上で実施する。元録音・書き起こし全文・秘密鍵・Hugging Face tokenをログやArtifactに保存しない。保存するのはメトリクスと参照EAF SHA256のみ。
- モデル変更は`quality_experiment=True`の場合に限定する。ベータ既定の`Config.asr_model='large-v3'`、`asr_beam_size=5`を保持する。新モデルを選ぶには同一音声・同一採点での改善を必要とする。

## Stage 9：重複発話の再認識と音源分離

**候補3つ**：
1. 混合音声の同じ短い重複区間をそのまま再認識する（音源分離なし）。
2. [SpeechBrain SepFormer WSJ0-2Mix](https://huggingface.co/speechbrain/sepformer-wsj02mix)で8kHz・2音源を分離し、それぞれをWhisper large-v3で再認識する。
3. [IngCrowdの公開話者別録音](https://huggingface.co/datasets/IngCrowd/japanese-themed-dialogue)を別々にWhisperで認識する**理想分離条件**（単一マイク録音からは得られず、運用に導入できない上限評価）。

- 評価対象：ID 01（異声質）と05（比較的近い声質）の**人手ELANを使って選んだ短い同時発話区間**。選定はあくまでオラクル評価用であり、実装時の重複候補はStage7のCommunity-1を使う。
- 正解発言が音声切断境界をまたぐとCERを不当に悪化させるため、参照話者の**注釈区間を丸ごと含む7秒以内の切り出し**だけを採用する。該当窓がない録音は判定不能として報告し、恣意的に参照を切り捨てない。
- 各短区間の話者ごとに**cpCER**を比較し、分離が適切なら尺度不変SNR改善（SI-SNRi）を参考算出。SepFormerは英語WSJ音声で訓練された8kHzモデルであり、日本語会議への性能を前提としない。
- 比較は一つの入力・一つのWhisper設定で統制。音声分離の新たな音質劣化、幻覚文字、実行時間、2系統ASRのコストも考慮。
- **採用ゲート**：理想音源で改善できてもSepFormerが混合音声より悪化すれば不採用。短い2例だけでは本番採用しない。音声分離を本番に入れるにはさらに10録音と実際の会議音声での再現性が必要。

## Stage 10：日本語ASRモデル・デコードの比較

- 3録音（01/05/08）で、**(A)** Whisper large-v3 beam5（固定基準）、**(B)** large-v3 beam8、**(C)** faster-whisper turbo beam5を同一音声・同一日本語人手ELANで比較。推論秒数と正規化CER、認識文字数を記録。
- 追加候補：[Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)（Apache-2.0）を**別GPUイメージ**で非商用対話01/05に試行し、同じ人手参照で比較。Qwenの話者付き文字起こしは未実装であり、段階的なASR単体候補評価とする。
- 評価のCERは、人手の重複発話を開始時刻順に連結した**全文連結CER**。重複時の文字順序の違いが寄与するため、通常の単一話者音声CERや最終話者付きcpCERと同一視しない。
- 3本・2本の探索試験だけで「CER15%目標達成」や一般性能改善を宣言しない。候補が有利なら10録音に範囲を広げ、最終的な話者付きcpCER、処理速度、費用、安全性を評価して採否する。
- 新モデルの公式利用条件およびモデル品質の違いを記録。Qwen3-ASRはオープンモデルでApache-2.0。Qwenを実用する場合、話者割当てに必要な単語時刻の取得方法とGPU構成を別途設計しなければならない。

## 実験コード・検証先
- Stage 9: `scripts/stage9_select_eval_windows.py`、`modal_stage9.py`、[Stage9 GPU Workflow](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/blob/eval/meeting-transcriber-stage1-20261030/.github/workflows/stage9-overlap-separation.yml)
- Stage 10: `transcriber/asr.py`・`transcriber/processor.py`のオプトイン実験設定、`modal_app.py --stage asr --no-diarization --quality-experiment`、[Stage10 ASR Workflow](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/blob/eval/meeting-transcriber-stage1-20261030/.github/workflows/stage10-asr-model-ablation.yml)
- 追加Qwen: `modal_stage10_qwen.py` と [Qwen GPU Workflow](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/blob/eval/meeting-transcriber-stage1-20261030/.github/workflows/stage10-qwen-pilot.yml)
- 無制限のGPU自動実行を避けるため、初回起動後はワークフローを手動実行専用へ戻す。

## 結果の判定規則

- 数値改善・悪化・実装障害を区別し、実測できなかった項目は未検証と記載する。
- Stage9/10の実験結果が改善であっても、本人確認・安全なデータ削除・ブラウザ編集・日本語会議での修正時間削減を確認するまではv0.1の公開判断は**No-Go**。
