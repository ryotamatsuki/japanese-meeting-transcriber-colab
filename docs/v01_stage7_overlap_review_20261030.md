# Stage v0.1-7 — 重複発話の要確認UIと実環境検証

**実施日：2026-10-30 / 状態：Stage 7の機能・単一録音E2E完了、v0.1公開判定はNo-Go**

## 目的

Stage 6で重複発話区間を保持したCommunity-1通常出力が独立DER/JERを改善した。ただし、その出力を単語へ自動割り当て直すと誤検出により文字起こしを悪化させる危険がある。本段階は、検出した重複発話を**人間が確認するための候補**としてWeb画面へ接続し、既存のASR・排他的話者帰属を変更しない。

## 変更内容

- `transcriber.processor.Config.overlap_review` は既定で `False`。従来Colab・Stage1 CLI・研究評価では動作を変えない。
- 限定ベータの`beta_modal.py`では話者分離を有効にした場合にだけ`overlap_review=True`を設定し、既存のCommunity-1推論から得られる`speaker_diarization`（通常出力）で同時発話候補を抽出する。
- `transcriber/quality.py`の`find_overlap_windows`を利用し、最短0.20秒の2話者以上の同時活動候補を生成する。新モデル追加、再認識、ASRビーム変更、単語への自動話者再帰属は**行わない**。
- 候補は`beta/review.py`で検証・時刻ソート・最大1,500表示・発話者ID非公開として整理する。モデル推定であり、人手の正解ではない。
- Web画面では区間再生、発言行への移動、確認済みフラグの登録・解除、再読込後の継続を提供。確認済みフラグは`review_checked.json`へ独立して永続化し、元の文字起こしや4種類の書き出しには自動反映しない。
- 新API：認証必須`GET /api/jobs/{id}/review`、認証・CSRF必須`PUT /api/jobs/{id}/review/{window_id}`。旧録音・話者分離OFFでは安全な空レスポンス。
- Model`speaker_id`を実在の個人識別情報として提示しない。

## 証拠と実測

### 回帰・ブラウザ操作

- [Chromium QA Run 41053529713](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41053529713) **PASS**。非機密の合成WAV、2つの模擬重複候補を使い、ログイン、表示、チェック登録、再読込による永続化、該当発言行へのジャンプ・フォーカス、テキスト編集・保存、チェック解除を実ブラウザで確認。
- `tests/test_beta_overlap_review.py`：候補検証、サニタイズ、後方互換性、認証・CSRF、データ保存・削除、原文不変を検証。
- `tests/test_evaluate_overlap_review.py`：複数話者区間の併合・重複計測・不正時刻拒否を検証。
- 新JSは`node --check`をCIに追加。CSPの`script-src 'self'`を緩めず、Playwrightの`expect(locator)`でテスト。
- GitHub CI：全テスト成功。

### 公開日本語音声・Modal A10

- [隔離環境のWeb→GPU→要確認UI API E2E Run 41053310600](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41053310600) **PASS**。対象は [IngCrowd 日本語テーマ別対話01](https://huggingface.co/datasets/IngCrowd/japanese-themed-dialogue) の**CC BY-NC 4.0・非商用研究評価**。元音声・本文は保存／アップロードしない。
- 11分15.864秒（675.864秒）、MP3入力4,055,444 bytes、A10 pipeline 82.277秒、HTTP E2E 129.81秒、165発言、2話者、音声末尾まで完走。
- **モデル推定重複候補82区間**、モデルの重複検出49.422秒、人手ELAN正解の重複92.796秒、両者一致44.349秒。
- **時間ベース適合率89.7353%・再現率47.7919%（この1録音のみ）**。誤検出推定時間は5.073秒、未検出正解時間は48.447秒。評価用EAF SHA256：`c59daa71d0ffa34e50b4c532d33f5c0d2a51ceaa8aea4435a68a87d924f61b32`。
- 認証拒否、静的ファイル、アップロード、GPUジョブ、生成候補、確認済み保存と解除、本文修正、ZIP出力、ファイル削除、試験専用Modal環境の削除まで全項目PASS。
- GitHub Actions証拠Artifact `12975422155` SHA256 `97e00f2f8693d8a62ee31ceb409f4c1d364a30f0628c328c881b1d8d27616d8e`。数値とテスト状態のみ保持、音声・全文なし。

## 採否判断

**機能実装・画面・単一録音E2Eは完了。重複候補表示機能は限定ベータの採用候補として保持する。**

ただし候補表示は誤検出を含み、重複発話時間の**半分程度を取りこぼす**。候補がない区間を「重複なし」と判断してはいけない。今回の適合率・再現率は単一の日本語2話者対話であり、一般化できない。

最終文字起こしのCER・cpCER・話者属性精度は本Stageで改善していない。**元のASRと排他的な話者割当てを維持**し、利用者が判断して修正する。自動重複転写や別モデルの追加は、複数録音での最終出力品質比較後とする。

## 残るv0.1公開ゲート

- 日本語の実会議録音に対する独立したCERおよび話者対応付き誤差の検証、2〜4人会議への一般化。
- 長時間Web経由処理の不定期保存失敗の根本原因検証・連続再現性。
- 実運用の費用上限／請求通知／24h自動削除の監査、使用者のセキュリティ要件に対する最終確認。
- 実利用者による作業時間削減の計測。**いずれも終わるまではRelease No-Go**。

