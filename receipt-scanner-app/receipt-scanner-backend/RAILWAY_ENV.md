# Railway環境変数設定ガイド

Railwayのダッシュボードで以下の環境変数を設定してください：

## 必須の環境変数

```
OPENAI_API_KEY=sk-your-actual-api-key
DATABASE_URL=postgresql://user:password@host:port/dbname
SECRET_KEY=your-secret-key-here
```

## オプション環境変数

```
DEBUG=false
ENVIRONMENT=production
ALLOWED_ORIGINS=https://your-frontend-url.railway.app
PORT=8000
```

## Railwayでの設定方法

1. Railwayダッシュボードにログイン
2. プロジェクトを選択
3. "Variables"タブをクリック
4. "Add Variable"をクリック
5. 各環境変数を追加

## 注意事項

- OPENAI_API_KEYは必須です（OpenAI APIキーがないと動作しません）
- DATABASE_URLはRailwayが自動的に提供する場合があります
- SECRET_KEYは推測されにくい長い文字列を使用してください
