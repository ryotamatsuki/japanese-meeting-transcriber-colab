# 日本語会議文字起こし Web v0.1 — リリース受入基準（Draft）

## スコープ

- **限定ベータのみ**。アクセスパスワードを付与された少数の利用者が、**機密情報・個人情報を含まない、クラウド転送が許可された音声**を処理する。
- 最大60分、最大180 MiBの音声（MP3/M4A/WAV/FLAC/OGG/MP4/WebM）。4 MiB単位で分割アップロード。Web gatewayの単一リクエストのサイズ上限を回避。
- Whisper large-v3（faster-whisper）+ Community-1、任意2〜4話者または自動推定、A10 GPU。
- ブラウザで同期再生、文章・話者名・発話時刻編集、発話分割・結合、TXT/CSV/SRT/JSON ZIP出力。
- アクセス認証、セッション署名、CSRFトークン、ログインレート制限、利用ジョブ数上限、24時間4GPUジョブの上限、ジョブ削除、24時間後自動削除。
- AI要約・実名推定・議会や庁内の機密処理・複数人の組織共有・本番SLAは**範囲外**。

## 客観的なGo/No-Goゲート

| 条件 | 合格基準 | 証拠 | 現況 |
|---|---|---|---|
| 0. 推論 | A10のASR/diarを実GPUで完走、エラーを証拠保存 | Stage1 A10 Run 41006199679 | 基礎処理のみPASS |
| 1. Webワークフロー | 音声投入→進捗→音声再生→編集→保存→出力→削除が実環境HTTPS APIで音声→進捗→再生用音声取得→修正→保存→ZIP→削除を完走 | Actions Runs 41022519388・41022846766 | **HTTPS API E2E PASS／ブラウザ手動操作は未実施** |
| 2. 1時間の入力 | 実際の60分音声で完走し、最後まで発話区間欠落なし | A10 Run 41019777172: 合成反復音声3598.336秒、最終ASR終了3598.11秒 | **合成試験PASS／実会議未検証** |
| 3. 性能 | 60分音声を待機・転送込み30分以内 | Web E2E再試験 Run 41028143023: 509.92秒（GPU480.09秒） | **合成60分Web E2EはPASS、異なる長時間音声での再現性は未検証** |
| 4. 安定性 | 異なる公開録音10件連続で異常終了0件、成果物欠損0件 | A10 Run 41027370025、IngCrowd自然日本語2人対話10録音 | **GPU CLI 10/10 PASS／Web経由10件は未検証** |
| 5. 文字精度 | 現代日本語会議の逐語参照に対するCER中央値15%以下（暫定目標） | IngCrowd 10件のELAN簡易全文CER中央値39.907% | **未達。重複発話を含む全文連結CERでありcpCERではない** |
| 6. 話者精度 | 正解話者区間付き現代日本語2〜4話者会議でDER中央値30%以下（暫定目標） | IngCrowd 2話者10件、oracle話者数2、collar0/overlap含む：DER中央値32.124%、JER34.215% | **2話者の暫定基準未達。3〜4話者別途評価要** |
| 7. 効率 | 人手文字起こしより仕上げ完了時間を50%以上短縮 | 同一録音での人手タイムスタンプ | 未検証 |
| 8. 安全性 | 未認証/CSRF/不正入力に対する拒否、ランダムID、ログに音声なし、24時間消去、月額課金監視 | Web APIテストと隔離実環境HTTPS E2E | **認証・CSRF・明示削除 PASS／期限後自動削除・費用監視は未検証** |

**学術研究上の精度改善と、Webアプリの機能動作は別に認定**。基準に未達でも、個人での技術試験に限り使用可能。一般向け公開・庁内業務での利用は不可。

## GitHubブランチ

- Stage1 GPU：Draft PR #1
- 研究用話者分離：Draft PR #2
- 語単位監査/beam A/B：Draft PR #3
- v0.1 Webアプリ：新たなDraft PR。**mainへ自動マージしない**。

## 設定と利用時の注意

ModalのWeb Functionは技術的にはパブリックURLを持ちますが、アプリ内の認証を必要とします。公開URLを知っているだけでは音声の投入や推論ができないよう、認証を必須としています。認証コードは独立したセキュリティ監査前提の暫定実装であり、組織の認証基盤を代替しません。

