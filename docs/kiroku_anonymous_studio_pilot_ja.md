# Kiroku Studio — 匿名セッション分離（限定試験版）

## 利用の流れ

React Studioを開くと、FastAPIがランダムな署名付きCookie（Secure / HttpOnly / SameSite=Strict / 12時間）を発行する。ユーザー登録・共通パスワードは不要。録音をアップロードし、完了を待ち、必要なら話者名・発話を修正してZIPを保存する。会話後に再訪して編集を継続することは想定しない。Cookieが失効・削除された場合、以前のファイルにはアクセスできない。新しい匿名セッションへの移管やURL共有は提供しない。

## 安全境界

- `beta/server.py` の `anonymous=True` では、署名Cookieを検証し、HMACで一意の内部owner IDを導出する。Cookie原文は保存しない。
- `FileBackend(require_owner=True)` は匿名ジョブのすべての操作でowner IDを必須とし、job_idが存在しない場合と異なる所有者の場合に同じ404を返す。閲覧一覧、状態、アップロードチャンク、完了、音声、編集、重複候補、確認状態、ZIP、削除の全経路を検証する。所有者の指定を漏らしたバックエンド呼び出しも拒否する。
- 同一オリジンCSRFチェック、署名Cookie、HTTPS限定、no-store、CSP等を維持する。ReactのlocalStorageに録音内容・認証情報は保存しない。
- 新しい `beta_modal_anonymous.py` は旧パスワード付きベータとは別アプリ・Volume・Dictを使用する。GPU推論のモデル重みのみ共有する。匿名アプリのWeb FunctionにはHugging Faceトークンを渡さない。
- 共有推論GPUはA10の最大1コンテナ。Webも最大1コンテナとしプロセス内ロックでジョブ一覧の更新を直列化する。これは限定試験向けであり、複数Webコンテナによる本番スケールでは原子的なキュー・クォータ管理に変更する。
- 既定の保護: 同一匿名セッションの保存済みジョブ2件、実行中1件、全セッションの保存済みジョブ8件、全体GPU開始4件/24時間、最大音声180MiB・1〜60分、音声と生成結果の保持24時間（期限を過ぎたものは毎時の削除ジョブで消去）。削除ジョブ実行遅延や失敗があり得るため厳密な24時間以内の消去は保証しない。
- 匿名Cookieは認証資格情報なので、そのブラウザ・Cookieを盗まれた場合は他人になりすませる。ブラウザが違えば自動的に別ユーザーになるが、同一ブラウザ・同一Cookieを共有する利用者同士は分離されない。組織内機密情報の保管や利用者の同一性確認には個別認証が必要。

## デプロイ手順（環境設定が完了した限定試験のみ）

```bash
cd frontend
npm install --no-audit --no-fund
npm run build
cd ..
# 事前にModal SecretsをGUIで設定すること。
# kiroku-anonymous-session : BETA_SESSION_SECRET（予測困難な32文字以上）
# transcriber-hf : HF_TOKEN（Community-1のアクセス条件に同意）
modal deploy beta_modal_anonymous.py
```

※ `beta_modal.py` は従来のパスワード付き環境としてそのまま維持。公開デザインプレビュー `modal_public_preview.py` も実録音処理には接続しない。

## 検証と公開条件

`python -m unittest tests.test_beta_anonymous -v` で以下を確認する。

1. 二つの匿名ブラウザ間でCookieとジョブ一覧が独立する。
2. 他人のジョブIDの直接指定でも、音声・文字起こし・編集・ZIP・削除・チャンク追加・GPU開始すべて404になる。
3. 有効な所有者だけがチャンクアップロード、編集、重複候補の確認、ZIP、削除を正常に実行できる。
4. セッションCookieの削除・無効化やCSRF不備による越権を拒否する。
5. 並行する二つの匿名ブラウザで所有者の入れ替わりがない。Cookieを増やしても全体保存件数を突破できない。
6. 既存のパスワード付きベータ・Reactビルド・Modalのインポートが正常に動く。

これは**コードの分離機構**であり、全利用者向け公開の承認ではない。特にModalの請求上限が真のHard Spend Limitか、無制限なセッション発行・未完了アップロードによる妨害、レート制限、24時間物理削除、実GPU経由のE2E、自然音声の精度・速度、データ取り扱い許諾の確認は必要。公開前にこれらの不足を解消すること。

## 2026-10-31 — Modal実デプロイ・2セッション実音声試験の準備

