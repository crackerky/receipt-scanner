# 🔍 写真アップロード問題の解決ガイド

写真をアップロードしても処理できない問題を解決するためのガイドです。

## 📋 実装された修正内容

### 1. **強化されたAPI通信**
- エラーハンドリングの改善
- デバッグログの追加
- ファイル検証の強化
- ネットワークエラーの詳細表示

### 2. **バックエンドの改善**
- CORS設定の強化
- リクエストログの追加
- レスポンス詳細化
- エラー情報の充実

### 3. **フロントエンドの機能追加**
- バックエンドヘルスチェック
- サーバー状態表示
- リアルタイムエラー表示
- 詳細なデバッグ情報

## 🛠️ 問題診断手順

### ステップ1: バックエンドの起動確認

```bash
cd receipt-scanner-app/receipt-scanner-backend

# 環境変数確認
cat .env

# 依存関係インストール
poetry install

# サーバー起動
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### ステップ2: ヘルスチェック

```bash
# ブラウザまたはcurlで確認
curl http://localhost:8000/healthz
curl http://localhost:8000/api/status
```

**正常なレスポンス例:**
```json
{
  "status": "ok",
  "timestamp": "2023-05-15T10:30:00.000Z",
  "environment": "development", 
  "openai_available": true,
  "cors_origins": ["http://localhost:3000", "http://localhost:5173"]
}
```

### ステップ3: フロントエンドの設定確認

```bash
cd receipt-scanner-app/receipt-scanner-frontend

# 環境変数ファイル作成
cp .env.example .env.local

# .env.localの内容確認
cat .env.local
# VITE_API_URL=http://localhost:8000

# 依存関係インストール
npm install

# 開発サーバー起動
npm run dev
```

### ステップ4: ブラウザでの確認

1. **開発者ツールを開く** (F12)
2. **Console タブを確認**
3. **Network タブを確認**

**確認すべきログ:**
```
API_URL: http://localhost:8000
API Request: POST http://localhost:8000/api/receipts/upload
Uploading file: {name: "receipt.jpg", size: 123456, type: "image/jpeg"}
API Response: 200 OK
```

## 🚨 よくある問題と解決方法

### 問題1: "バックエンドサーバーに接続できません"

**原因:** バックエンドが起動していない

**解決方法:**
```bash
cd receipt-scanner-app/receipt-scanner-backend
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 問題2: "CORS エラー"

**原因:** フロントエンドとバックエンドのポートが異なる

**解決方法:**
```bash
# .env.localで正しいURLを設定
echo "VITE_API_URL=http://localhost:8000" > receipt-scanner-app/receipt-scanner-frontend/.env.local
```

### 問題3: "OpenAI API key not provided"

**原因:** APIキーが設定されていない

**解決方法:**
```bash
# バックエンドの.envファイルに追加
echo "OPENAI_API_KEY=sk-your-actual-api-key" >> receipt-scanner-app/receipt-scanner-backend/.env
```

### 問題4: "Rate limit exceeded"

**原因:** 短時間に多数のリクエスト

**解決方法:**
- 1分間待ってから再試行
- または設定で制限を緩和

### 問題5: "ファイル形式エラー"

**原因:** サポートされていないファイル形式

**解決方法:**
- JPEG, PNG, JPG形式のファイルを使用
- ファイルサイズを10MB以下にする

## 🔧 詳細な診断コマンド

### バックエンドの詳細ログ確認

```bash
cd receipt-scanner-app/receipt-scanner-backend

# デバッグモードで起動
DEBUG=true poetry run uvicorn app.main:app --reload --log-level debug
```

### フロントエンドのデバッグ

```bash
# ブラウザの開発者ツールでConsoleタブを確認
# 以下のような情報が表示される:
console.log('API_URL:', API_URL);
console.log('API Request: POST /api/receipts/upload');
console.log('Uploading file:', fileInfo);
```

