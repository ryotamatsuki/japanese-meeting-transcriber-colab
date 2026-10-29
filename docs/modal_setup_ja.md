# Stage 1：Modal L4での検証手順

現状は実装・オフライン回帰テストまで。GPU動作保証ではありません。
結果：[Stage 1報告書](modal_stage1_report_ja.md)。公開API・UI・常駐サービスは作りません。

## 1. 認証と依存関係

```bash
python -m venv .venv-modal
source .venv-modal/bin/activate
python -m pip install modal==1.4.3
modal token new
```

Modalアカウントの残高・予算・課金設定を本人が確認してください。
この手順はGPUを消費します。課金の有効化や追加支出の承認は自動で行いません。
Modal認証情報をリポジトリやチャットに貼らないでください。

話者分離を使う場合だけ、[Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)の利用条件に同意し、Readトークンを用意します。
Modal DashboardのSecretsで **transcriber-hf** を作り、キー **HF_TOKEN** に登録します。
トークンをCLI引数・コード・ログに記載しないでください。ASR単独・話者分離OFFではSecretの作成自体が不要です。
Community-1ロード時に権限・利用条件・ネットワーク・依存関係のエラーを表示します。Secret未作成ならModalが開始前にエラーを返します。

イメージはPython 3.11、CUDA 12.8対応PyTorch 2.9.1／cuDNN 9、faster-whisper 1.2.1、pyannote.audio 4.0.7、PyAV 18.1.0。
`requirements-modal.lock` に推移依存も固定しています。PyTorchとTorchCodecの対応表に合わせTorchCodec 0.8.1を使用します。
Modalイメージビルド時にpip checkと全ライブラリのimportを実施し、pip freezeを証拠に保存します。実行ごとのpip installはありません。
OSパッケージ・ベースイメージとモデルrevisionは完全固定していないため、バイト単位の環境再現は未保証です。
実GPUでの整合性確認後、取得したモデルsnapshotとビルド情報を基準に確定してください。


Windows PowerShellで実行する場合は、上記の仮想環境作成・有効化を次に置き換えます。

```powershell
py -3.11 -m venv .venv-modal
.\\.venv-modal\\Scripts\\Activate.ps1
python -m pip install modal==1.4.3
modal token new
modal token info
```

認証にはブラウザでのログインが使えますが、`modal run` 自体はPythonとModal CLIが動く端末（ローカルPC、Codespaces等）から実行します。ModalのWebダッシュボードを開いているだけではStage 1のGPU検証は開始されません。

## 2. テスト音声

`local_audio/two_speakers.wav` に、**公開可能な日本語を2人が交互に発話する30〜60秒程度の自作録音**を置きます。
庁内会議、個人名、非公開情報は使わないでください。Stage 1のアップロード上限は25 MiBです。
無音・正弦波で代用しません。公開データを使う場合は出典・ライセンス・利用条件を別途記録します。

次の情報をローカルに記録します（GitHubには入れません）。

- 音声の作成日、権利根拠、SHA256、音声長、実際の話者数
- 正解の日本語発話と、どちらがいつ話したかの区間（匿名A/B）
- 例：Aが冒頭、Bが次、Aが最後。各人複数秒の発話を確保する

人数だけで精度を判定せず、文字列・話者切替え・誤割当てを原音声と照合します。

## 3. 実行（順番を守る）

