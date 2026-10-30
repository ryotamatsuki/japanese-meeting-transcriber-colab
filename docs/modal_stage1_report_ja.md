# Japanese Meeting Transcriber — Stage 1 実装・検証報告

検証日：2026-10-29〜30（日本時間）。**判定：Stage 1未完了。L4実診断とlarge-v3実ASRはPASS。Community-1実推論は未完了。**

> 最新状態は末尾「2026-10-30 最終実測追記」を参照。以下の2026-10-29時点の表は初回検証履歴。
基準main：`84628cdc6f31e0a811d7bdbc0348347bf88fe7f7`。
作業ブランチ：`feature/modal-gpu-inference-poc`。mainへ直接コミット・マージしない。

## A. 実装結果

| ファイル | 変更内容・再利用範囲 |
|---|---|
| transcriber/files.py | cell 8のsha256_file・safe_nameを抽出 |
| transcriber/asr.py | cell 12のキャッシュ照合、Whisper推論、単語JSON、部分保存・メモリ解放を抽出 |
| transcriber/diarization.py | cell 14の人数指定、ffmpeg変換、Community-1 exclusive区間、JSON/CSVを抽出 |
| transcriber/alignment.py | cell 16のassign_and_group。グローバル設定を引数化した以外は同じアルゴリズム |
| transcriber/exporters.py | cell 18の時刻形式、TXT/CSV/SRT、話者対応表、処理レポート、ZIPを抽出 |
| transcriber/processor.py | 単一ファイルのASR・話者分離・統合エントリー。Colab/Modalに依存しない |
| transcriber/runtime.py | L4/CUDA実演算、import診断、CTranslate2を含むGPUメモリのサンプリング |
| modal_app.py | L4・専用モデルVolume・Secret・一時入力、modal run。ASRと話者分離のFunctionを分けOFF時のSecret参照をなくす |
| requirements-modal.in/.lock | 主要依存・推移依存を固定。イメージ内pip check/import/freeze |
| tests/test_transcriber.py・test_modal.py | 元コードとの一致、キャッシュ、OFF制御、構成検査 |
| scripts/validate_run.py・estimate_cost.py | 実出力の構造検査と実測値からの限定的費用推定 |
| docs/modal_setup_ja.md | 認証・テスト音声・Test 1〜6・証拠の確認・削除手順 |
| README.md・SECURITY.md・.gitignore・CI | Modal案内、データ除外、回帰検査 |

既存ノートブックは変更していない。インストール・ランタイム再起動・upload・userdata・files.download・Drive mountはノートブックに残し、推論モジュールへ持ち込んでいない。
専門用語と話者数の設定はConfig/CLI引数に移した。元の単語照合・発言統合・エクスポートを独立関数にし、依存を引数として渡す。
モデルロードはASR終了後に解放してから話者分離する。小型モデル・量子化・CPU代替は追加していない。

### 移植前後の対応表

| 精度に関係する設定・処理 | Colab | Modal移植 |
|---|---|---|
| ASR | Whisper large-v3 / faster-whisper 1.2.1 | 同じモデル・バージョン |
| GPU計算精度 | CUDA時float16 | CUDA/float16固定。CPU代替禁止 |
| 言語・task | ja（auto/en可）/ transcribe | 同じ |
| beam_size | 5 | 5 |
| VAD | True / 無音550ms | 同じ |
| word_timestamps | True | True |
| condition_on_previous_text | False | False |
| GLOSSARY | stripしてinitial_prompt / 空はNone | 同じ |
| 話者分離 | Community-1 / pyannote.audio 4.0.7 | 同じ |
| 話者数 | expected優先、なければmin/max、0は未指定 | 同じ |
| 音声変換 | ffmpeg 16kHz mono PCM16→float32 waveform | 同じ |
| 話者出力 | exclusive_speaker_diarization | 同じ |
| 単語照合 | 重複時間の合計最大、なければ近傍1.2秒以内 | 同じ |
| 話者ラベル | 出現順「話者1」等 | 同じ |
| 発言統合 | 同一話者・110字/22秒以内・無音1.5秒以内 | 同じ |
| ASR/話者結果キャッシュ | 音声SHA256＋設定辞書の完全一致 | 同じ述語。再実行検査用に1呼出し内保持 |
| 出力 | TXT/CSV(BOM)/SRT/ASR JSON/話者JSON/レポート/ZIP | 同じ名前・列・エンコード・収録対象 |

