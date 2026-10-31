# Stage 19 — 3〜4話者の自然な日本語会議の評価準備

検証用の音声・人手逐語原文・話者RTTMを**権利者から許可された非公開作業環境内**で用いる。現時点では未入手、モデル精度は未測定。

資料候補：

- 国立情報学研究所 RWCP-SP01。4名以上の模擬会議7件、録音は単一マイク等あり。研究用途・無償だが申請と審査が必要。利用の権限は本人／部署に限る。 https://www.nii.ac.jp/dsc/idr/speech/submit/RWCP-SP01.html
- Qlean Datasetの日本語ビジネス会話（2〜3人）、約25時間の3話者音声があるが、利用条件と費用の確認が必要。 https://qleandataset.visual-bank.co.jp/en/datasets/speech-meetings

`scripts/evaluate_multispeaker_ja.py`は許可済みの独立した人手確認済みJSON発話注釈とRTTMを要求し、最新の録音結果ZIPとのcpCER/DER/JERを比較する。音声、原文、氏名はGitHubにアップロードしない。RTTM未提供ならDER/JERは`null`で、合格と見なさない。

使用例：

    python -m scripts.evaluate_multispeaker_ja --reference /private/reference.json --human-rttm /private/reference.rttm --archive /private/result.zip --output local_runs/aggregate_metrics.json

評価要件：3人と4人の独立会議、各3件以上、語句の重複を含み、音源の権利と注釈方法を記録。元の2話者IngCrowdの単純混合を自然な4話者会議として宣言することは認めない。

**実測未完了。限定ベータ公開はNo-Go。**
