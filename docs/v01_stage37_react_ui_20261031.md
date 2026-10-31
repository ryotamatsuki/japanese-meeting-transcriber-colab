# Stage 37 — React/TypeScript プライベートアルファUI（2026-10-31）

## 実装完了・非公開アルファのデプロイは未実施

- Streamlitは採用しない。React 19 + TypeScript + Vite + lucide-reactを用いたフロントエンドを `frontend/` に追加。現行FastAPI/Modal GPUワーカー・Qwen3-ASRの変更はなし。
- ダークサイドバー、アップロード領域、処理状態一覧、編集ワークスペース、話者カード、重複発話チェック、固定音声プレーヤー、検索、保存／ZIP出力、削除、モバイルレイアウト。
- 誤消去防止：未保存状態ではZIP出力を禁止し、ブラウザ離脱・ジョブ切替時に警告を表示する。60分級の大量発話には60行単位のページングを採用。
- 認証は既存HttpOnly Secure SameSite cookieとCSRFヘッダーを継続利用。React UIは同一オリジンで提供し、外部CDN/Google Analyticsは使わない。
- `beta/server.py` はビルド済み `beta/react_dist/index.html` が存在する場合だけReact HTMLを認証後に返す。各 `/ui/assets/...` ファイルも認証必須・拡張子制限・パストラバーサル拒否。ビルド未実施の場合は既存レガシーUIを安全に維持する。
- 配布: `cd frontend && npm install && npm run build` をModal deployより前に実行。GitHub Actionsは production bundle をArtifactとして公開するが、プライベート認証SecretやGPUジョブは含めない。

## 確認した証拠

- React TypeScriptビルド、`beta/server.py` の認証付きアセット回帰テスト： [Actions #41144729153](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41144729153) **SUCCESS**。
- デスクトップ/モバイル実Chromium、ダッシュボード表示、編集画面、テキスト編集、未保存時のZIP禁止、保存後出力許可、検索： [Actions #41144723935](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41144723935) **SUCCESS**。
- スクリーンショット（ダッシュボード、エディタ、モバイル）： [Actions Artifact stage37-react-browser-previews](https://github.com/ryotamatsuki/japanese-meeting-transcriber-colab/actions/runs/41144723935/artifacts/13020465534)。
- Chromium試験は架空の音声ファイル名・人工の発言テキストを返すモックAPIだけを使用。モデル品質や本物の音声同期、Modal実環境でのデプロイ完了を示すものではない。

## リリース前に未実施の事項

1. ビルド済みUIを実際の秘密認証付きModalアプリにデプロイし、アップロード→GPU→編集→ZIP→削除の端から端まで実音声で検証する。
2. 失敗した [Stage36](https://github.com/ryotamatsuki/ehime-kokubunsai-ai-poc/actions/runs/41142093001) はModalコンテナ内への試験実行ID受け渡し漏れを修正して再評価する。テストは失敗したが一時環境の削除成功。
3. Workspaceの支払上限はユーザーが30ドル枠設定済みと申告。ただし無料クレジットと実際のHard Spend Limitは別の仕様であり、前者だけから課金上限を推定しない。
4. 50%時間短縮と自然な日本語3〜4話者会議の精度認証はユーザー意向で後日実施する。これらの正式評価がない間は一般公開GOとはしない。

**現段階判定：React UI Build / Browser smoke GO、非公開実運用デプロイ未実施、一般公開Release NO_GO。**