## B. GPU・依存環境

以下は**構成値**であって、GPUコンテナでの実測値ではない。

| 項目 | 指定値 |
|---|---|
| GPU | NVIDIA L4 |
| Python | 3.11（Modal image） |
| PyTorch / torchaudio | 2.9.1+cu128 |
| CUDAランタイム | 12.8系（wheel依存） |
| cuDNN | 9.10.2.21（lock） |
| CTranslate2 | 4.6.2 |
| faster-whisper | 1.2.1 |
| pyannote.audio | 4.0.7 |
| PyAV | 18.1.0 |
| soundfile | 0.13.1 |
| TorchCodec | 0.8.1（公式CPU音声デコーダwheel、torch2.9対応。推論はL4） |
| huggingface-hub | 0.36.0 |
| Modal CLI | 1.4.3（ローカルでversion確認済み） |
| CPU / メモリ | 2物理コア / 8 GiB |

推移依存の解決とlock生成は成功した。CUDA12/cuDNN9はfaster-whisper公式要件、TorchCodecは公式互換表、PyTorchは公式cu128 wheelを起点とした。
イメージビルド・全import・GPUドライバとの整合は認証不足で未検証。OSパッケージとモデルrevisionも完全固定ではなく、実際のsnapshot情報を取得してから再現性を確定する必要がある。

## C. テスト結果

| テスト | 結果 | 証拠・範囲 |
|---|---|---|
| main取得・ソース全セル確認 | PASS | 基準コミットを取得、全コード抽出・処理フロー確認 |
| 既存check_notebook.py | PASS | 20 cells、構文・出力除去・元の話者割当て |
| 新規unittest 8件 | PASS | ローカル回帰・構成・キャッシュ検査のみ |
| 話者割当て一致 | PASS | ON/OFF計200ケース、元関数と抽出関数の出力一致。境界検査も追加 |
| 出力形式一致 | PASS | 架空データでON/OFF両方、元コードとZIP内ファイル内容がbyte一致 |
| 認識結果キャッシュ制御 | PASS（テストダブル） | 同じ設定でモデルを再生成せず、用語/音声SHA変更・破損JSONで再生成 |
| Test 1：Modal L4起動 | 未実施（起動要求は認証で停止） | `Token missing. Could not authenticate client.` |
| Test 2：Whisper実推論 | 未実施 | Modal認証なし。日本語実音声での推論出力なし |
| Test 3：Community-1実推論 | 未実施 | Modal認証・HF_TOKENなし。利用条件同意も確認不能 |
| Test 4：GPU統合・各形式生成 | 未実施 | ローカル架空データの検査を実推論成功とは扱わない |
| Test 5：GPU上の話者分離OFF | 未実施 | OFFでSecret参照しない構造・制御はローカル検査済み |
| Test 6：GPUモデル/結果キャッシュ | 未実施 | モデルオフライン再ロードと結果再利用の実行経路を実装済み |
| Colab対Modalの精度比較 | 未実施 | 同じ音声の双方の実出力がない |

実行コマンド：

```bash
python tests/check_notebook.py
python -m unittest discover -s tests -p 'test_*.py' -v
python -m compileall -q transcriber modal_app.py scripts
python -m modal run modal_app.py --stage gpu --output local_runs/gpu
```

サニタイズした実行記録：[modal_stage1_validation.log](modal_stage1_validation.log)。
GPUの起動要求はexit code 1で停止し、音声はアップロードしていない。請求設定を変更していない。
テスト録音・推論結果・認証情報はGitHubに登録していない。

## D. 性能・コスト

**実測GPU性能・コンテナ起動時間・モデルロード時間・GPU利用量・1件当たり費用は未取得。数値を推測して成功報告しない。**
Modal公式料金表（2026-10-29参照）：L4 $0.000222/秒、CPU $0.0000131/物理コア秒、メモリ $0.00000222/GiB秒、Volume $0.09/GiB月（無料枠等の条件あり）。
https://modal.com/pricing