### ネットワーク確認

```bash
# バックエンドへの接続確認
curl -v http://localhost:8000/healthz

# ファイルアップロードテスト
curl -X POST -F "file=@test-receipt.jpg" http://localhost:8000/api/receipts/upload
```

## 🎯 完全動作確認手順

### 1. 両方のサーバーを起動

```bash
# ターミナル1: バックエンド
cd receipt-scanner-app/receipt-scanner-backend
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ターミナル2: フロントエンド  
cd receipt-scanner-app/receipt-scanner-frontend
npm run dev
```

### 2. ブラウザでアクセス

```
http://localhost:3000 (または 5173)
```

### 3. 状態確認

- 右上の**ステータスインジケーター**が「オンライン」になっているか確認
- テストレシートボタンで動作確認

### 4. 写真アップロード

- **「レシートを撮影」**または**「画像を選択」**をクリック
- JPEG/PNG形式の画像を選択
- 処理状況をConsoleで確認

## 📞 それでも解決しない場合

以下の情報を確認してください：

1. **ブラウザのConsoleエラー**
2. **バックエンドのログ出力**
3. **環境変数の設定**
4. **ファイアウォール設定**
5. **Tesseractのインストール状況**

### Tesseractのインストール確認

```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr tesseract-ocr-jpn

# macOS
brew install tesseract tesseract-lang

# インストール確認
tesseract --version
```

### OpenAI APIキーの確認

```bash
# APIキーが正しく設定されているか確認
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('OPENAI_API_KEY')
print('API Key set:', bool(key))
print('Key starts with:', key[:10] + '...' if key else 'None')
"
```

## 🔍 実際の動作ログ例

### 正常動作時のログ

**フロントエンド (Console):**
```
API_URL: http://localhost:8000
API Request: POST http://localhost:8000/api/receipts/upload
Uploading file: {name: "receipt.jpg", size: 234567, type: "image/jpeg"}
API Response: 200 OK
API Response Data: {success: true, message: "AI処理でレシート情報を抽出しました。", data: {...}}
```

**バックエンド (ログ):**
```
INFO:     Request: POST http://localhost:8000/api/receipts/upload
INFO:     File info: name=receipt.jpg, content_type=image/jpeg, size=234567
INFO:     File content size: 234567 bytes
INFO:     Starting image processing...
INFO:     OpenAI API initialized successfully
INFO:     OCR extracted text length: 156
INFO:     Processing result: True
INFO:     Successfully processed receipt 1
INFO:     Response: 200 - 2.345s
```

### エラー時のログ例

**CORS エラー:**
```
Access to fetch at 'http://localhost:8000/api/receipts/upload' from origin 'http://localhost:3000' has been blocked by CORS policy
```

**API キーエラー:**
```
INFO:     Processing result: False
WARNING:  Required environment variable OPENAI_API_KEY is not set. Some features may be limited.
```

**ファイル形式エラー:**
```
WARNING:  Unsupported file extension: gif
API Response: 400 Bad Request
```

## 📱 モバイル端末での注意点

### iOS Safari
- カメラへのアクセス許可が必要
- HTTPS接続が推奨

### Android Chrome  
- ファイル選択が正常に動作することを確認
- 大きなファイルは処理に時間がかかる場合がある

## 🎉 修正後の新機能

### 1. リアルタイム状態表示
- 右上にサーバー接続状態を表示
- オンライン/オフライン/確認中の3状態

### 2. 詳細エラー情報
- 具体的なエラーメッセージ
- 解決策の提示
- デバッグ情報の表示

### 3. 自動再接続
- 30秒ごとのヘルスチェック
- 自動復旧機能

### 4. 改善されたファイル検証
- ファイル形式の事前チェック
- サイズ制限の確認
- 詳細なエラーメッセージ

これらの修正により、写真アップロードの問題が解決され、何が問題だったかが明確に分かるようになります。