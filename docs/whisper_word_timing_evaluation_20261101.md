# Whisper large-v3 × Community-1 単語時刻と話者区間の整合性検証（2026-11-01）

## 目的と厳格な切り分け

Kiroku Studio公開匿名版の発話者ラベルに、単語の途中で話者が変化する事例が見られた。音声モデルの話者時刻区間そのものの欠陥、Whisper単語時刻の誤差、区間重複に基づく帰属処理の欠陥を混同しないよう比較する。

- **実際に固定する内容**: faster-whisper large-v3、beam size 5、VAD 550ms、word_timestamps=True、Community-1 Exclusive、話者数2、同一音声ハッシュ。各録音のASRと話者区間推論はそれぞれ1回のみ。
- **変える内容**: 単語に話者を割り当てる判定位置（開始/中点/終了）、重なりの最大値、重なりなしの場合の1.2秒近傍fallbackの有無。0秒をベースラインとした±150/300msの全体オフセットは参考感度分析のみ。参照スコアから採用オフセットを選ばない。
- **主指標**: 全体と録音ごとのcpCERと原文保持、単語帰属変更数、話者交代数。補助: 話者区間開始時刻から150/300ms以内の単語数、区間に重ならない単語数。
- **評価データ**: J-CRe3公式テスト音声の既出3録音、CC BY-SA 4.0、公式BoxプレビューMP3（原WAVではない）、人手発話区間。2026-10-31より既に研究済みの開発データ。実行政会議ではなく、3〜4人会議・重複への一般性は未確立。
- **限界**: 人手発話区間には厳格な単語時刻正解はない。したがってcpCERが変化しても、単語時刻の何ミリ秒誤差が補正されたと主張しない。人手参照を使った最良ルールの後付け採用は禁止。
- **プライバシー**: 入力MP3・人手文字起こし・生成本文はGitHub履歴・Actionログ・Artifactに残さず、専用Modal Volume上でのみ推論。数値とハッシュ等の非原文データのみ出力。公開Studio・ユーザージョブにはアクセスしない。
- **スコア確定条件**: 全3録音成功、手法間に同じASR文字列・単語数、独立に再計算した現行legacyとのcpCER一致、0秒時間ずらし条件との完全一致、数値のみ保存、研究用GPUと入力削除確認。

## 実装とCI

- `scripts/whisper_speaker_timing_audit.py`: legacyの独立再現、5方式・感度分析、原文ハッシュ不変検証
- `tests/test_whisper_speaker_timing_audit.py`: 音声認識を伴わない単語境界・日時異常・false overlap等のテスト
- `modal_whisper_word_timing_audit.py`: 元と同じWhisper/Community-1に基づく別アプリ・A10研究専用関数
- `scripts/jcre3_reacquire_private.py`: 過去の出典ハッシュに一致した音声・発話区間だけを入手
- 一度限りの研究評価: [GitHub Actions #41257350429](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41257350429)

## 既存GPU研究の数値（2026-10-31、今回のWhisper数値とは別）

Qwen3-ASR-1.7B+ForcedAligner-0.6BにCommunity-1 Exclusiveを組み合わせた同じJ-CRe3 3録音の固定入力で、話者区間を一律オフセットしても最良の後付け条件でmicro cpCERが45.209%→44.717%、0.492パーセントポイントの差にとどまった。録音ごとには非一様。自動話者区間と人手発話区間を同じ単語時刻・同じ帰属方式で比較すると45.209%と8.477%だったが、後者はprivileged human turnsによる診断値、配備可能な性能ではない。

実会議録音を認証前にモデル改善を主張しない。レポートに最終数値が未記載ならGPU試験は未確定扱い。