```bash
# Test 1：L4・CUDA tensor演算・CTranslate2・importを確認
modal run modal_app.py --stage gpu --output local_runs/01-gpu

# Test 2：Whisper large-v3単独。HF Secret不要
modal run modal_app.py --stage asr --audio local_audio/two_speakers.wav --output local_runs/02-asr
python scripts/validate_run.py local_runs/02-asr/run-1.zip --stage asr

# Test 3：Community-1単独。まず人数を固定せず推定人数を比較する
modal run modal_app.py --stage diarization --audio local_audio/two_speakers.wav --output local_runs/03-diar
python scripts/validate_run.py local_runs/03-diar/run-1.zip --stage diarization

# Test 4：統合（TXT/CSV/SRT/JSON/ZIP）。必要なら --expected-speakers 2
modal run modal_app.py --audio local_audio/two_speakers.wav --output local_runs/04-full
python scripts/validate_run.py local_runs/04-full/run-1.zip

# Test 5：HF Secretを参照しない、話者分離OFFの別Function
modal run modal_app.py --audio local_audio/two_speakers.wav --no-diarization --output local_runs/05-off
python scripts/validate_run.py local_runs/05-off/run-1.zip --off

# Test 6a：モデル重みの再利用。各回の結果フォルダは別。
# 2回目はHF Hubをオフラインにし、実際にモデルを再ロード・再推論する。
modal run modal_app.py --audio local_audio/two_speakers.wav --repeat 2 --output local_runs/06-model-cache

# Test 6b：同一結果フォルダでASR・話者分離JSONの再利用。
modal run modal_app.py --audio local_audio/two_speakers.wav --repeat 2 --result-cache --output local_runs/07-result-cache
```

`--glossary '用語1、用語2'`、`--expected-speakers`、`--min-speakers`、`--max-speakers`、`--language ja/auto/en`を指定できます。
large-v3／CUDA／float16は固定です。GPU不調時にCPUや小型モデルへフォールバックしません。
既定の総処理タイムアウトは900秒、同時コンテナは1、リトライは0、CPUは2物理コア、ホストメモリは8 GiBです。
1つの呼出し終了後はsingle-use containerを破棄します。最大2回に制限し、長時間ベンチマークはしません。

## 4. 証拠の読み方

各出力先に `evidence.json` と推論結果の `run-N.zip` が保存されます。音声本文は標準出力に表示しません。
JSONにはGPU名、CUDA、cuDNN、全主要バージョン、pip freeze、モデルsnapshot、ロード時間・推論時間・統合出力時間を記録します。
`model_downloads_disabled=true` の回が成功し、result cache hitがfalseならモデルキャッシュの証拠です。
`asr_result_cache_hit`・`diarization_result_cache_hit` がtrueなら結果キャッシュの証拠です。
結果キャッシュhitの回にはモデルロード・推論時間がなく、処理速度比較に混ぜません。

GPUメモリはnvidia-smiによる200ms間隔の観測ピークです。CTranslate2も含みますが、サンプル間の瞬間最大値は捉えられません。
`gpu_memory_sample_errors` が0か確認します。PyTorch allocatorだけの値で全体の最大使用量を主張しません。
`client_wall_seconds` はビルド・キュー・転送を含み、コンテナ起動時間ではありません。
純粋なコンテナ起動時間と請求対象時間はModal Dashboardのログ・メトリクスで別途確認してください。
Whisper推論にはジェネレータの全消費、話者分離にはwav変換を含みます。
音声長に対する速度は、初回の `audio_seconds / pipeline_seconds` などで比較します（初回ダウンロードの有無を注記）。

ZIPの構造検査は認識精度の合格判定ではありません。
`pyannote_話者区間.json` と原音声の正解区間を比較し、人数、切替え時刻、誤割当て、短い相づちを記録します。
Colab版との精度比較は同じ音声・設定で別途実行し、双方のモデルsnapshotと出力を照合してください。

```bash
# 実測されたコンテナ稼働時間が分かれば指定。未指定はFunction内実測時間による限定的概算。
python scripts/estimate_cost.py local_runs/04-full/evidence.json --billable-seconds SECONDS
```

