# Japanese Meeting Transcriber — Stage 1 実装・検証報告

検証日：2026-10-29（日本時間）。**判定：Stage 1未完了。Modal上の実GPU推論は未検証。**
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
| TorchCodec | 0.8.1+cu128（torch2.9対応） |
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

Draft PRを作成してレビュー可能にする。mainへのマージは行わない。
コミットIDはGit履歴、PR URLはこの作業の最終回答を参照（コミットの自己参照を避ける）。
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
| Draft PR | 最終回答の作成結果参照 |