- `.github/workflows/kiroku-anonymous-live.yml` を追加。ブランチの既存アプリとは独立した `beta_modal_anonymous.py` をデプロイし、Studio画面のビルド済みアセットを含める。デプロイ成功後に `scripts/smoke_anonymous_modal_live.py` を実行する。
- 実験音源：Wikimedia Commonsのパブリックドメイン日本語音声（`Ja-LessonIntroKonPron-practice1.ogg`、約27秒）。利用許諾：https://commons.wikimedia.org/wiki/File:Ja-LessonIntroKonPron-practice1.ogg
- 実環境試験では異なるCookie jarを持つ2つの独立したHTTPクライアントで、**同時アップロード→GPU処理待ち・完了→他人のファイルに404→発話1件を編集して保存→TXT/CSV/SRT/JSONのZIP検証→両ジョブ削除**を実施する。これは**2台の実物の端末ではなく、2つの独立した仮想クライアント**による並行E2Eであり、実スマートフォンとPCの操作検証は別途必要。
- このワークフローは、GitHub ActionsリポジトリSecretsの `MODAL_TOKEN_ID` と `MODAL_TOKEN_SECRET`、管理者がModalの実画面で費用上限を確認したうえでGitHubリポジトリVariable `KIROKU_BUDGET_VERIFIED=yes` を設定した場合だけデプロイを許す。これは自己申告ゲートであり実予算の独立検証ではない。あわせてModal内Secret `kiroku-anonymous-session` の `BETA_SESSION_SECRET` と、既存 `transcriber-hf` の `HF_TOKEN` が必要。
- 実験失敗時はデプロイ済みの匿名アプリを停止する処理を用意。成功時はアプリを保持し、公開URLをActionsのStep Summaryへ記録する。
- [GitHub Actions Run 41155771547](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41155771547)：Python 170件PASS、ReactビルドPASS、スクリプト構文チェックPASS。ただしデプロイ前提の設定を値を表示せずに確認したところ **MODAL_DEPLOY_CREDENTIALS_CONFIGURED=no、KIROKU_BUDGET_APPROVAL_CONFIGURED=no**。そのため、この時点では実デプロイ・本物のGPU処理・ライブ2クライアントE2Eは**未実施**である。


## 2026-10-31 — Workクラウドブラウザによる管理画面監査

- PR #4、#5はともにopen/Draft。調査開始時の#5 HEADは `3b74def9b263b7f3700ee557eb30d83a8ca29e6d`。リポジトリ内AGENTS.mdは見つからなかった。main・既存Modalアプリは変更していない。
- Modalの認証済み管理画面でWorkspace `ryota-matsuki`（Owner）、環境 `main` を確認。既存live appは6件で、匿名版アプリはまだ存在しない。
- Usage limitは$30、当期使用$4.52（credits）、請求$0、残credits $25.48。Spend limitは「Set spend limit」の状態で、明示的な保存済み上限は確認できない。入力画面にDefault $0という表示があることだけをもって保存済みのHard Spend Limitとは認定しない。画面説明では停止後もVolume storage chargesは発生する。
- Usage alertsはEmail/In-appとも有効。main環境の通知欄にはMuted表示がある。Workspace-wide concurrent GPU limitは10、現在使用0。A10のその時点の実在庫・起動成功までは未検証。
- Secrets一覧で `transcriber-hf` の存在を確認（値は閲覧していない）。`kiroku-anonymous-session` は存在しない。作業環境のModal profile・環境変数credentialsは未設定。CLIの `modal token new` は「Could not connect to the Modal server」で失敗し、資格情報は取得していない。
- ローカル検証：170 offline tests PASS。初回 `npm ci` はlockfile欠如で失敗。package-lock.jsonを追加した後の `npm ci` と `npm run build` はPASS。これはデプロイ前の再現可能な不具合修正であり、GPU試験の成功ではない。
- live smokeを強化：両方向の編集PUT拒否、Cookieなし401、不正CSRF403、全4形式の編集マーカーと相手のマーカー非混入、削除後の状態・音声・結果・ZIPの404、両ジョブ完了までの経過時間とpipeline_secondsを検査する。アップロード途中の失敗に備え、ID発行時点でクリーンアップ対象へ登録する。
- **BLOCKED / 未実施**：匿名版デプロイ、公開URL取得、実GPU2ジョブ、独立ブラウザ2コンテキストのUI操作、PC/スマートフォン相当画面、実環境の24h物理削除。モックや過去の別アプリ結果でPASSに代用しない。
- 次の具体的操作は、デプロイ資格情報の作成と対象リポジトリActions Secretsへの登録、匿名署名Secret作成、明示的Spend Limitの確認・必要なら$0設定。ブラウザで新規credentials・アクセス権を作る操作に対する確認前に停止した。資格情報はコード・本文・公開ログへ保存しない。
- default branchにworkflow定義が必要なdispatchを回避する経路として、既存live workflowは対象ブランチの自ファイル更新pushで起動する構成。実際のdispatch呼出しやデプロイrunはこの作業では実行していない。
