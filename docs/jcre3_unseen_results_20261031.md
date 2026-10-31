# J-CRe3新規ソース評価：3本の実A10処理完了

## 結論と適用範囲

許諾と人手参照を確認して取得した日本語J-CRe3の3録音をModal A10で実処理した。既存IngCrowd10録音と別ソースであり、このプロジェクトでは初めて評価する。モデル学習時の未見性は確認できない。家庭内作業を演じる2人対話であり、実際の行政会議・3〜4話者会議ではない。原WAVの移送に失敗したため、公式BoxプレビューMP3を使用した。会議データ確保の要件は部分達成、商用受入は未達。

配布元: https://github.com/riken-grp/J-CRe3/tree/61814236abf16258c7fb9778e32e660c1602ecfa

データセットのREADMEはCC BY-SA 4.0を明記。音声のクラウド処理を禁じる追加条件は確認されず、ライセンス・帰属を保持した同一パッケージをModalへ送った。論文のライセンスをデータセットへ転用していない。人手が各発話を書き起こし、時刻を付与したことは原著のデータ構築節で確認した。

出典: Nobuhiro Ueda et al. (2024), *J-CRe3: A Japanese Conversation Dataset for Real-world Reference Resolution*, LREC-COLING, pp.9489–9502. https://aclanthology.org/2024.lrec-main.829/

事前選択・変換・参照注記の扱いは[jcre3_unseen_protocol_20261031.md](jcre3_unseen_protocol_20261031.md)、各ファイルのSHA-256と参照パスは[manifest](jcre3_unseen_manifest_20261031.json)に固定。実音声・人手参照・認識全文は公開リポジトリやActionsログへ出していない。参照本文をQwenへ入力せず、音声切断にも用いない。

## 最終の実GPU結果

Qwen3-ASR-1.7B、ForcedAligner-0.6B、Community-1 exclusive、期待話者2、30秒低エネルギー分割目標、contextなし。CPUモックの結果ではない。

|録音ID|処理|音声秒数|cpCER|平坦化CER|話者分離秒|ASR・評価秒|
|---|---|---:|---:|---:|---:|---:|
|20220302-56130322-0|PASS|69.474|51.402%|12.617%|7.468|4.728|
|20220303-56130205-1|PASS|147.400|44.850%|3.322%|4.604|5.670|
|20220304-56132112-1|PASS|161.147|41.137%|7.358%|5.594|6.870|

合計59発言、参照814正規化文字、デコード後音声378.021秒。cpCER中央値44.850%、文字数加重micro cpCER45.209%、平坦化micro CER7.248%。録音1の無音末尾にも認識語があり、未発話挿入の疑いは残る。cpCERと平坦化CERの差は話者帰属を重点診断すべき根拠になるが、話者分離だけが全誤差の原因と断定しない。時刻アラインメント・参照との時間同期も切り分けが必要。従来IngCrowdと録音・参照が違うため、26.812%などとの直接比較で改善・悪化を判定しない。

3本の小規模な同一コーパス評価から行政用語精度・商用品質・有意な改善を主張しない。原録音の話者はコーパス全体でも限られている。今回結果を見た3本は、以後の調整では開発データとして扱い、再び独立受入データと呼ばない。

## 障害・修正・再試験

1. 初回はCPU受付のremote import不具合で入力待ちタイムアウト。GPU未起動。クライアント専用image factoryのimportをmodal.is_local()で制限し、欠落依存を再現するCPUテストを追加した。
2. 次の実GPU実行では3本中2本成功。録音2がASR/alignment段階でValueError。失敗試行の数値を[initial_failed_trial.json](metrics/jcre3_unseen_20261031/initial_failed_trial.json)に残した。成功2本のみの中央値を全体評価と扱わない。
3. CPUで公式qwen-asr==0.0.6の分割を再現し、1秒未満の末尾を上流が0.5秒へパディングし、infer_chunkの最小1秒条件で拒否されると判明。研究runnerで元波形から末尾を直前区間へ統合した。38秒上限を超える場合は境界を移す。全サンプルが一度ずつ残ることをfixtureで検証し、参照由来の無音除去や語の削除で回避していない。モデル重みは不変。
4. 上記修正後に同一ハッシュの3本すべてを実A10で再実行し、3本完了をassertした。最後の録音では既存のbounded alignment retryが1回動作した。
5. modal app stopは非対話CLIに--yesが必要だった。修正後の停止・入力削除ステップはともにsuccess。専用入力Volumeだけを操作し、モデルキャッシュや他アプリは削除していない。

[最終実A10・後片付け Run 41177076789](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41177076789)

[初回CPU受付失敗 Run 41175645974](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41175645974)

[最初の実GPU・2/3成功 Run 41176213822](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41176213822)

最終実GPUコード: bafdb5ea19d50c917319a24eb71f06aebb9dd01c。固定された研究専用アプリ名: kiroku-jcre3-unseen-pilot-20261031-01。公開Studioへのデプロイはしていない。

## 計測と費用

最終GPU関数内43.674秒（うちQwenロード8.728秒）。失敗を含む2回の実GPU関数内合計87.400秒。2026-10-31に公式料金表 https://modal.com/pricing で再確認したA10単価$0.000306/秒による計算値は合計$0.02674。実請求ではなく、CPU・メモリ・起動・待機・受付・Volume等を含まない。研究反復の全時間を製品1回の価格へ換算しない。

2026-10-31の試験中に管理画面を再確認: Usage limit $30、Spend limitは未設定（Set spend limit表示）、残クレジット$24.86、当期$5.14 credits / $0 charges。設定変更なし。Workspace全体の残高差分は本試験の確定請求とは扱わず、無料クレジットと請求上限は別として記録する。

## 再現と次の判断

非公開の固定入力ZIPはサイズ5670036 bytes、SHA-256 ec83653e440a2707781443298549c3f92cb22c1930294eec10f9a83c03f15d31。3組のpreview.mp3/reference.txt、manifest.json、ATTRIBUTION.txtを含む。原本WAVと異なることを維持する。

1. ソースrevision・公式test.id・manifestで同一録音と参照を確認する。
2. 現在の既存Secretsを使い、専用アプリをmodal deploy modal_qwen_unseen_jcre3.pyで準備する。料金上限と残高をその時点で確認する。
3. 専用intakeのPUT /ingestへ固定ZIPを送る。受付は固定ハッシュ・サイズのみ許可し、本文のダウンロードやGPU起動ルートを持たない。
4. modal run modal_qwen_unseen_jcre3.py --output numeric.jsonを1回実行する。公開ログ・成果物は数値のみ。
5. modal app stop --yes kiroku-jcre3-unseen-pilot-20261031-01 と、modal volume rm kiroku-jcre3-unseen-inputs-20261031-01 /eval.zipでこの試験だけを終了する。

一回限りの起動jobは実行開始後のcommit 2837d8e15ddf8a74159897a318185922517963a6でCIから削除済み。後続CIはGPUを自動起動しない。

次は、本文の追加推論を一律に増やす前に話者帰属と時刻誤差を診断する。実際の許諾付き日本語会議と人手逐語参照、行政固有名詞、独立3〜4話者、利用者の修正時間・残存誤りは未評価。今回のJ-CRe3をそれらの代替としてPASSにしない。