`scripts/estimate_cost.py` は実測evidenceまたはDashboardから得た請求対象秒数に、L4・2コア・8 GiBを適用する。
イメージビルド、Function外の起動/終了時間、ネットワーク、Volume無料枠は別途評価する。性能比較はモデルロード時間と推論時間を分離し、結果キャッシュhitの回を混ぜない。
コンテナ起動時間はclient wallからの単純な差分では認定しない。Dashboardの実ログを採取する。

## E. 既存Colab版との比較

機能・アルゴリズムは対応表のとおり維持し、オフラインで比較可能な出力と話者割当ては一致した。
Modal版は単一ファイル入口、L4/CUDA固定、モデル専用Volume、HF Secret、コンテナ内一時処理へ変更した。
Colab版の複数ファイル選択・Drive保存・ダウンロードUIはノートブックに維持し、Modal版のStage 1対象外とした。
結果JSONキャッシュは1回のModal呼出し内での再実行検証用で、呼出しをまたぐ永続結果キャッシュはない。
両モデルのrevision・GPU・PyTorch環境が異なる可能性があるため、**認識精度が同一とは未認定**。同一音声での比較が必要。

## F. 次のステージへの移行判断

`transcriber.processor.process` は将来FastAPI/UIから呼べる独立関数にした。ただし**実用性の確定とWebアプリ化への正式移行は保留**。
利用者側でModal認証・予算確認、HF条件同意・Secret設定、公開可能な日本語2話者音声の用意が必要。
その後Test 1→6を実行し、音声との照合、起動ログ・費用・出力ZIPを採取し、本報告の未実施欄を証拠付きで更新する。

## G. GitHub・残課題

