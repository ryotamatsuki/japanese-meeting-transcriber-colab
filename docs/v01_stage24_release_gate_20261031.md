# Stage 24 — v0.1 リリース最終判定・機械的なGo/No-Go検査

## 2026-10-31の判定

**Release No-Go**。Stage17で研究精度ゲートPASS、Stage18で11分のQwen実GPU Web E2E合格、Whisperによる2種類の60分合成Web E2E合格。ただしQwenで60分の実Web E2Eを2種類の録音で再現できておらず、自然な3・4話者会議の人手正解、CER中央値15%以下、最終話者モードDER中央値30%以下、人間の完成作業時間50%削減、Modal Workspace予算と通知、定期削除ジョブ実運用の監査は未完了。

### 再現可能な現時点の監査

    python -m scripts.release_gate_v01 --evidence docs/evidence/v01_go_evidence_snapshot_20261031.json --output local_runs/v01_release_gate.json

Go条件を満たさない場合は非ゼロ終了コード2、数値と未達理由を結果JSONに書き出す。学術研究上の精度優越のみではリリースできない。単体テスト中の擬似的なGO分岐は認証用の実証ではない。

## 確定した証拠

- 10件Qwen＋ForcedAligner＋Community-1： [A10 Stage17 Run 41076994471](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41076994471)、内部10/10成功、cpCER中央値36.60008%。Artifact ID 12990015767、ZIP SHA256 6905d2dc412c2a92cc2cca6ea087a970dca7b831226b7295308182a479dad60b。
- [Qwen 11分実GPU Web E2E Run 41079582347](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41079582347)、発話176、話者2、編集ZIP削除すべてPASS。実環境終了。
- [Whisper 合成60分 Web E2E Run 41072366917](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41072366917) PASS。
- [Modal実体削除 Stage15 Run 41073598915](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41073598915) PASS。ただし定期起動の継続的監視は未実証。
- [Modal課金API照会 Stage22 Run 41079742581](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41079742581) PASS。個別の請求額を公開ログへ出さない。予算設定済みとみなさない。

## 残る外部の実測・権限確認

1. [Qwen専用60分 E2Eの手動起動ワークフロー](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/workflows/transcriber-stage18-qwen-web-60min.yml) で、独立する少なくとも2つの許可済み音源を使って実測、最終分まで確認。現行ワークフローは公開の日本語音声反復を用いた**合成長時間試験**なので、実際の60分会議評価を代替しない。実験起動前にModalのWorkspace予算を確認。
2. 自然な3話者と4話者の録音、人手話者RTTM、人手逐語を用意し、`scripts.evaluate_multispeaker_ja`で各3会議以上のCER/cpCER/DER/JERを計測する。例えば [RWCP-SP01（研究用途、要利用申請）](https://www.nii.ac.jp/dsc/idr/speech/submit/RWCP-SP01.html)。権限がなければ無断取得しない。
3. 人間による5つ以上の独立録音の編集時間クロスオーバー試験、完成品質の同時確認。 `scripts.evaluate_human_time_study`で中央値50%以上の削減判定。
4. ModalのWorkspace Owner/Managerが [Usage & Billing](https://modal.com/docs/guide/budgets) で月額Workspace予算・別建てのspend limit・通知を確認。**Workspace budgetはクレジット適用前の利用額を制限**し、spend limitはクレジット後の自己負担額を制限する。両者は異なる。Environment budgetはTeam/Enterpriseのみ、請求総額の上限を代替しない。
5. 機密・個人情報・県業務上の保護対象は、現行の個人向け研究Webにはアップロードしない。必要なら情報管理責任者の許可とサービス評価が別に必要。

## 運用上の区別

`11分Web E2E PASS` と `研究用cpCER比較PASS` は**閉じた研究試験の成功**。利用者にサービスとして提供する最終リリースの`GO`ではない。品質を満たしていない事実を隠すため、既存の受入基準を事後に下げたり、合成・自動生成データを「人手」注釈や実際の作業時間と呼び替えたりしない。

