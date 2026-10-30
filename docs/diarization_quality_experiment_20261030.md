# 話者分離精度改善実験（2026-10-30）

## 実施方針・判定

**技術実装・GPU実行は成功。精度改善の一般性は未認証。100ms短区間補正はデフォルトOFF、既存main・Stage 1モデルを上書きしない。** 
出力の話者数と短区間数だけを最小化するのは最適化目標としない。特に短い実際の相づちを消す危険がある。

## 実装

- `transcriber/quality.py`: 10〜100ms程度の短い A-B-A 異常区間のみを対象にする非破壊ワンパス補正（隙間は勝手に埋めない）。パラメータ・補正前区間を保存。補正の一般的有効性は未立証。
- `transcriber/diarization.py`: `output.speaker_diarization`（通常・重複あり）、`output.exclusive_speaker_diarization`（ASR統合用）を実験モードで別々に保存。
- 通常出力の同時話者活動から `pyannote_重複発話確認候補.json` を生成。これは確認候補であり、音声分離や正解認定ではない。
- `Config(quality_experiment=False, speaker_cleanup_ms=0)` が既定値。実験モード `--quality-experiment --speaker-cleanup-ms 100` でのみ補正し、出力ZIPに通常・補正前・補正後・重複確認候補を追加。
- `scripts/evaluate_diarization.py`: 人手注釈されたRTTMが必須。DER・JER・Miss・FA・Confusionを `collar=0`, `skip_overlap=False` で採点。補助的に `collar=0.25` を選べる。

## A10京都方言2話者サンプル（正解話者時刻なし）

- Run: https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41013349093
- Artifact: `12958492754`、SHA-256 `63fb18f22a27b88fcb043fcd738bf00b8be26e2a13d39266d77fe2699730ccee`
- `--expected-speakers 2`、34.579375秒、原exclusive16区間・12交代、補正後12区間・8交代。
- 補正対象: 13.025–13.092秒（約67ms）、14.189–14.206秒（約17ms）の2区間のみ。
- 通常出力22区間、異なる2話者の同時発話候補8時間帯。特に4.722–5.448秒、6.393–6.612秒の発話候補はexclusive出力で単一話者になっていた。
- **数値は出力の構造を説明するもので、正解発話区間に対するDER/JER改善値ではない。**

## AMI 4話者ベンチマーク（人手参照RTTM付き）

- 公開AMI ES2004a Mix-Headset音声300–360秒を切り出し、`pyannote/AMI-diarization-setup`の `only_words/rttms/test/ES2004a.rttm` を同じ区間にクリップして評価。
- AMI元データはCC BY 4.0。音声はartifact/リポジトリに含めず、RTTMと結果のみ保存。
- Run: https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41013941517
- Artifact: `12958791913`、SHA-256 `021f7dbdfdbb255f5f713e847430604ecaed197c079cf6c38051233163af7729`
- 正解RTTM話者数4、指定話者数4。モデル変更なし、100msのみ実験。
- 評価は `collar=0`、重複区間を除外しない。

| 方法 | DER（低い方が良い） | JER（低い方が良い） |
|---|---:|---:|
| exclusive補正前（現行） | 57.9067% | 72.3376% |
| exclusive 100ms補正 | 57.8378% | 72.3817% |
| regular（重複を含む通常出力） | 53.4711% | 68.5421% |

**100ms補正のDER差は約0.069パーセントポイントに過ぎず、JERは悪化。改善効果が十分だとは認定しない。** 通常出力は当該音声で優位だったが、文字起こし統合にそのまま置き換えると重複音声の単一ASR文字列の帰属が定まらないため、置換はまだ行わない。

## 品質保証上の残件

- 2話者京都方言の原音声を人が聴き、話者ごとの秒単位正解（重なり含む）を作る。字幕のみではDER/JERを算定しない。
- 同じ短い音声でパラメータを最適化してその音声で高精度と主張しない。独立した複数録音・会議ドメインで比較する。
- AMI別区間（420–480秒）のホールドアウト比較を実施し、人数の正しい条件で確認する。
- 必要なら別の音響話者分離エンジンとの独立評価を別段階で計画する。外部API課金や新たなSecretsは事前承認なしには使わない。
- 自動ASRの文字誤り率（CER）と話者帰属誤り（cpCER）は別の注釈が必要。GPUの実行PASSを精度PASSとしない。

## 保全と安全性

- 本評価は別ブランチ `experiment/diarization-quality-20261030` で実施。主PRのモデル、既存デフォルト、国文祭PoC main/本番Appは変更しない。
- 元のA10比較ArtifactとAMIベンチマークArtifactはChatGPT Library `/AI開発/日本語会議文字起こし/Stage1_A10_20261030/` に期限に依存しない形で保全。
- 音声・本人の認証情報はGitHubに保存せず、元の結果・補正履歴も別々に保持。
