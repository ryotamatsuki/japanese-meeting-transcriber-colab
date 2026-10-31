# 同一話者の段落化：公開匿名版への反映記録（2026-11-01 JST）

対象：Kiroku Studio 匿名公開版 `kiroku-anonymous-studio-beta`。
URL：<https://ryota-matsuki--kiroku-anonymous-studio-beta-anonymous-web.us-east.modal.run/>

**実際の本番相当デプロイ成功：** [GitHub Actions Run #41253348326](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41253348326)。GitHub Actions内でModal認証、ワークスペース予算確認フラグ、既存署名鍵の継続利用、ReactのCIビルド、既存Modal appへの`modal deploy beta_modal_anonymous.py`、URL解決、実HTTPS新JS配信、匿名セッション、owner-scoped jobs APIを順に検証。

- `LIVE_BUNDLE_SPEAKER_PARAGRAPHS_AND_ANONYMOUS_SESSION=PASS`
- `LIVE_SCRIPT_ASSETS_FOUND=1`
- リリース後のワークフロー全体 **SUCCESS**、リカバリーのロールバックステップは SKIPPED。
- 変更範囲：連続する同一話者の読みやすい段落表示、非破壊的コピー、TXT段落化および旧発言形式TXTの併録。発言単位のタイムスタンプ・保存内容、CSV/SRT/JSONは保持。
- ASRは既存のWhisper large-v3 / beam5、話者分離はCommunity-1で**変更なし**。
- モデルGPU処理や利用者データのアップロードを伴う本番受入テストは実施せず。CPU契約テスト、Reactビルド・ブラウザのUIトグル／編集への復帰の回帰テストはPR #14の[CI #41246475608](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41246475608)でPASS。
- 同一アプリ名、同一Modal Volume/Dict、既存署名Secretを上書きしない設計でデプロイ。既存データは意図的に削除・更新していない。

初回の一時デプロイ Run #41253243480 では、検証スクリプトに誤った二重エスケープ正規表現がありReact JSを検出できず、既定安全策として旧匿名版への自動ロールバックに成功。修正後はPython `HTMLParser` で実HTMLのscript srcを解析し、Run #41253348326 で新UIの実配信を確認して成功。初回の失敗を成功と偽らない。別の一時Run #41253091183 はデプロイ前のテスト依存不足で失敗し公開アプリは変更していない。

研究PR #6–13・Qwen/Sortformer/Nemotronは同時反映していない。本番アプリ公開は旧の非機密音声専用・保持期間・レート制限等の運用制約をそのまま継続。PR #14はGitHubのDraftとして残し、mainマージの事実はない。
