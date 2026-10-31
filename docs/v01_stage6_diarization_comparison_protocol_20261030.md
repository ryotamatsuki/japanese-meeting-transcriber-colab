# Stage v0.1-6 — Community-1通常出力 vs 排他的出力の対応比較

## 目的
同一のCommunity-1、同一の日本語自然対話10録音、同一人手ELAN話者区間を用い、`speaker_diarization`（複数話者の同時発話を許す）と`exclusive_speaker_diarization`（1時点最大1話者）の精度差を検証する。**ASRや最終発言者割当ての改善を推定しない**。

## 一次出典
- [Community-1 model card](https://huggingface.co/pyannote/speaker-diarization-community-1) — 2種類の話者区間出力を提供。
- [pyannote.audio CHANGELOG](https://github.com/pyannote/pyannote-audio/blob/main/CHANGELOG.md) — 4.0の通常/排他的出力について。
- [IngCrowd Japanese Themed Casual Conversation Corpus](https://huggingface.co/datasets/IngCrowd/japanese-themed-dialogue) — 10録音、ELAN人手区間、**CC BY-NC 4.0・非商用研究評価のみ**。

## 凍結条件
- Modal A10、同一の`pyannote/speaker-diarization-community-1`。
- `stage=diarization`、`quality_experiment=True`（通常・排他的両方を出力するだけ、cleanup無効）。
- `num_speakers=2` （正解話者数を既知として与えるoracle条件）。
- 各混合音声WAVを16kHzモノラルMP3 48kbpsに変換。
- 参照：人手ELANの`speaker_1`/`speaker_2`区間、collar=0、skip_overlap=False。
- DER：最適ラベル対応後のmissed detection + false alarm + confusionを分母のreference speaker-secondsで割る。JERは各録音で算出。
- **同一ZIPから双方の出力を読む**ことが比較の前提。コード`scripts/evaluate_diarization_modes.py`が片側欠落を拒否する。
- 同一試行内での出力比較のため、モデル再初期化・学習パラメータ差などは両出力にかからない。
- 音声・転写・人手ELAN本文・発言者の固有名を保存／ログ出力しない。

## 成功基準
1. GPU実行・数値採点10/10完走、原評価の参照EAF SHA256と今回のSHA256が全件一致。
2. 録音ごとのDER・JER、miss・FA・confusionを比較。母数（speaker-seconds）で重み付けしたmicro DERも集計。
3. regularの方がDERが低くても、**FAやconfusionが増加した場合は程度を明示**する。
4. DERの改善量は「話者分離モデルの出力表現の効果」であり、編集可能な最終文字起こしのCER・cpCER改善とは言わない。
5. ベータの既定出力は凍結。改善を利用する場合は、重複発話時のASR転写・話者帰属アルゴリズムを別試験で合格させてから。

## 現時点の制限
- 10録音の話者数は2人固定。5人以上や実務の会議室集音は対象外。
- 単一ASR列では2人の同時発言を完全には転写できない。話者活動だけのDERが改善しても話者付き文字列の正しさは別。
- 元の10録音は非商用ライセンス。商用サービスの学習・販売データとして自由に使えるわけではない。
