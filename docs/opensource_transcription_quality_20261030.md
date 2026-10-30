# 既存文字起こし実装を参考にした品質改善・実測評価（2026-10-30）

## 結論

**A10上で実GPU比較を実施。Whisper large-v3のbeam 8は京都方言34.58秒の公開字幕を弱い参照として正規化CER 27.91%→26.74%に改善。ただしASR推論時間4.16→5.33秒、かつ単一短時間資料のためデフォルト採用は保留。**

**WhisperXに類似する区間重なりの評価に加え、語単位の話者割当ての曖昧さと、通常diarizationで検出された複数話者同時活動を「要確認」JSONとして出力。既存の話者IDは自動変更しない。**

## 公式ソースと設計差分

| プロジェクト | 参照URL | 有用な設計要素 | 今回の判断 |
|---|---|---|---|
| WhisperX | https://github.com/m-bain/whisperX | VAD、CTC forced alignment、単語/話者の重複時間最大化による割当 | 重複時間・割当ての曖昧さの監査を実装。CTC強制整列は依存環境と評価が必要で未導入 |
| WhisperX diarize.py | https://github.com/m-bain/whisperX/blob/main/whisperx/diarize.py | 話者の重複を区間クエリで集計 | 重複を事前計算する高速な別実装。コードをコピーせず独自実装 |
| Whisper-WebUI | https://github.com/jhj0517/Whisper-WebUI | faster-whisperとSilero VAD、diarizationの統合 | 現行faster-whisper内蔵VADを維持し重複導入しない |
| stable-ts | https://github.com/jianfch/stable-ts | 無音制約を用いた単語区間補正 | 日本語の単語時刻正解データがないため、今回は候補止まり |
| Kotoba-Whisper | https://github.com/kotoba-tech/kotoba-whisper | 日本語特化ASRと句読点補正 | 既存large-v3を無根拠に交換しない。独立日本語ベンチマークで比較する |

## 実装

専用ブランチ `experiment/whisperx-quality-evidence-20261030`、主PRの変更なし。

- `transcriber/attribution_review.py`: 短い/ゼロ長語時刻、複数話者区間を横断する語、重なり得点が近い語、独立したregular出力での同時発話候補、話者区間のカバレッジ不足を検出。データは `話者割当て要確認.json` に保存。
- `quality_experiment=True` の場合のみ出力。baselineのCSV/TXT/SRT/話者IDを勝手に書き換えない。
- `transcriber/processor.py` からASR語とexclusive/regular区間の重なりを評価し、レビュー語数を実測証拠に記録。
- `asr_beam_size` を5（既定）と8（実験）のみ許可し、8は `quality_experiment=True` なしでは拒否。キャッシュ設定にbeamの値を含め、異なる結果を取り違えない。
- `scripts/evaluate_asr_cer.py` は日本語NFKC+小文字化・空白/記号の削除を明示したLevenshtein CER評価。参照字幕のSHA256を記録。字幕は逐語注釈でないと明記。
- `tests/test_attribution_review.py` / `tests/test_asr_cer.py`：モック・合成単語・重複時刻、デフォルト不変性の回帰テスト。CIの成功は推論精度の証明とは区別。

## A10・同一公開日本語音声でのA/B実証

- Run: https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41015741559
- 元Artifact ID: `12959796337`
- 元Artifact SHA256: `96bfb0393f8e1165e0163c77d55787fac47b08810f259fff83094def9e1ee51c`
- Actions保持期限: **2026-11-06 15:44:29 JST**
- 音声：Wikimedia Commons 34.579375秒、公開京都方言2話者、SHA256 `9f6a382ddeffc9e74d9a94954b66c6ed43ae3a3ae1d2fede03747845c2e10124`
- 第三者字幕：https://commons.wikimedia.org/wiki/TimedText:Kyoto_women_conversation_in_1964.ogg.ja.srt
- 参照字幕SHA256: `8c580db4cff72f885f99976bb82215aa0d3af24811f6790025c25a6f4ce1f766`
- 話者数は既知2人固定、CUDA A10・Community-1・large-v3を維持。独立run2回、各1回のみ。

| 実測 | beam 5（baseline） | beam 8（candidate） |
|---|---:|---:|
| 正規化CER（外部字幕を弱い参照） | 27.90698% | 26.74419% |
| 編集誤り文字数 / 参照258字 | 72 | 69 |
| ASR推論秒数 | 4.16363 | 5.32749 |
| diarization推論秒数 | 2.13920 | 2.24994 |
| パイプライン処理秒数 | 10.87310 | 12.25605 |
| remote_function秒数 | 17.44051 | 18.78535 |
| client_wall秒数（純粋請求秒数ではない） | 23.97938 | 26.91694 |
| sampled GPU VRAM MiB | 11645 | 11645 |
| ASRセグメント数 | 13 | 21 |
| Whisperの単語トークン数 | 184 | 189 |
| 話者割当て要確認語 | 63 | 64 |
| 話者区間に紐づく発言行数 | 9 | 9 |

beam 8は**この短い音声だけで**3編集文字（CERで約1.163pt）改善。しかしASR推論が約1.164秒増加。字幕そのものに方言表記・省略等が含まれるため専門家の逐語正解に対するCERではない。

レビュー要確認はbeam 5で63/184（34.2%）、beam 8で64/189（33.9%）。「要確認」は必ず誤りという意味ではない。beam5の理由別フラグは同時発話候補34、ゼロ/短時間語21、話者重なり境界10、重なりなし12、カバレッジ不足1、得点僅差2で、同一語に複数フラグが付く。

## 採否ゲート

1. **beam8は実験設定のまま**。FLEURS等の日本語独立正解データと、現代日本語会議の少なくとも複数録音で再評価後にデフォルト変更可否を決定。
2. 日本語の正解話者区間（重複発話・相づち含む）について、DER/JER・話者交代検出・単語話者帰属の誤りを別々に測る。曖昧さ検出の割合を誤差低減率と誤解しない。
3. WhisperXの日本語強制整列候補 `jonatasgrosman/wav2vec2-large-xlsr-53-japanese` は別環境で比較する。重い依存変更やモデル交換はStage1へ自動混入させない。
4. 利用者の体感時間、メモリ、GPU請求、語・話者精度を同一ベンチマークで比較。
5. **main・稼働App・既存Colabノートブックの変更なし。** 別PRのDraftで保持。

原本ArtifactはChatGPTファイルライブラリにも期限に依存しない形で保全する。