### デプロイ前の前提

- Modal Secret `transcriber-hf`: `HF_TOKEN`（既存のCommunity-1用）
- Modal Secret `transcriber-beta-auth`: `BETA_PASSWORD`（ランダムで16字以上）、`BETA_SESSION_SECRET`（ランダムで32字以上）
- Modalアカウントの利用上限・請求アラート設定を確認すること
- v0.1試験用の機密性のない60分音声、正解書き起こし、正解話者RTTMを準備すること

```
modal secret create transcriber-beta-auth BETA_PASSWORD="<生成したパスワード>" BETA_SESSION_SECRET="<生成した長いランダム値>"
modal deploy beta_modal.py
```

**注意**：実際のパスワードをGitHub・Actionsログ・ChatGPTチャットへ書かない。ブラウザが使うURLはModal deployの出力から取得する。テスト前にSecretなしでデプロイすることは不可。

### 既知の制約

1. 単一利用者向け、Webコンテナは最大1個。最大2件保存、同時GPUジョブは1件。組織向けのマルチテナント認証・原子的分散キューは未実装。
2. 結果は書き起こし開始後の処理時間に依存。GPUの起動・モデルダウンロード・空き状況で変動する。
3. 実行ジョブ中の録音は即時削除しない（GPU読取中の破損防止）。終了後に削除でき、期限後は定期的に削除。任意時点での即時取り消しは今後の課題。
4. モデルの話者ID、語時刻の精度は保証しない。誤りが疑われる場合は必ず音声を再生して照合する。
5. WebコンテナのVolumeはworkspace内の他の許可済みApp等から参照できるため、権限管理はModal側でも行うこと。
## 2026-10-30 A10 60分合成音声の実測

- [GitHub Actions Run 41019777172](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41019777172) 全ステップ成功。
- 元Artifact ID `12961741294`、ZIP SHA-256 `c1ab74271086a65016273d19e412747e8e70cf241aac12708dcc3f6d6e3a260b`。保持期限2026-11-06 16:32:43 JST。
- 公開CC BY音声を繰返して作成した**約60分の合成音声**であり、現代日本語会議の認識精度を検証する録音ではない。
- 録音長3598.336秒／最後の認識発話終了3598.11秒／ASRセグメント1875件／発言1085件／推定2話者。
- pipeline 497.0446秒、CLI側537.6155秒、観測GPUメモリ最大11761MiB。
- 生音声・転写全文は証拠ZIPに含めず、技術メトリクスのみChatGPT Library `/AI開発/日本語会議文字起こし/Stage1_A10_20261030/transcriber_v01_60min_A10_41019777172.zip` へ保全。
- **本試験は旧Stage1のCLI経路であり、新Web API＋Modal Volumeを経由したWeb E2E試験ではない。** 旧CLIの25MiB制限内へ圧縮して実行。新実装の180MiB・60分上限は構造とAPI単体テスト段階。


## 2026-10-30 v0.1隔離した実環境E2E

**本件でv0.1の公開承認は行わない。** 2件のWeb E2Eは成功したが、ブラウザ上で人が画面編集した検証、実会議10件、60分Web E2E、品質指標、実運用費用等の条件が残る。

| E2E | 実行証拠 | 結果 |
|---|---|---|
| 認証/静的ファイル配信・話者分離OFF・アップロード・GPU・編集・ZIP・削除 | [Run 41022519388](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41022519388) | **PASS**、発言3件、HTTP E2E 54.36秒、ジョブ削除PASS、隔離環境削除PASS |
| 認証/静的ファイル配信・話者分離ON・アップロード・GPU・編集・ZIP・削除 | [Run 41022846766](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41022846766) | **PASS**、2話者検出・発言9件、HTTP E2E 50.17秒、ジョブ削除PASS、隔離環境削除PASS |

