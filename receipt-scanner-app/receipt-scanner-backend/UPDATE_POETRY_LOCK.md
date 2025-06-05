# poetry.lockファイルを更新するための手順

## エラーの原因
pyproject.tomlに新しい依存関係（opencv-python、numpy）を追加しましたが、
poetry.lockファイルが更新されていないため、Dockerビルドが失敗しています。

## 解決方法

### ローカルで実行する場合:
```bash
cd receipt-scanner-app/receipt-scanner-backend
poetry lock --no-update
poetry install
```

### Dockerfileを一時的に修正する場合:
Dockerfileの該当行を以下のように変更:
```dockerfile
# 依存関係のインストール（システム環境に直接）
RUN poetry config virtualenvs.create false \
    && poetry install --only=main --no-root --no-interaction \
    && rm -rf $POETRY_CACHE_DIR
```

### または、poetry.lockを再生成:
```bash
cd receipt-scanner-app/receipt-scanner-backend
rm poetry.lock
poetry install
git add poetry.lock
git commit -m "chore: Update poetry.lock with new dependencies"
git push
```

## 注意事項
- poetry.lockファイルは、プロジェクトの依存関係の正確なバージョンを記録しています
- pyproject.tomlを変更した後は、必ずpoetry.lockも更新する必要があります
- CI/CDパイプラインでは、poetry.lockファイルが最新でないとビルドが失敗します
