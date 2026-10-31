# Kiroku Studio：Community-1／Sortformer v2.1／Nemotron 3 実GPU比較（2026-10-31）

**評価結果：Sortformer v2.1 と Nemotron 3 は有望な研究候補。公開アプリの既定モデルは変更せず、リリース判定は No-Go。**

## 実験の再現性

- 正式な最終実行：[GitHub Actions #41194877641](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41194877641) **PASS**、Qwen凍結3件、NVIDIAの2モデル×3録音とも実GPU A10上で実測完了。旧NeMoでのNemotron読み込み失敗は、Transformersの別実装に切り替え、人工音声6秒の単体確認を経て解決。
- 音声は J-CRe3（CC BY-SA 4.0）の2話者×3件の**すでに研究開発に使用した演技による家庭作業会話**。未見実会議ではない、独立標本ではない、実運用の編集時間は未測定。音声は原WAVではなく公式BoxのプレビューMP3。
- 3音声＋3人手ELAN参照のSHA-256を既存manifestと個別照合。Qwen3-ASR-1.7B、Qwen3-ForcedAligner-0.6B、Community-1は固定構成で再実行し、ASR文字列・単語時刻と人手参照、Community区間を新設の非公開Modal Volumeに一時保存。基準cpCER/DERは前回と一致しなければ処理停止。
- 新モデルは同じ16kHzモノラルPCM入力で推論。Sortformer v2.1: NeMo toolkit 3.0、公開モデル `nvidia/diar_streaming_sortformer_4spk-v2.1`、最大4話者、30.4s streaming buffer設定。Nemotron 3: Transformers offline processor `nvidia/Nemotron-3-Diarization`、最大8話者、フレーム10ms。いずれも話者数は**自動推定**、元Communityは2話者を指定するため、この差を評価上明記。
- **認識本文と単語時刻は同一**。話者帰属は3モデル共通の、重複に対応した最大区間重複＋最大1.2秒最近話者補完。話者ラベルのグローバル置換に対応するcpCER。DER/JERは同じ人手区間、collar 0秒、重複音声も評価。人手参照はGPUモデル入力に使用せず、事後評価のみ。
- 商用可能性：Sortformer v1はCC-BY-NCのため研究候補から除外。v2.1はNVIDIA Open Model License、Nemotron 3はOpenMDW 1.1。実際の製品配布・モデル再配布に先立ちNoticeと利用条件を別途実装・確認する。

## 実測値：元Qwen文字列固定

|音声ID末尾|参照文字数|Community cpCER|Sortformer cpCER|Nemotron 3 cpCER|Community DER|Sortformer DER|Nemotron 3 DER|
|---|---:|---:|---:|---:|---:|---:|---:|
|20220302-…-0|214|51.402%|13.084%|13.084%|33.454%|16.184%|16.846%|
|20220303-…-1|301|44.850%|3.987%|3.987%|34.265%|17.680%|19.498%|
|20220304-…-1|299|41.137%|10.702%|9.699%|27.574%|10.281%|10.976%|
|**全録音micro cpCER**|**814**|**45.209%**|**8.845%**|**8.477%**|—|—|—|

対応する **JER**：
- 録音01：Community 43.814%、Sortformer 15.959%、Nemotron 3 17.108%。
- 録音02：Community 49.852%、Sortformer 15.022%、Nemotron 3 17.209%。
- 録音03：Community 39.491%、Sortformer 9.995%、Nemotron 3 10.367%。

文字数加重cpCER原始編集数：Community **368/814**、Sortformer **72/814**、Nemotron 3 **69/814**。Sortformerは対Community **-36.364ポイント**（相対誤り削減80.435%）、Nemotron 3は **-36.732ポイント**（81.250%）。NemotronのSortformerに対する追加差は**-0.369ポイント、3文字分**のみ。Sortformerは全3録音でNemotronよりDER低下（0.662、1.819、0.695ポイント差）。この3件では両モデルとも**話者混同時間0秒**だが、miss/FAは残る。人手区間のオラクルを含むモデル選択、録音3件に対する有意差検定は不適切。

全体の flattened CER は固定Qwenテキストのため従来 **7.248%のまま**。今回の改善は「誰が話したか」の帰属結果に由来し、ASRの文字認識自体が改善したものではない。

## 性能・再現・費用上の注意

GPU内部モデルロード時間：Sortformer 5.390秒、Nemotron 3（Transformers）3.493秒。各3録音の推論時間：Sortformer 1.109 / 0.559 / 0.579秒、Nemotron 0.143 / 0.207 / 0.210秒。**これらはモデル内部の計時値で、GPUのモデルイメージビルド時間、音声取得、Qwen前段、デプロイ、ネットワーク、請求額、編集者の操作時間を含まない。** モデル間の同一条件なE2E時間比較でもない。特にNeMo streaming bufferとTransformers offline実装は異なるため処理時間を単純な高速化率として宣伝しない。

数値のみArtifact **#13040815412**、SHA256 **b24426065047fe6bd8f5fc0972ae8e0443dad03366f8d0e59cf8d77541b67163**、実行リンク [#41194877641](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41194877641)。専用Modal App停止、音声ZIP＋凍結Qwen/人手原稿3JSON＋PCM WAV3ファイルを確認後に**全7件個別削除**、GitHubには数値JSONだけ保存。公開アプリや既存モデルキャッシュを変更せず。

## 採否判断

- **Sortformer v2.1を研究上の比較基準として維持。** 自動話者区間の改善は再現したが、Nemotron 3のわずか3文字分のcpCER改善は統計的優位性を意味せず、DERは全3件でSortformerの方が良好。
- Nemotron 3も8話者を扱える商用可能な候補として残す。4話者以上と雑音下の実会議では別の順位があり得る。アルゴリズムの遅延・メモリ・E2E時間・配布ライセンスも評価する。
- **次に必要**なのは、未見の実際の日本語会議（2、3、4、5〜8話者、近接/遠距離/重複/背景雑音を含む）の使用許諾が確認された録音と、別々に作られた人手逐語・話者区間参照。会議単位の対応比較と編集者の修正時間・修正後重要語の正確性を測る。
- 以前の3件を何度繰り返しても独立の証拠にはならない。**v1 Release No-Go**、本番モデル置換なし。

コード：`scripts/diarizer_nvidia_matched_eval.py`、`modal_nvidia_frozen_qwen.py`、`modal_nvidia_diarizer_headtohead.py`。歴史的な失敗とSortformer単独の結果は `docs/nvidia_sortformer_ja_actual_gpu_20261031.md` に保持。
