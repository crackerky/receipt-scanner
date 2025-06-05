# Receipt Scanner - セキュアなレシート処理アプリケーション

🔒 **GitHub Repository Secrets対応の安全なレシートスキャナー**

AIとOCRを活用した日本語レシート処理システムです。APIキーの安全な管理とセキュリティを最優先に設計されています。

## 🛡️ セキュリティ機能

- ✅ **GitHub Repository Secrets** 完全対応
- ✅ **環境変数による機密情報管理**
- ✅ **APIキーの安全な取り扱い**
- ✅ **レート制限** (デフォルト: 1分間10リクエスト)
- ✅ **入力検証** (ファイル形式・サイズ制限)
- ✅ **セキュリティヘッダー** 自動付与
- ✅ **非rootユーザーでのDocker実行**
- ✅ **ログから機密情報を除外**

## 🚀 クイックスタート

### 1. GitHub Repository Secrets の設定

リポジトリの **Settings → Secrets and variables → Actions** で以下を設定:

#### 必須のSecrets ⚠️
```
OPENAI_API_KEY=sk-your-actual-openai-api-key
```

#### オプションのSecrets
```
DATABASE_URL=postgresql://user:pass@host:5432/dbname
SECRET_KEY=your-jwt-secret-key
VITE_API_URL=https://your-api-domain.com
```

### 2. ローカル開発環境

```bash
# リポジトリをクローン
git clone https://github.com/crackerky/receipt-scanner.git
cd receipt-scanner

# バックエンド設定
cd receipt-scanner-app/receipt-scanner-backend
cp .env.example .env
# .envファイルを編集して実際のAPIキーを設定

# 依存関係インストール
poetry install

# Tesseract OCR インストール
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr tesseract-ocr-jpn
# macOS:
brew install tesseract tesseract-lang

# 開発サーバー起動
poetry run uvicorn app.main:app --reload --port 8000
```

```bash
# フロントエンド設定（別ターミナル）
cd receipt-scanner-app/receipt-scanner-frontend
cp .env.example .env.local
# .env.localファイルでVITE_API_URLを設定
npm install
npm run dev
```

### 3. 動作確認

1. ブラウザで `http://localhost:3000` にアクセス
2. レシート画像をアップロード
3. 自動的にデータが抽出されることを確認

## 🌐 デプロイメント

### Netlify (フロントエンド推奨)

#### 方法1: 自動デプロイ（推奨）

1. **Netlifyダッシュボードにアクセス**
2. **"New site from Git"をクリック**
3. **GitHubリポジトリを選択**
4. **ビルド設定は自動検出** (netlify.tomlで設定済み)
5. **環境変数を設定**:
   ```
   VITE_API_URL = https://your-backend-api-url.com
   ```
6. **Deploy siteをクリック**

#### 方法2: 手動設定

Netlifyダッシュボードで以下を設定:

**Build settings:**
- Build command: `npm ci && npm run build`
- Publish directory: `receipt-scanner-app/receipt-scanner-frontend/dist`
- Base directory: `receipt-scanner-app/receipt-scanner-frontend`

**Environment variables:**
```
VITE_API_URL = https://your-backend-api-url.com
NODE_VERSION = 18
```

### Railway (バックエンド推奨)

```bash
npm install -g @railway/cli
railway login
railway init
railway variables set OPENAI_API_KEY=sk-your-key
railway variables set ENVIRONMENT=production
railway up
```

### Vercel (フロントエンド代替案)

```bash
npm install -g vercel
cd receipt-scanner-app/receipt-scanner-frontend
vercel env add VITE_API_URL production
vercel --prod
```

## 🐳 Docker での実行

```bash
# バックエンドのみ
cd receipt-scanner-app/receipt-scanner-backend
docker build -t receipt-scanner-backend .
docker run -p 8000:8000 \
  -e OPENAI_API_KEY="your-api-key" \
  receipt-scanner-backend
```

## 📊 API エンドポイント

