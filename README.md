# Receipt Scanner - セキュアなレシート処理アプリケーション

🔒 **GitHub Repository Secrets対応の安全なレシートスキャナー**

AIとOCRを活用した日本語レシート処理システムです。APIキーの安全な管理とセキュリティを最優先に設計されています。

## 🆕 新機能

### ✨ 最新アップデート (2025.06.05)
- **🔍 OCR処理の大幅改善**: 画像前処理（ノイズ除去、コントラスト調整、二値化）を追加
- **📝 レシート編集機能**: アップロード済みレシートの情報を後から編集可能
- **🗑️ レシート削除機能**: 間違えてアップロードしたレシートを削除可能
- **📅 日付自動補完**: レシートから日付が読み取れない場合、自動的に現在の日付を設定
- **⏰ アップロード日時表示**: レシートをアップロードした日時を記録・表示
- **🐛 デバッグ機能強化**: OCRテストスクリプトを追加

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

### 1. OCR環境のセットアップ

#### Tesseract OCRのインストール（必須）

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-jpn tesseract-ocr-eng
# 確認
tesseract --version
tesseract --list-langs | grep -E "jpn|eng"
```

**macOS:**
```bash
brew install tesseract tesseract-lang
# 確認
tesseract --version
tesseract --list-langs | grep -E "jpn|eng"
```

**Windows:**
1. [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)からインストーラーをダウンロード
2. インストール時に「Additional language data」で「Japanese」を選択
3. 環境変数PATHに`C:\Program Files\Tesseract-OCR`を追加

### 2. GitHub Repository Secrets の設定

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

### 3. ローカル開発環境

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

# OCRテスト（オプション）
python test_ocr.py [レシート画像パス]

# 開発サーバー起動
poetry run uvicorn app.main:app --reload --port 8000 --log-level debug
```

```bash
# フロントエンド設定（別ターミナル）
cd receipt-scanner-app/receipt-scanner-frontend
cp .env.example .env.local
# .env.localファイルでVITE_API_URLを設定
npm install
npm run dev
```

### 4. 動作確認

1. ブラウザで `http://localhost:3000` にアクセス
2. レシート画像をアップロード
3. 自動的にデータが抽出されることを確認

## 📱 主な機能

### レシートアップロード
- 画像から自動的に店名、日付、金額を抽出
- 日付が読み取れない場合は自動的に現在の日付を設定
- AI（OpenAI）またはOCR（Tesseract）で処理
- 画像前処理により認識精度を向上

### レシート管理
- **編集**: レシート一覧から編集ボタン（✏️）をクリック
- **削除**: レシート一覧から削除ボタン（🗑️）をクリック
- **CSV出力**: 全レシートデータをCSV形式でエクスポート

### データ分析
- 費目別の支出をグラフで可視化
- カテゴリー別の経費集計

## 🔍 OCRトラブルシューティング

### OCRが動作しない場合

#### 1. Tesseractの確認
```bash
# インストール確認
tesseract --version

# 言語データ確認
tesseract --list-langs

# 日本語データが表示されない場合
sudo apt-get install tesseract-ocr-jpn  # Ubuntu/Debian
brew install tesseract-lang              # macOS
```

#### 2. OCRテストスクリプトの実行
```bash
cd receipt-scanner-app/receipt-scanner-backend
python test_ocr.py test_receipt.jpg
```

#### 3. よくあるエラーと対処法

**TesseractNotFoundError**
```bash
# Tesseractがインストールされていません
# 上記のインストール手順を実行してください
```

**言語データエラー**
```
Failed loading language 'jpn'
```
解決策: 日本語データをインストール
```bash
sudo apt-get install tesseract-ocr-jpn
```

**画像品質の問題**
- 画像が暗い、ぼやけている → より明るく鮮明な画像を使用
- 傾いている → アプリが自動補正しますが、できるだけ正面から撮影
- 小さすぎる → 最低でも1000x1000ピクセル以上推奨

#### 4. ログの確認
```bash
# バックエンドのログを確認
poetry run uvicorn app.main:app --reload --port 8000 --log-level debug
```

デバッグログで以下を確認:
- `Tesseract found at: [パス]`
- `Available Tesseract languages: ['eng', 'jpn', ...]`
- `OCR extracted text length: [文字数]`

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

### Railway (バックエンド推奨)

```bash
npm install -g @railway/cli
railway login
railway init
railway variables set OPENAI_API_KEY=sk-your-key
railway variables set ENVIRONMENT=production
railway up
```

### Docker での実行

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
| `/api/receipts/{id}` | PUT | レシート更新 | なし |
| `/api/receipts/{id}` | DELETE | レシート削除 | なし |
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
| `TESSDATA_PREFIX` | ❌ | - | Tesseractデータディレクトリ |

**フロントエンド:**
| 変数名 | 必須 | デフォルト | 説明 |
|--------|------|------------|------|
| `VITE_API_URL` | ✅ | `http://localhost:8000` | バックエンドAPI URL |
| `VITE_APP_NAME` | ❌ | `Receipt Scanner` | アプリケーション名 |
| `VITE_ENVIRONMENT` | ❌ | `development` | フロントエンド環境 |

## 🧪 テスト

```bash
# OCRテスト
cd receipt-scanner-app/receipt-scanner-backend
python test_ocr.py test_receipt.jpg

# バックエンドテスト
poetry run pytest tests/ -v

# フロントエンドテスト
cd receipt-scanner-app/receipt-scanner-frontend
npm test
npm run lint
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