- 実行音声は著作権・出典を確認済みの公開京都方言34.58秒のみ。利用者の録音・実際の庁内会議データは使用しない。
- WebページのHTML/CSS/JSがModalに配置されなかった問題を修正：web imageの`add_local_python_source('beta')`を`add_local_dir('beta', remote_path='/root/beta')`に変更。実環境E2Eで静的ファイル200応答確認。
- 実行ごとに`modal environment create`で専用環境を作成。認証パスワード・署名シークレットはGitHub Actions内で生成し、パスワードの平文はログ/Artifactに保存しない。試験用Appと一時ストレージを環境削除で破棄。
- 話者分離OFF試験では使わないダミーHFトークンを隔離環境に用意。話者分離ON試験では既存のmain環境にある`transcriber-hf` Secretを**Secret参照で読み込む**（値を取得・コピー・表示しない）方法で検証。コード置換はActionsの隔離チェックアウト内だけであり、PRの本番コードには入れていない。
- それぞれの生Artifactと独立計算SHA256を一致確認：OFF `46907adb9ca024523a044d11ccc4f5ca8b3f756e644dc0923e309959f93c2e6d`、ON `bee535557f24bc4a61cfcf9357b0df23969b9dbfef6fbe4a2ffec975c6e8d569`。
- GitHub ActionsでのArtifact保持期限は2026-11-06。期限後も再検証できるようChatGPT Library`/AI開発/日本語会議文字起こし/Stage1_A10_20261030/v01_E2E_ASR_only_20261030.zip`、`v01_E2E_speaker_on_20261030.zip`へ保存済み。
- **現時点で外部利用者向けの永続Webサービスはデプロイしていない。** 試験URLは環境の削除により無効。限定利用に向けた認証情報は利用者自身がModal Secretに設定する必要がある。


## 2026-10-30 日本語10対話・人手ELANの独立評価

