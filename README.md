# Japanese Meeting Transcriber for Google Colab

**Google Colabで日本語の会議音声を文字起こしし、必要に応じて話者を分離するノートブックです。** ファイル名を書き換える必要はありません。音声ファイルを選択してセルを実行するだけで、TXT / CSV / SRT / JSONを出力します。

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ryotamatsuki/japanese-meeting-transcriber-colab/blob/main/notebooks/meeting_transcriber.ipynb)

> **公開版の注意**：研究・学習・個人での使用を想定したサンプルです。音声認識・話者分離は誤ることがあります。機密音声、個人情報を含む録音は、クラウド環境へのアップロードが許可されている場合にのみ利用してください。実際の発言内容と話者は原音声で確認してください。

## 主な機能

- **Whisper large-v3**（`faster-whisper`）による日本語音声認識
- **pyannote.audio Community-1** による任意の話者分離
- MP3 / M4A / WAV / FLAC / MP4などの入力（ffmpegで読み取れる形式）
- ファイル名・保存フォルダ名の**自動設定**、複数ファイルの順次処理
- TXT / Excel向けCSV / SRT / JSON / ZIP出力
- 専門用語の任意指定、話者数の任意指定
- 同じ音声・設定の再処理を避けるキャッシュ（Colabの一時領域に残っている場合）
- オプションでGoogle Driveに結果を保存

**対象**：Google Colab / GPUランタイム（T4推奨）。ローカルGPUは不要ですが、GoogleアカウントとColabの利用枠が必要です。モデルのダウンロードにはネット接続が必要です。

## 3ステップで使う

1. 上の **Open in Colab** をクリックし、`ランタイム → ランタイムのタイプを変更` で **T4 GPU** を選択します。
2. **①ライブラリのインストール**を実行します。**その後、一度 `ランタイム → セッションを再起動` してください。** 再起動後はインストールセルを再実行せず、次の「動作環境チェック」から順に進みます。
3. 設定セルを確認し、**③音声ファイル選択**から録音をアップロードして、残りのセルを実行します。最後にZIPをダウンロードできます。

詳しい説明：[日本語の利用手順](docs/usage_ja.md)。

**話者分離を使う場合**：Hugging Faceの[Community-1モデルページ](https://huggingface.co/pyannote/speaker-diarization-community-1)でアクセス条件に同意し、[Read権限トークン](https://huggingface.co/settings/tokens)を用意してください。Colabのシークレットに `HF_TOKEN` として登録できます。トークンをノートブックに直接書かないでください。話者分離なしで使う場合、トークンは不要です。

## 出力例

以下は**架空の発言**です。実在する会議の録音や文字起こし結果はこのリポジトリには含めません。

```text
[00:00:03 - 00:00:12] 話者1：それでは本日の議題を確認します。
[00:00:13 - 00:00:18] 話者2：資料の二ページについて質問があります。
```

- `*_文字起こし.txt`: 読みやすい発言記録
- `*_文字起こし.csv`: 時刻・話者・発言を列に分けた表（Excel向けUTF-8 BOM付き）
- `*_文字起こし.srt`: 字幕形式
- `whisper_asr.json`: 単語のタイムスタンプを含む認識結果（内部再利用用）
- `pyannote_話者区間.csv/json`: 話者分離オン時のみ
- `話者IDの対応表.csv`: 手作業で話者名を確認するための空欄付き表

## 精度と制約

- 「話者1」「話者2」などは**自動推定したラベル**です。氏名・役職の特定はしません。
- 話者の人数、短い相づち、重複発話、遠くの声、専門用語は誤る場合があります。
- 専門用語の入力欄 `GLOSSARY` は認識の**ヒント**であり、単語辞書による正解保証ではありません。
- **議事録のAI要約・自動校正は未実装**です。
- 音声はGoogle Colabのクラウド実行環境にアップロードされます。Whisperとpyannoteによる推論は基本的にその実行環境で行います（モデルファイル等は外部から取得）。ローカル処理や機密性の保証を意味するものではありません。
- 実行可能性はColab環境・GPU・依存ライブラリの状態によって変わります。最新版のColabでの全工程に対する継続的な動作保証はありません。

## トラブルシューティング

**`ImportError: cannot import name '_slice' from 'numpy._core.umath'`**

ライブラリのインストール中にNumPyが入れ替わり、実行中のPythonプロセスの読み込み状態と不整合になった場合に発生します。インストール後に**セッションを再起動**し、インストールセルを飛ばして環境チェックから実行してください。詳しくは[利用手順](docs/usage_ja.md)。

## プライバシー・安全性

- 実際の会議音声、文字起こし結果、トークン、認証情報はコミットしないでください。
- Colabの `/content` は一時領域です。成果物を保持する場合はZIPをダウンロードするか、**任意で**自分のGoogle Driveへ保存してください。
- 機密性のある録音については所属組織の規程・本人同意・関連法令を優先してください。
- 問題を報告する際は音声や個人情報をIssuesに添付しないでください。詳細は[SECURITY.md](SECURITY.md)。

## 使用技術とライセンス

このリポジトリ内の**自作コード**は[MIT License](LICENSE)で提供します。モデル・依存ライブラリはそれぞれ別のライセンス・利用条件に従います。モデルの重みは同梱しません。

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（WhisperをCTranslate2で実行）
- [Whisper](https://github.com/openai/whisper)（音声認識モデル、MIT）
- [pyannote.audio](https://github.com/pyannote/pyannote-audio)
- [Community-1 model](https://huggingface.co/pyannote/speaker-diarization-community-1)（CC BY 4.0、アクセス条件への同意が必要）

モデルやクラウドサービスの商用利用・配布条件は各提供元の最新情報を確認してください。

---

### English summary

A Google Colab notebook for **Japanese meeting transcription** using Whisper large-v3, with optional speaker diarization via pyannote Community-1. Select one or more audio files without editing file names. Exports TXT, CSV, SRT, JSON and ZIP. Requires a Google Colab runtime; speaker diarization additionally requires accepting the model's access conditions and providing a Hugging Face read token. **Restart the runtime after dependency installation.** Speaker labels are estimates, not verified identities. Do not upload confidential recordings unless authorized.
