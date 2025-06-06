# Railway環境変数設定ガイド

Railwayのダッシュボードで以下の環境変数を設定してください：

## 必須の環境変数

```
OPENAI_API_KEY=sk-your-actual-api-key
ENVIRONMENT=production
```

## 重要な環境変数（CORS設定）

```
ALLOWED_ORIGINS=https://your-frontend-url.vercel.app,https://your-frontend-url.netlify.app,http://localhost:3000,http://localhost:5173
```

**注意**: `ALLOWED_ORIGINS`にはフロントエンドのURLを必ず含めてください。複数のURLはカンマで区切ります。

## オプション環境変数

```
DATABASE_URL=postgresql://user:password@host:port/dbname
SECRET_KEY=your-secret-key-here
DEBUG=false
PORT=8000
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_WINDOW=60
```

## Railwayでの設定方法

1. Railwayダッシュボードにログイン
2. プロジェクトを選択
3. "Variables"タブをクリック
4. "Add Variable"をクリック
5. 各環境変数を追加

## デバッグ用の設定

接続問題が発生している場合は、以下を試してください：

1. **ALLOWED_ORIGINSに全てのオリジンを許可（一時的）**
   ```
   ALLOWED_ORIGINS=*
   ```
   ⚠️ セキュリティ上、本番環境では特定のURLのみを指定してください

2. **デバッグモードを有効化**
   ```
   DEBUG=true
   ```

## 注意事項

- OPENAI_API_KEYは必須です（未設定でもOCRのみで動作します）
- DATABASE_URLはRailwayが自動的に提供する場合があります
- SECRET_KEYは推測されにくい長い文字列を使用してください
- ALLOWED_ORIGINSは本番環境では必ず特定のURLのみを指定してください
