# Stage 21 — 実利用者による文字起こし時間短縮の認定基準

実利用者による5つ以上の独立録音を用い、人間の手動完了とAI支援完了をクロスオーバー条件で比較する。両者とも**人手が完成品質を確認**したものに限定し、初回操作・推論待機・修正・音声確認・最終確認にかかった経過時間を測る。AI方式のみ品質を妥協することは認めない。

ローカル測定結果のJSONは`method: "human_timed_crossover"`、`pairs`に録音ID・manual_seconds・assisted_seconds・両結果のquality_pass・順序を含む。少なくとも各順序2録音、全5録音以上。原音声と発言文は保存・公開しない。

`python -m scripts.evaluate_human_time_study --observations /private/study.json --output local_runs/study_report.json` で中央値50%以上の短縮かを判定する。測定されていない録音・推定時間・GPU処理時間だけを根拠に合格と主張してはいけない。CPU単体テストはあくまで検算である。

**現時点：実利用者の測定はないため効率ゲート未認証、Release No-Go。**