| エンドポイント | メソッド | 説明 | レート制限 |
|----------------|----------|------|------------|
| `/healthz` | GET | ヘルスチェック | なし |
| `/api/status` | GET | システム状態 | なし |
| `/api/receipts/upload` | POST | レシートアップロード | ✅ |
| `/api/receipts` | GET | レシート一覧 | なし |
| `/api/receipts/export` | GET | CSV エクスポート | なし |
| `/api/stats` | GET | 統計情報 | なし |

**API ドキュメント**: `http://localhost:8000/docs`

## 🔧 設定オプション

### 環境変数

**バックエンド:**
| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|------------|------|
| `OPENAI_API_KEY` | ✅ | - | OpenAI APIキー |
| `ENVIRONMENT` | ❌ | `development` | 実行環境 |
| `DEBUG` | ❌ | `true` | デバッグモード |
| `RATE_LIMIT_REQUESTS` | ❌ | `10` | レート制限リクエスト数 |
| `RATE_LIMIT_WINDOW` | ❌ | `60` | レート制限時間窓（秒） |
| `ALLOWED_ORIGINS` | ❌ | `http://localhost:3000` | CORS許可オリジン |

**フロントエンド:**
| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|------------|------|
| `VITE_API_URL` | ✅ | `http://localhost:8000` | バックエンドAPI URL |
| `VITE_APP_NAME` | ❌ | `Receipt Scanner` | アプリケーション名 |
| `VITE_ENVIRONMENT` | ❌ | `development` | フロントエンド環境 |

## 🧪 テスト

```bash
# バックエンドテスト
cd receipt-scanner-app/receipt-scanner-backend
poetry run pytest tests/ -v

# フロントエンドテスト
cd receipt-scanner-app/receipt-scanner-frontend
npm test
npm run lint
```

## 📈 モニタリング

### ヘルスチェック

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/api/status
```

### ログ確認

```bash
# Docker ログ
docker logs receipt-scanner-backend -f

# 開発ログ
tail -f logs/app.log
```

## 🛡️ セキュリティガイドライン

### ❌ 絶対にやってはいけないこと

1. **APIキーをコードに直接書く**
2. **`.env`ファイルをGitにコミット**
3. **フロントエンドにAPIキーを含める**
4. **本番環境でDEBUG=trueにする**

### ✅ 推奨される方法

1. **GitHub Repository Secrets使用**
2. **環境変数での設定管理**
3. **レート制限の適切な設定**
4. **定期的なAPIキー更新**

### 緊急時の対応

APIキーが漏洩した場合:

1. **即座にOpenAIダッシュボードでAPIキー削除**
2. **新しいAPIキーを生成**
3. **GitHub Repository Secretsを更新**
4. **使用量を監視**

## 🔍 トラブルシューティング

### よくある問題

#### OpenAI API エラー
```
Error: OpenAI API key not provided
```
**解決策**: GitHub Repository Secretsで`OPENAI_API_KEY`が正しく設定されているか確認

#### Tesseract エラー
```
TesseractNotFoundError
```
**解決策**: 
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-jpn
```

#### CORS エラー
```
Access-Control-Allow-Origin error
```
**解決策**: `ALLOWED_ORIGINS`環境変数を確認

#### レート制限エラー
```
Rate limit exceeded
```
**解決策**: 1分間に10回以下のリクエストに調整

#### Netlify デプロイエラー
```
npm error enoent Could not read package.json
```
**解決策**: 
1. リポジトリルートに`netlify.toml`が存在することを確認
2. Netlifyダッシュボードで Base directory を `receipt-scanner-app/receipt-scanner-frontend` に設定
3. Build command を `npm ci && npm run build` に設定
4. Publish directory を `dist` に設定

## 🤝 コントリビューション

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### 開発ガイドライン

- **APIキーは絶対にコミットしない**
- **セキュリティ関連の変更は特に慎重に**
- **テストを必ず実行してからコミット**
- **ドキュメントも併せて更新**

## 📄 ライセンス

MIT License - see [LICENSE](LICENSE) file for details.

---

**🔒 重要**: このアプリケーションはAPIキーなどの機密情報を安全に管理するために設計されています。セキュリティガイドラインに従って使用してください。

**💡 サポート**: 問題が発生した場合は [Issues](https://github.com/crackerky/receipt-scanner/issues) を確認するか、新しいIssueを作成してください。