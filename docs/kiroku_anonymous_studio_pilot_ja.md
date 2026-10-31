## 最新の実環境検証（2026-10-31）

公開URL: https://ryota-matsuki--kiroku-anonymous-studio-beta-anonymous-web.us-east.modal.run/

専用アプリ: `kiroku-anonymous-studio-beta`。mainへのマージなし。既存の非公開ベータ、研究用アプリ、国文祭アプリはデプロイ対象にしていない。ASRは既定のWhisper large-v3 / beam5のまま。Qwenへの置換なし。

### 実環境で発見して修正した不具合

1. frontend/package-lock.jsonが未保存で、デプロイ用npm ciが失敗。lockfileをコミットし、npm ciとReactビルドを再確認。
2. Modalのコンソール出力が長いregional URLを折り返し、正規表現によるURL抽出が失敗。SDKのFunction.get_web_urlへ変更。最初のRun 41157947842はデプロイ成功後に検証前停止、GPU未実行。
3. Run 41158060101では独立HTTPクライアント2件のアップロード・実GPU処理は完了したが、並列GET /rowsの片方で500。Modal保護ログで「there are open files preventing the operation: .../results.json is open」を確認。同期GETが別スレッドでVolume.reloadとファイル読み取りを重ねていた。
4. 読み取り・書き込みを同じ非同期ロック内で直列化し、同期SDK処理はasyncio.to_threadで実行。音声はロック内でリクエスト専用ローカル一時ファイルへコピーし、FileResponse送信後に削除する。Volumeのファイルをストリーム中に開き続けない。Range再生を維持。
5. 新規回帰2テストは旧実装で1 failure/1 error、修正後は成功。全172 offline tests成功。初回失敗を後からPASSに変更しない。
6. ブラウザ試験の音声準備用FFmpegがGitHubランナーにないことを確認し、imageio-ffmpegを明示依存に追加。これらの準備失敗RunはGPU試験未実施。
7. 匿名モードにも残っていた「パスワード認証」表示を「利用者別に分離／登録・パスワード不要」に変更。保持時間は「24時間経過後に順次削除」に修正し、毎時sweepに伴う遅延を隠さない。

### 運用設定

Modalトークンはユーザーの操作時点承認後に1日期限で新設し、対象リポジトリのActions Secretsへ登録。値はソース、PR、ログへ記載しない。`kiroku-anonymous-session`の署名鍵はランダム生成し、既存Secretは上書きしない。

Workspace Usage limitは$30。確認時の残クレジット$25.48、当期$4.52 credits / $0 charges。Spend limit画面はDefault $0。0入力でもSaveは無効で、新たなcustom $0を保存したとは扱わない。Usage limitとクレジットは別々に確認し、全体usage capを30ドルより引き上げていない。Volume storageの課金停止までは保証しない。Usage alertsはEmail/In-appとも有効。main環境の通知にはMuted表示があった。

### 検証の範囲

二つの実物端末ではなく、Chromiumの独立browser contexts（PC 1440×1000、mobile 390×844）。各contextはCookie、localStorage等が別。許諾元: https://commons.wikimedia.org/wiki/File:Ja-LessonIntroKonPron-practice1.ogg （marsian自身がpublic domainとして公開）。元音源（ffprobe実測28.358617秒。配布ページ表記27秒）と8秒地点から切り出した12秒音源を使用。音源・ASR全文・ZIPは成果物として保存しない。画面証拠では本文を試験マーカーに置換。

自然な24時間経過を待っての削除、実物iPhone/Safari、長時間会議の匿名版E2E、汎用的な文字認識・話者分離精度は今回の短音声試験で認定しない。毎時削除Functionのデプロイとretention単体テストは別の証拠として扱う。

### 最終PASS（実GPU・実Chromium）

[Run 41159119383](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41159119383) は全ステップsuccess。

| 項目 | 結果 |
| --- | --- |
| 別Cookie・別ストレージの2ブラウザからUIアップロード | PASS |
| 2つの異なるjob ID、各一覧は自分の1件のみ | PASS |
| 大小2音源のA10実GPU（話者分離ON） | PASS |
| 両方向の状態・音声・発言・確認・ZIP取得拒否 | PASS、404 |
| 両方向の他人への編集PUT・DELETE拒否 | PASS、404 |
| 各自のテキスト・話者名のUI編集・保存・再読込 | PASS |
| 音声APIのSHA256と各自の入力ファイル一致 | PASS |
| PC/mobile双方の再生・停止ボタン | PASS |
| ブラウザダウンロードのTXT/CSV/SRT/JSON全形式 | PASS、各自マーカーあり・相手マーカーなし |
| UI削除と削除後の状態・音声・結果・ZIPへの404 | PASS |
| 両viewportで横はみ出しなし・JS例外なし | PASS |
| 匿名署名Cookieの独立 | PASS |
| Cookieなし401・不正CSRF403 | 実API Run 41158060101でPASS（そのRun全体は並行rowsでFAIL）、offlineでもPASS |
| セッション失効・期限経過削除 | offlineテストのみ。実際の12h/24h経過は未実施 |

数値は最終成功Runだけを採用:

| 指標 | PC A | mobile B |
| --- | ---: | ---: |
| 音源秒数 | 28.358617 | 12.0 |
| 発言数 | 3 | 1 |
| pipeline_seconds | 13.311641212 | 15.170554529 |
| gpu_task_seconds | 15.592784405 | 17.865192652 |

2利用者の画面操作・待機・編集・ダウンロード・削除を含む試験全体は **76.333秒**。`gpu_task_seconds`はGPU関数内の開始記録から結果保存後までで、課金GPU秒やコンテナ起動待ちを含む壁時計全体とは同一視しない。GPU最大1コンテナのためGPU処理自体はキューに並ぶ。

画面証拠Artifact `13026491234` / SHA256 `a9bd20c21f63449f25732e6b5dc6c0b46aca5c180bcc9d55ea3569d0e582d6ac`。ZIP内はPC/mobileのdashboard・本文置換済みeditor PNGと集計JSONのみ。ダウンロード後にSHA256を独立照合し、両編集画面を目視確認。モバイルで保存通知が再生を遮る不具合を修正し、同じライブ操作で再検証済み。

初期失敗4GPUジョブと、最終成功2GPUジョブの合計6回を使用。URL抽出、停止済みendpoint、FFmpeg欠落、初期表示待機の失敗ではGPUは実行していない。試験のみの名前を持ち、全件deletedかつjob_indexが空であること、GPU受付履歴数と試験レコード数が一致することを条件に、試験メタデータと対応する試験受付履歴だけを清掃。全体4GPUジョブ/24hという制限は変更していない。最終清掃もPASS、通常利用の受付枠を試験消費で塞いだままにしていない。

デプロイ成功: [Run 41158401082](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41158401082)。最終ブラウザRunでも同じ専用アプリを再デプロイし、修正済み版を検証。コードCI: [Run 41159121086](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41159121086) success（172テスト、Reactビルド等）。

誤った通知表示の修正後、最初の待機5秒は起動・セッション応答の揺らぎを許容できずRun 41158964191が試験開始前にFAIL。初期UI待機を60秒とした最終Runは成功した。失敗を成功として数えない。

今後の意図しないGPU起動を避けるため、終了時に両ワークフローのpush自動起動を外し、手動実行専用に戻す。workflow_dispatchはdefault branchに定義がない場合そのまま起動できないので、mainへ勝手に追加しない。次回は明示的に認証したModal CLIで対象ブランチをデプロイするか、承認された一時pushトリガーを使う。


---

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