Draft PR：[PR #1](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/pull/1)。mainにはマージしていない。
実装・テストの基準コミット：`acf7024b779bd7646f62b288ad64e025ae07dc8c`。
このコミットのGitHub Actions「Validate notebook」は成功（run ID: `40812647212`）。
本節の追記のみ、後続のドキュメント更新コミットに含む。
残課題はGPU依存環境のビルド、Test 1〜6、精度・実測費用・証拠の確定。Stage 1の完了条件のうち、実GPUに関係する項目はすべて未達成。


### 完了条件の照合

| 完了条件 | 判定 |
|---|---|
| L4でPyTorch/CUDA正常動作 | 未完了：認証で停止 |
| large-v3日本語実推論 | 未完了 |
| Community-1実話者分離 | 未完了 |
| 統合実処理 | 未完了 |
| 既存話者割当ての再利用 | 完了：元関数との回帰一致 |
| 各形式の実推論出力 | 未完了：架空データの出力回帰のみ成功 |
| 話者分離OFFのGPU動作 | 未完了：ローカル制御検査のみ |
| モデルキャッシュ実再利用 | 未完了 |
| 既存・新規オフラインテスト | 完了 |
| 実測性能・費用 | 未完了 |
| Draft PR | 完了：Draft PR #1 |


## H. 2026-10-29 追加検査・Windows認証ガイド

GPU実行後の`evidence.json`を別途検証する`scripts/validate_evidence.py`を追加した。L4/CUDA/cuDNN/CTranslate2認識、推論・モデルロードの所要時間、GPUメモリ観測、話者分離OFF、モデル・結果キャッシュの整合性をテスト1〜6別に検査できる。合格は**実測証拠の内部整合性のみ**であり、原音声と結果の精度比較やModal利用明細との照合を代替しない。実GPU推論は引き続き未実施。

`tests/test_modal_evidence.py`に合成証拠を用いる9件の回帰テストを追加した（既存の新規8件と合わせて17件）。2026-10-29のGitHub Actions run `40813890342` は成功。Windows PowerShellでの認証・起動方法を`docs/modal_setup_ja.md`に追記。Modalダッシュボード上でログイン済みであることと、CLIトークンの有効化・GPUが起動できることは別問題として扱う。

ブランチ上の追加コミット：`9bd99b4`、`b76c5ca`、`f35b372`。本追記も含め、mainは未変更。


## 2026-10-29 ブラウザ確認・CLI認証再試行

今回の開始時にDraft PR #1を取得し、前回の`f9b2690`から
`50f254bbc25d6bd09031b43cef6e27507ebe9c0f`までfast-forwardした。
追加の証拠検証スクリプトと9件のテストを取り込み、オフライン17テスト、
既存ノートブック検査、compileallはすべて成功した。

### ブラウザで確認した状態

- 指定されたEdgeのModalタブを実際に操作した。ログイン済み。
- Workspace `ryota-matsuki`、環境 `main`、Starterプラン。
- クレジット残高$30.00、当月使用額$0.00、Workspace usage limit $30。
- Spend limitは「Set spend limit」表示。変更・追加課金・アップグレードは行っていない。
- Concurrent GPUs上限10、使用中0。Concurrent containers上限100、使用中0。
  これらは割当上限であり、L4の確保成功や個別権限の実証ではない。
- Secrets一覧に`transcriber-hf`は存在しなかった。新規Custom Secret画面で
  名前`transcriber-hf`、キー`HF_TOKEN`まで入力し、値は空のまま本人入力待ち。
  Doneは押しておらず、Secretはまだ作成されていない。既存Secretの値は開示していない。
- Community-1の公式ページを開いたがHugging Faceは未ログイン。
  アカウントの同意済み・未同意は確認できない。本人ログイン後に条件の確認が必要。
- ブラウザでの代替実行可否も調べたが、Modal Notebooksは提供終了と表示された。

### CLI側の新しい阻害要因

`python -m modal token new`を正規フローで実行したが、
認証URLが発行される前に`Could not connect to the Modal server.`でexit 1。
`socket.getaddrinfo('api.modal.com', 443)`は`gaierror`。
標準HTTPクライアントからのHTTPS要求はModalトップで200、APIトップで415となり、
ブラウザ/HTTPの到達性とModal SDKのgRPC接続は区別が必要。
インストール済みModal 1.4.3の接続実装はgrpclib Channelの直接接続であり、
今回の実行環境では通常のSDK認証接続が成立していない。
認証Cookieの抽出・転用、TLS回避、SDK通信経路の改造は行っていない。
この接続失敗は、本人のModalログイン失敗や残高不足を意味しない。

### 今回の実GPU検証結果

| Test | 結果 | 根拠 |
|---|---|---|
| 1 L4/CUDA/import | 未実施 | CLI認証前の接続で停止。イメージビルドなし |
| 2 large-v3 ASR | 未実施 | Test 1未達、実音声推論なし |
| 3 Community-1 | 未実施 | 接続に加えHFログイン・Secret設定が未完 |
| 4 統合出力 | 未実施 | 実推論ZIPなし |
| 5 話者分離OFF | 未実施 | Secretを参照しない構造は回帰検査のみ |
| 6 モデル/結果キャッシュ | 未実施 | 実GPU再ロード・再推論なし |

Modal App/Function/Containerの実行識別子、GPU実行ログ、実出力ZIP、
性能・請求対象時間・実測費用は未取得。Stage 1は引き続き未完了。
音声・推論結果・認証情報はGitHubへ追加していない。

### 再開に必要な本人操作

1. 開いているCommunity-1ページでHugging Faceにログインし、条件を確認する。
   同意が必要なら本人が実施する。
2. Read権限のHFトークンを、準備済みModal Secret画面のValueへ直接入力してDone。
   トークンをチャットやGitHubへ貼らない。
3. Modal APIへ通常接続できる本人PC等で、最新の作業ブランチを取得し、
   `python -m modal token new`の正規認証を実施する。
   本実行環境のネットワーク制限はHF Secret登録だけでは解消しない。
4. setupのTest 1をまず実行し、成功してから権利関係の明確な日本語2話者音声でTest 2〜6へ進む。
   本回は音声準備・転送・実推論まで進んでいない。


## 2026-10-30 Actions実検証（更新時点）

### 実行経路と修正

本人がWorkのクラウドブラウザでModalへログインしたことを、
`ryota-matsuki / main`のApps画面で確認した。
国文祭PoCで使用したGitHub Actions Environment Secretsが現存することも確認した。
文字起こし側にはSecretsがないため、国文祭リポジトリの隔離ブランチ
`eval/meeting-transcriber-stage1-20261030`で検証workflowを実行した。
Secrets値は取得・コピー・表示していない。国文祭main・稼働Appは変更していない。

1. Actions run `40998500388`：Modal接続・認証成功。
   未使用の話者分離FunctionのSecretまで解決されるため、GPU診断で停止。
   GPU/ASR/OFF用AppとSecretを使う話者分離Appを分離して修正。
   修正コミット `cd6636cb8056e4fa3e98c4f3061e00c45a0e793c`。
2. Actions run `40998805817`：依存インストールとpip check成功。
   CUDA版TorchCodecの共有ライブラリimportでビルド失敗。
   公式CPU音声デコーダwheelをURL・SHA256固定。モデルの推論はCUDAのまま維持。
   元CUDA wheelのreadelfでlibnppicc.so.12等の依存も確認。
3. Actions run `40999313679`：上記修正後、Test 1成功。Test 2を順次実行中。
   検証元コミット `b7bf442ea57d8f3cd7a41e4a8ee31796d56144c1`。
   同コミットの既存CI run `40999216987`も成功。

### Test状況

| Test | 状況 | 証拠・制限 |
|---|---|---|
| 1 L4/CUDA/import | PASS | ActionsのTest 1 step成功、validate_evidence.pyもPASS。L4識別、CUDAテンソル演算、CTranslate2 CUDA、全importを実行 |
| 2 large-v3 ASR | 進行中 | 別L4コンテナの割当待ち。推論成功とは扱わない |
| 3 Community-1 | 未実施 | transcriber-hfの本人入力・モデルアクセス権確認待ち |
| 4 統合 | 未実施 | Test 3未完了 |
| 5 OFF | 未実施 | 起動時Secret依存は修正。実音声のOFF統合は未実施 |
| 6 モデル/結果キャッシュ | 未実施 | 実GPU再推論未実施 |

Test 1 Modal App：`ap-ixJoxZE95dtW7KuGmItKmy`。
GPU診断Function：`fu-CSAuQslqKFgSr7SeOtfxCO`。
Test 2 Modal App：`ap-PBLmIpjIwEOxnUT3r1FYfN`。
ASR Function：`fu-uYLGsE4rBka7qXpeqN3BGH`。

Test 2ログで12:53:01及び12:53:49（JST）に、GPU_L4 workerの割当待ちを確認。
この待ち時間をモデルロード・推論時間・請求対象時間として計上しない。
更新時点ではASR JSON・ZIP・性能の実測値はまだ未取得。
診断evidenceとログはworkflow終了時にActions artifactへ保存される設定。

### テスト音声・予算

国立国語研究所「方言録音資料シリーズ11 京都市方言」のWikimedia公開音声。
原公開元でシリーズ3〜15の音声にCC BY 4.0が付されていることを確認。
長さ34.579375秒、SHA256
`9f6a382ddeffc9e74d9a94954b66c6ed43ae3a3ae1d2fede03747845c2e10124`。
`scripts/prepare_validation_audio.py`で取得・照合・出典記録を行う。
音声・推論結果はGitHubにコミットしていない。
古い京都方言の2話者会話であり、一般的な会議音声の精度認証ではない。

実行前の残クレジット$30.00、実行中の表示$29.99。
表示はWorkspace全体の丸め値であり、単一テスト費用の実測ではない。
課金設定・利用上限の変更は行っていない。
公式料金は2026-10-30にもL4 $0.000222/秒、CPU $0.0000131/コア秒、
メモリ $0.00000222/GiB秒を確認した。
ASR/話者分離の費用・性能は、実測秒数取得後に算出する。

### 当時の本人操作待ち（以下のHF設定後の追記で解消）

WorkのModal Secret作成画面に`transcriber-hf`、`HF_TOKEN`まで入力済み。
Valueは空欄、未送信。本人がReadトークンを直接入力しDoneを実施する。
Community-1のモデルアクセス条件は、トークンを発行したHFアカウントで確認する。
CLI認証は既存Actions経由で成立しており、本人PCでのModal CLI操作は不要。

実行ログ：https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/40999313679
Test 1：https://modal.com/apps/ryota-matsuki/main/ap-ixJoxZE95dtW7KuGmItKmy
Test 2：https://modal.com/apps/ryota-matsuki/main/ap-PBLmIpjIwEOxnUT3r1FYfN


### 2026-10-30 HF設定後の再開

本人操作後、Modal Secret `transcriber-hf`の作成をUsage画面で確認した。
値は読み取っていない。モデル利用権限の有効性は推論開始後のモデル取得で確認する。

- 前runのASRは12:51:39にenqueueされ、13:03時点でも未開始・Pendingだった。
  ModalとActionsから停止し、run全体はcancelled。Test 1 stepのsuccessは維持。
  artifact `12952759823`を取得し、証拠validatorを再実行してPASS。
- 新run `41001086758`はTest 2に成功。日本語の実認識、単語タイムスタンプ、
  ZIP構造、GPU実行証拠を検査した。Test 2 Appは`ap-oku3npcbfnF7rNepLaImgS`。
- 同runのTest 3専用Appは`ap-gTQ5or6dldrqH1M5qpl1Xx`、
  Functionは`fu-rPToc1Hlm40cyYDxmyKY6Z`。
  13:09:52、13:10:39、13:11:35（JST）のModalログにL4割当待ちを記録。
  これはHF権限エラーではなく、モデルの取得・推論前の待機。
- 各クライアント呼び出しに600秒上限を設け、上限超過時も証拠を保存する。

Test 1の実証値：NVIDIA L4、torch CUDA 12.8、cuDNN 91002、
CTranslate2 CUDA devices=1。実測ライブラリはtorch/torchaudio 2.9.1+cu128、
TorchCodec 0.8.1、faster-whisper 1.2.1、CTranslate2 4.6.2、
pyannote.audio 4.0.7、PyAV 18.1.0、soundfile 0.13.1。
Modal Function Calls画面でStartup 4.40秒、Execution 14.11秒、Succeededを確認。
診断時のnvidia-smiメモリは228 MiB（瞬間値でモデル推論ピークではない）。

公式単価をStartup+Executionの18.51秒に適用した限定的概算は
$0.0049229196。請求対象時間の確定値ではなく、ビルド・終了処理・ストレージ・
無料枠を含めた請求額でもない。
client_wall_secondsは20.440750744999974秒だが、local_entrypoint内の時計である。
CLI初期化と事前イメージビルドを含まないため、計測注記を実装と手順で修正した。

Test 1 artifact SHA256:
`e1090fd7ab4e9f934673747b367d35101ec28ecc15ac3727b37c07f41680c82d`

現行run：https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41001086758
Test 1 artifact：https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/40999313679/artifacts/12952759823


### 2026-10-30 最終実測追記

**Stage 1未完了。Test 1・2は実L4でPASS。Community-1はGPU未割当のため推論未実施。**

検証run `41001086758`では、Test 2成功後、Test 3が600秒のクライアント上限で
exit 124となった。専用AppのModalログは13:18:32までGPU_L4容量待ちを記録。
13:21:27にclient disconnectedで停止し、live container / running callとも0を確認した。
モデルロード開始、HF認可成功、GPU転送、exclusive出力を示す証拠はない。
HF Secretの作成は確認済みだが、Community-1利用条件の同意・Read権限の有効性は未検証。
Test 4・6は依存するTest 3の未成立により未実施。統合成功とは扱わない。

#### Test 2の出力・実測

- App：`ap-oku3npcbfnF7rNepLaImgS`、Function：`fu-FNyuLwgDozCx6sHyhVd7su`。
- 入力34.579375秒。large-v3 / faster-whisper 1.2.1 / CUDA float16、言語ja。
- ZIP内 `whisper_asr.json` はUTF-8で読め、13セグメント・184単語、非空の日本語出力。
  セグメントの開始時刻順と、全単語の0以上・開始<=終了・音声長内を確認した。
  ASR出力範囲1.18〜34.18秒。語のゼロ長区間はWhisperの出力として許容する。
- `validate_evidence.py --stage asr`、`validate_run.py --stage asr`を
  Actionsと取得後のローカルで実行しPASS。精度の合格判定・会議音声品質の保証ではない。
- モデルロード30.950656724秒（初回取得を含み得る）、ASR推論6.058045705秒。
  ASR RTF 0.1751924581、音声長/推論時間5.708008273倍。
- pipeline 37.421000727秒、remote_function 61.841951989秒。
  GPUメモリのサンプル最大4214 MiB、サンプリングエラー0。厳密な瞬間ピークではない。
- Modal画面：13:07:20 enqueue、13:07:33 started、Startup 7.49秒、
  Execution表示1m 1s、Succeeded。client_wall 75.823667645秒を起動・請求時間と同一視しない。
- このrunのevidenceは修正前のtiming_noteを含むため、その注記は不正確。
  時計自体はlocal_entrypoint内で、CLI初期化・事前イメージビルドを含まない。
  後続コミット37071dbで注記のみ修正し、取得した証拠ファイルは改変していない。

公式 https://modal.com/pricing （2026-10-30確認）のL4、2 CPU、8 GiB単価合計は
$0.00026596/秒。remote_function実測のみでは約$0.01645、
これに観測Startup 7.49秒を加えた限定的概算は約$0.01844。
モデル取得・診断を含むこの短いASR実行の概算であり、定常ASR単価ではない。
終了処理・イメージビルド・ストレージ・丸め・無料枠を含む請求額の確定値ではない。
Modal App overviewのusage表示は$0.02、Workspace残クレジット表示は$29.96。
後者はWorkspace全体の表示でテスト固有の請求額ではない。

証拠：Actions artifact `12953802803`（run `41001086758`、7日保存設定）。
SHA256 `ce6e4a92a8916507bc7e8e365067b5ca5ec4e4f4c61204c53335ab234a766936`。
内容は `02-asr/evidence.json`、`02-asr/run-1.zip`、ASR/話者分離ログ、音声出典。
取得・ZIPハッシュ照合を実施した。音声・認識JSON・ZIP・認証値はGitHubへコミットしない。

#### Test 5・最終状態

Test 5を依存するTest 3と切り離してrun `41002514566`で実行した。
App `ap-iOSdjxhqlw0nM5NSNUVb5m` / Function `fu-XNEAfa4KGmMfssSVZEM5ff`。
起動時に作成したFunctionはgpu_checkとasr_onlyだけで、HF Secretを参照しない経路。
ただし13:23:30（JST）のModalログはL4割当待ちで、180秒上限によりexit 124。
OFF時の出力完走は未検証でありPASSとはしない。
artifact `12954326457`（ログ・出典のみ、認識出力なし）のSHA256は
`4a5344c2707d87663d1d8f877bdd00bfedc574e62fc74c6da89e3cd320cf1cfe`。

| Test | 最終判定 | 確認範囲 |
|---|---|---|
| 1 L4起動・CUDA演算・import | PASS | 実L4と証拠を確認 |
| 2 Whisper単独 | PASS | large-v3実ASR・単語時刻・JSON |
| 3 Community-1単独 | FAIL（実行試行）／推論未実施 | L4割当待ち600秒でtimeout。HF認可・GPU転送・話者精度は未検証 |
| 4 統合 | 未実施 | Community-1・話者ラベル付き出力は未確認 |
| 5 話者分離OFF | FAIL（実行試行）／推論未実施 | Secret不要のApp起動のみ確認。L4待ち180秒でtimeout |
| 6 モデル重み・結果JSONキャッシュ | 未実施 | snapshot保存は確認したがオフライン再推論・結果再利用効果は未確認 |

再開時は既存Secretを維持したまま、L4容量が利用できる時にTest 3を実行する。
403等のモデル認可エラーが出た場合にだけ、本人がHFアカウントでCommunity-1条件への
同意・トークンRead権限を確認する。現時点で追加トークン入力や本人PC操作は不要。
Test 3成功後、Test 4と6を行い、実際の話者切替えと照合する。
Test 5も独立して再実行する。地域固定・他GPU・他モデル・CPU推論へは変更していない。
残りを全て満たすまでStage 1完了としない。

実行run：https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41001086758
OFF run：https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41002514566
ASR artifact：https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41001086758/artifacts/12953802803
OFF artifact：https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41002514566/artifacts/12954326457
