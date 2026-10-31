# Stage35 — Modal実料金・上限・通知の運用監査（2026-10-31）

## 判定：部分完了、設定確認は NOT_VERIFIED

現行Modal Workspaceの現在の請求・予算・通知設定はGitHubだけでは取得できない。**設定済みと断定してはならない。** Releaseは引き続きNO_GO。

### 確認済みの事実

- [Stage22 read-only billing run](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41079742581)は成功。2026-10-31時点の実請求額そのものは公開しない。APIが有限Decimalの `billed_cost` と `metered_cost` を返すことだけ確認した。
- [Modal official budgets](https://modal.com/docs/guide/budgets)によればWorkspace Budgetは**クレジット適用前の利用量に対する月間ハード上限**、Workspace Spend Limitは**クレジット適用後の追加請求上限**。
- StarterでもWorkspace BudgetとSpend Limitは使用可能。Environment BudgetはTeam/Enterprise限定。
- Qwen研究のGPU関数は `gpu='A10'`, `max_containers=1`, `timeout=3600`, `retries=0`, `scaledown_window=2`, `single_use_containers=True` に制約。これらは**一時的なリソース消費を抑える**が、月額予算上限や支払限度に代わるものではない。
- GitHub Actionsの同時実行抑制や個別ジョブのタイムアウトも、複数種類の関数・アプリから生じるWorkspace全体の費用を限定するものではない。

### Workspace Owner/Managerが私的に確認する項目

1. Modalの自分のWorkspaceで **Settings → Usage & Billing** を開き、月間Workspace Budget（利用額のハード上限）を表示・確認する。共同利用Workspaceなら**他のアプリにも影響**するため勝手に変更しない。
2. 同じ画面でWorkspace Spend Limit（クレジット適用後の支払い上限）を確認する。実際に許容する金額は所有者が決める。アシスタントは設定額を推定して決めない。
3. 課金・利用量に関する**通知設定と受信先**を別に確認。一般的なジョブ失敗通知と課金通知は同一ではない。設定機能がない場合は「通知済み」と記録せず、別の承認済み監視が必要。
4. Workspaceの現在の使用額・今月の請求額・設定額は公開GitHubに貼らない。ダッシュボードの証拠写真をローカル保存し、SHA-256だけ記録する。画像ハッシュは画像の内容が正しいことを証明しないため、管理者が原画を直接目視する。
5. `docs/evidence/modal_finance_budget_attestation_template.json` を**非公開のローカルファイル**にコピーして実際に確認した値と日時を入力し、`python -m scripts.modal_finance_guard --evidence /private/modal_budget.json --output /private/modal_budget_audit.json` で入力整合性を検査。公開リポジトリにユーザーの請求情報・スクリーンショットをアップロードしない。

### 境界条件

- **プログラムで料金APIを読めた**ことは、予算上限が設定されている証拠ではない。
- **単体テスト用の架空設定がPASS**でも、現実のWorkspaceの設定済みは示さない。
- `modal_finance_guard` の監査は自己申告の形式・鮮度・ハッシュ・確認事項の網羅性をチェックする。Modalの管理画面や課金上限の実在を直接検証するものではない。
- 通知先をチェックできない限り、現行 `modal_budget_controls` ゲートの `charge_notifications_configured` をtrueにしてはならない。
- 実利用者の修正時間計測はユーザーの希望により後日実施。今は `human_editing` ゲート未達。

### 次工程

既に実施済みの60分Qwen E2Eはソース2種とも同一コミットで成功（Run 41092963562, 41091559990）。`human_check_final_minute` は人による音声聴取未実施のためfalseのまま。料金上限・通知はユーザーのModal管理画面での確認を要するためfalse。