概算は[公式料金](https://modal.com/pricing)（2026-10-29参照）のL4、CPU、8 GiBメモリに基づきます。
Volumeは `--model-gib` と `--retention-days` で加算可能。無料枠・ネットワーク料金・ビルド費用等は別扱いです。


### GPU実行証拠の構造検査（追加）

ZIPの構造検査とは別に、`evidence.json` が本当にL4/CUDA環境を記録し、指定ステージでモデルロードと推論が実行されたか、GPU使用量・経過時間・キャッシュ状態を機械的に点検します。

```bash
python scripts/validate_evidence.py local_runs/01-gpu/evidence.json --stage gpu
python scripts/validate_evidence.py local_runs/02-asr/evidence.json --stage asr
python scripts/validate_evidence.py local_runs/03-diar/evidence.json --stage diarization
python scripts/validate_evidence.py local_runs/04-full/evidence.json --stage full
python scripts/validate_evidence.py local_runs/05-off/evidence.json --stage full --off
python scripts/validate_evidence.py local_runs/06-model-cache/evidence.json --stage full --cache-mode model
python scripts/validate_evidence.py local_runs/07-result-cache/evidence.json --stage full --cache-mode result
```

判定は証拠JSONの**構造と内部整合性**についてのみです。実際のクラウド実行を確認するにはModal Dashboardの実行ログ・課金メトリクスを照合します。音声認識精度や話者分離精度を保証するものでもありません。GPUが未起動の場合、検証すべき実測JSON自体が存在しないのでPASSにはなりません。

## 5. データ保存と削除

- **/models**：専用Modal Volume `meeting-transcriber-models-v1`。Whisper・HFモデル重みのみ。HF_TOKENを保存するlogin処理はしません。
- **入力・結果**：GPUコンテナのTemporaryDirectory。リモート処理終了時（例外時も）に削除。結果は呼出し元にZIPとして返します。
- **結果キャッシュ**：同一呼出し内で2回処理するときだけ保持。別呼出し間の結果永続化はStage 1では実装しません。
- **ローカル**：`local_audio/` と `local_runs/`。検証後、必要な証拠を手元に保管して不要データを削除してください。
- **モデル保存を終了**：Modal Dashboardから専用Volumeを削除できます。他アプリと共有しないでください。

元音声はZIPに含めません。例外ログにはライブラリ由来のファイル名などが含まれる場合があるため、公開可能なテスト音声と匿名ファイル名を使用してください。
モデル初回ダウンロード中のライブラリログは表示される場合があります。HF HubのHTTP認証エラーはトークンや認証URLを出さずに説明する例外に置き換えています。CUDA・依存関係などの他の例外は原因調査のため伝播させます。

## 6. オフライン回帰テスト

```bash
python tests/check_notebook.py
python -m unittest discover -s tests -p 'test_*.py' -v
```

これらはモデルをダウンロードせず、モックを使った検査を含みます。GPU推論の代わりにはなりません。

## 参考（公式）

- https://modal.com/docs/guide/gpu
- https://modal.com/docs/guide/cuda
- https://modal.com/docs/guide/images
- https://modal.com/docs/guide/volumes
- https://modal.com/docs/guide/secrets
- https://github.com/SYSTRAN/faster-whisper#gpu
- https://github.com/meta-pytorch/torchcodec#installing-torchcodec
- https://pytorch.org/get-started/previous-versions/


## CLI接続とブラウザログインを切り分ける（2026-10-29追記）

ブラウザにログイン済みでも、この実行環境では`modal token new`が
認証URLの発行前に`Could not connect to the Modal server.`で停止した。
`api.modal.com`の名前解決失敗を確認しており、HF Secret登録とは別の問題である。
ブラウザCookieやAPIキーをコピーして接続問題を回避しない。
Modal Notebooksもブラウザでは提供終了と表示され、新規実行の代替には使えない。

通常接続できる本人PCでは、既存のWindows手順で作業ブランチを更新し、
`python -m modal token new`から認証する。Test 1の成功を先に確認する。
認証トークンはSDKに保存させ、チャットやログに表示しない。
HF Secretとモデル利用条件は話者分離用であり、Test 1・ASR・OFFには不要。