- [A10 GPU run 41027370025](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41027370025) 全ステップ成功、処理失敗0/10。
- コーパス [IngCrowd/japanese-themed-dialogue](https://huggingface.co/datasets/IngCrowd/japanese-themed-dialogue)、10本・120分52秒・人手ELAN付・2話者。**CC BY-NC 4.0・非商用評価のみ**。10組の異なる話者ではないこと、行政会議の音声ではないことに注意。
- Artifact `12965191701`、SHA-256 `971ad447a5b6865c4a03e804e52a374f78c34e3a1f8f0ccf53e7e046f667bd80`、期限2026-11-06 17:51:24 JST。元ArtifactをChatGPT Library `/AI開発/日本語会議文字起こし/Stage1_A10_20261030/ingcrowd_10dialogues_metrics_20261030.zip` へ保全。
- ASR: Whisper large-v3 beam5。Community-1話者数既知2で固定。原ミックスWAVをモノラルmp3 48kbpsに圧縮して推論。
- **CER中央値39.907%、DER中央値32.124%、JER中央値34.215%、1録音あたりGPU pipeline約60秒。** 品質目標CER15%以下・DER30%以下は未達。
- 前半4対話（女性・男性）の平均DER19.415%、後半6対話（女性同士）平均DER33.438%。話者構成と会話・録音条件等が同時に異なるため因果的な話者属性効果は断定しない。
- **CERは重複発話を含む人手ELAN発言の開始時刻順連結と単一ASR列との簡易距離**。重複発話の不一致で大きくなり得るため、通常CER・cpCERと混同しない。
- 音声・逐語転写本文はGitHub・Libraryへ保存せず、数値指標とELAN SHA256だけを保存。再現手順は`docs/ingcrowd_10dialogue_protocol_20261030.md`。

## 2026-10-30 60分 Web経由の初回負荷実行：失敗したゲート

- [GitHub Run 41026648129](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41026648129) は **失敗**。約3595秒の反復公開音声を、分割HTTPアップロードから実GPU推論し、2話者・音声末尾の発話・保存前の行取得まで通過。しかし全発言をWeb APIから一括修正保存する箇所でHTTP非200。ZIP出力・明示削除までのE2Eを完遂できなかった。
- 失敗時、試験専用Modal環境の削除は成功。推論モデルの精度が不合格だったという意味ではない。
- FastAPIで合成1200発言の一括編集・ZIP・削除が通る回帰試験を追加し、CI成功。次の隔離実環境で数値だけの保存失敗診断を行う。本文や秘密値はログに残さない。
- **60分Web E2Eは未達のまま**。診断と修正後に同条件で再試験を通過するまで公開不可。


## 2026-10-30 Stage 5 追加：重複発話がDERを構造的に制限

- [CPU-only 10対話人手ELAN重複診断](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41039604629) 全件PASS。参照重複活動1601.568 speaker-seconds / 総参照話者活動8262.109 speaker-seconds。
- 1時点1話者だけを出力する方式の厳格なDERの**理論下限19.3845%（全10録音合算）**。実際の合算DER28.5208%、録音別DER中央値32.124%とは異なる統計量。
- 観測話者活動検出漏れ1988.717秒の少なくとも1601.568秒、**80.53%**は重複発話の排他的表現だけでも説明できる。音声自体の無音区間注釈等を精査する前の参考値。
- 最優先の研究上の比較は同一Community-1のstandard（重複区間を保持）対exclusive（単一話者）の同一音声・同一ELANによるDER/JER。**実際に改善するか未検証のため既定出力は変更しない**。
- 参照メトリクスを引用した独立レポート：`docs/v01_stage5_error_analysis_20261030.md`。
- **再試験で60分Web経由E2E成功**：[Run 41028143023](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41028143023) 3593.448秒入力→509.92秒で完了、1097行編集保存・ZIP・削除までPASS。しかし初回Run 41026648129の保存失敗の根本原因は不明であり、ランダムな失敗に対する安定性は未認定。


## 2026-10-30 Stage 6：Community-1の通常（重複保持）対排他的出力の同一実験比較

- [GitHub Actions A10 41046765301](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41046765301) **10/10成功**。参照EAF SHA256は前回の10件と全件一致。
- Whisperとは独立した話者区間評価。全条件固定：IngCrowd 2話者10対話、Community-1、A10、num_speakers=2、collar=0秒、skip_overlap=False、48kbps MP3入力。
- **録音別DER中央値**：Exclusive 32.124% → Regular **25.548%**。**録音別JER中央値**：34.214% → **27.359%**。10録音すべて双方改善。
- **全録音合算DER**：28.521% → **22.219%**。Miss 1988.717秒→1392.380秒（約596.337秒改善）、Confusion 276.961秒→243.366秒（約33.596秒改善）、**False alarm 90.744秒→200.018秒（約109.274秒悪化）**。メリット・デメリットを併記する。
- 元Artifact `12972029827` / SHA256 `dd881612dc553d4ccc72dd3f2ebb6adb8164a32506b9d3b20b7e93ad2bfc9a66`。有効期限2026-11-06 20:22:36 JST。
- **話者区間（Diarization）の2話者暫定ゲートDER中央値30%以下はRegularで達成**。ただし既定アプリはExclusiveであり、最終文字起こしの話者ID/重複発言の抽出/CERは改善を実証していない。**v0.1全体は引き続きNo-Go**。
- 技術的推奨：`speaker_diarization`を重複話者候補の確認表示用として保持し、`exclusive_speaker_diarization`を現行の単語→単一話者割当て用に維持。重複部分のASR再推論や人手訂正UIを別実験してから機能統合する。
- 詳細：[docs/v01_stage6_community1_overlap_comparison_20261030.md](v01_stage6_community1_overlap_comparison_20261030.md)。

## 2026-10-30 Stage 7 — 重複発話「要確認」機能の実装・実環境合格

- [Stage 7 証拠・設計資料](v01_stage7_overlap_review_20261030.md)、[実GPU・Web E2E Run 41053310600](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41053310600)、[Chromium操作QA Run 41053529713](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41053529713)。すべて成功。
- 同一Community-1から重複推定区間を抽出し、Webで音声再生・発話行ジャンプ・確認済みを永続化。通常のASRと排他的な単一話者帰属は既定維持。
- 非商用研究用IngCrowd対話01（11分15.864秒・2人）：候補82区間。人手ELAN重複区間を参照した時間適合率**89.7353%**、再現率**47.7919%**。**見逃しを含むため重複なし保証には利用できない**。
- 165発言、HTTP E2E 129.81秒、GPU処理82.277秒。認証・CSRF・確認済み保存/解除・字幕修正・ZIP出力・明示削除・専用Modal環境削除すべてPASS。
- ブラウザUI操作は合成WAVのローカルChromiumでPASS。Modal実音声の検証はブラウザと同じHTTP API経路であり、音声プレイヤーの長時間手動操作を含む本番UI試験ではない。
- **v0.1全体の判定は引き続きNo-Go**。現行アプリの日本語CER、最終話者帰属、2〜4人の一般会議精度、再現性・費用・削除・作業時間短縮に未達の項目がある。
