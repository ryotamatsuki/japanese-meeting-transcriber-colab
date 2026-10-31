# Stage 12：Qwen強制アラインメントと話者付きcpCER — 証拠監査

2026-10-30。**研究評価のみ。v0.1 Release No-Go、mainとWebの既定Whisperは変更しない。**

## 初期GPU検証の確定結果

- 実行：[Qwen A10 2録音 Run 41068300913](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41068300913)。ジョブsuccessかつ内部2/2完了、失敗IDなし。
- 証拠Artifact ID 12983087754、ZIP SHA256 d39ed3b55250696a9b604fd81fcead765054cba1781bff83f92703e202e10134。
- Whisperの同一人手ELAN基準：[Stage8 A10 10録音 Run 41054900339](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41054900339)。基準Artifact 12976708710。2録音とも人手ELAN SHA256および正規化文字数が一致。
- 録音01：Whisper cpCER 37.7100% → Qwen cpCER 26.8123%（−10.8977pp）。単純全文CER 22.7076%、176発言、時刻付き2,095語。
- 録音05：Whisper cpCER 46.7040% → Qwen cpCER 40.8296%（−5.8744pp）。単純全文CER 33.4081%、115発言、時刻付き2,091語。
- 2録音のcpCER中央値：Whisper 42.2070%、Qwen 33.8209%（−8.3861pp）。2件だけでの優越一般化禁止。
- 双方本文正規化保持・2話者統合PASS。モデルロード約8.6～8.8秒、Qwen＋aligner実推論約59.9～60.3秒。Community-1推論・Web入出力を含む合算処理時間ではない。

## Stage12で実装したゲート

評価スクリプト scripts/evaluate_stage12_qwen_release_gate.py と回帰テスト tests/test_evaluate_stage12_qwen_release_gate.py を追加。基準・2録音結果は docs/evidence に数値のみ格納（生音声、原文、逐語録は非掲載）。

必須条件：10/10件を明示的に完走し、失敗0件、全録音で同一ELAN SHA256と正規化参照文字数が一致、モデル/aligner/Community-1 exclusive一致、本文保持、時刻末尾カバレッジ、話者数2を満たすこと。GitHub Actionsのジョブsuccessのみでは合格としない。重複、欠番、NaN、参照不一致は即時失敗。

研究を次へ拡張する暫定判定：10件中8件以上改善、ペア改善中央値5ポイント以上、個別最大悪化2ポイント以下。これは**Qwenを既定採用する基準ではなく追加研究の優先順位**のみを決める。品質・60分Web・編集時間・GPU費用・24時間削除が未認証のため、研究ゲートPASS時も Release No-Go。

実行例（GPUの再推論不要、数値ファイルだけを監査）：

    python -m scripts.evaluate_stage12_qwen_release_gate --baseline docs/evidence/stage8_whisper_cpcer_10_20261030.json --qwen-summary docs/evidence/stage11_qwen_bridge_2_20261030.json --exploratory-two --output local_runs/stage12-exploratory.json

現在の2録音結果の研究拡張ゲートは NOT_MET（10録音未達）。この判定は失敗ではなく、データが不足していることを示す。

## 残作業

最優先は同一条件で残り8録音の Qwen3-ASR-1.7B＋Qwen3-ForcedAligner-0.6B＋Community-1 exclusive cpCER を計測すること。現行の独立GPU実験は約15分以内入力専用であり、60分試験へそのまま流用しない。次にQwenの発言データから編集・SRT・ZIP・再保存をWeb E2Eで試験し、Stage11の60分保存不定期失敗の再現性を別途解明する。

データセットはCC BY-NC 4.0。商用サービスの学習・評価利用へ無断転用しない。
