# 2026-10-31 実GPU比較: Community-1 vs Sortformer v2.1 — 開発用J-CRe3

**研究用 / Draft PR #12 / 本番未変更 / 独立した実会議テスト未実施。**
実際のGPU比較: [GitHub Actions #41194301755](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41194301755)。

## 実験条件

- データはオープンライセンスJ-CRe3（CC BY-SA 4.0）の**既存開発用3録音**、演技による2話者の家庭内作業会話。行政・業務の実会議ではない、未見holdoutでもない。モデル学習への含有は不明。
- 元音声はRIKEN共有のpreview MP3（原WAVではない）。再取得した3音声/3人手ELAN参照の**個別SHA256**全6件が、過去固定manifestと一致した。
- Qwen3-ASR-1.7B・ForcedAligner-0.6B・Community-1を同一実音声で再推論し、文字列と単語時刻と人手参照を専用非公開Modal Volumeへ凍結。基準cpCERとDERは前回の固定試験と完全一致。異なるバックエンドに人手参照を渡さず、その推論終了後に指標のみ算出。
- NVIDIAモデルには全く同じ16kHzモノラルPCMを入力し、凍結済みQwen単語時刻と語彙を、**両バックエンドとも同じoverlap-safe最大重複+1.2秒最近話者fallback**で帰属。モデルごとのDER/JERは同じ人手発話区間、0.0秒collar、重複発話を除外しない設定。
- Community-1基準は2話者に固定。Sortformer v2.1は話者数を自動推定（最大4）。今回各録音2と判定した。話者数固定という条件の差は残るため別途評価が必要。
- Sortformer v2.1はNVIDIA Open Model Licenseを使用する研究用選択肢。非商用限定CC BY-NCのSortformer v1は製品候補から除外。後継Nemotron 3 (OpenMDW-1.1) はNeMo読み込みで `InstantiationException`、実精度は**欠測**で、ベンチマーク勝利と主張しない。

## 実測値（%、小さいほど良い）

|録音|参照文字数|Community cpCER|Sortformer v2.1 cpCER|Community DER|Sortformer DER|Community JER|Sortformer JER|
|---|---:|---:|---:|---:|---:|---:|---:|
|20220302-56130322-0|214|51.402|13.084|33.454|16.184|43.814|15.959|
|20220303-56130205-1|301|44.850|3.987|34.265|17.680|49.852|15.022|
|20220304-56132112-1|299|41.137|10.702|27.574|10.281|39.491|9.995|
|**micro cpCER**|**814**|**45.209**|**8.845**|—|—|—|—|

- cpCER edit counts: Community **110+135+123=368**、Sortformer **28+12+32=72**、同じ参照814正規化文字。**絶対36.364ポイント改善**、**相対80.435%誤り削減**。3録音全てcpCER改善。個々の分割文字列は保存・公開していない。
- この3件の話者混同時間はSortformerでは **0秒**、Communityは各7.0494、9.4530、9.7298秒。Sortformerにもfalse alarm（1.207、1.875、0.892秒）とmiss（5.201、7.302、4.600秒）が残る。
- Sortformer v2.1のGPU推論時間は録音ごとに1.620、0.910、0.901秒（モデルロード6.256秒）。これはGPU内部計測であり、NeMo imageビルド・準備・前段Qwen・アップロードを含む利用者E2E所要時間や費用ではない。
- Qwen本文固定なので、全体flat CERは従来の **7.248%** と同一。cpCER改善をCER改善とは言わない。
- 比較対象の**人手話者区間を使うオラクル**（同じ安全帰属）のcpCER 8.477%は製品性能ではない。Sortformerの8.845%が近いことは重要な診断だが、この3件への汎化を保証しない。
- DER優位だけでなく、後段cpCERの大きな改善が同時に認められた。ただし3録音・開発データのため統計的な独立信頼区間、実会議一般化、編集時間短縮は不明。

## 再現性・データ保護

- One-shot 実GPU Action: [#41194301755](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41194301755)、A10、再試行0、Qwen凍結成功、Sortformer推論3件成功、Nemotron 3モデル読み込み失敗を欠測として記録。途中で発生した初回Modalイメージ構築順序エラーは修正後再実行済み。
- GitHub Actions Artifact #**13039714642**（数値JSONのみ）、SHA256 **e7b046358f27e808c11e877da4c2220331f16089fb3ac5d7f240af30c7f8adc0**。音声・文字起こし本文・人手参照の内容は含まない。
- 最終クリーンアップstep成功: Modal研究アプリ停止、専用Volume `/eval.zip` と private `/frozen/*.wav` / `/frozen/*.json` の全7ファイルを個別削除。既存のモデル共有キャッシュ・本番Studioを変更しない。
- 正規化テキストのSHA、基準cpCER edits、baseline DER の厳密一致を試験中に確認。Source scripts: `scripts/diarizer_nvidia_matched_eval.py`, `modal_nvidia_frozen_qwen.py`, `modal_nvidia_diarizer_headtohead.py`.

## 研究上の判断

**Sortformer v2.1は有望な研究用候補と認める。** この時点でデフォルト話者分離器の変更はしない。未見の実際の日本語会議（2〜4話者以上、雑音・遠距離・かぶり発話を含む）を取得し、独立参照によるcpCER/DER/JER、推論E2E時間・実コスト・編集時間と修正後の固有名詞や数字の誤りを比較する。現データだけでv1合格にはしない。

Nemotron 3は現NeMo 3.0.0からモデルを読み込めない。別途Audioデータを使わないモデルロード専用診断で原因（バージョンやconfig）を確認し、NeMo-SpeechまたはHF Transformersで互換性が確認できた場合のみ同じ固定評価を再実行する。未知エラーを無断で本番処理に組み込まない。

**リリース判定 No-Go**。
