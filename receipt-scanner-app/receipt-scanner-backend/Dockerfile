# Railway対応のシンプルなDockerfile
FROM python:3.12-slim

# システム依存関係のインストール（OpenCV追加）
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-jpn \
    tesseract-ocr-eng \
    build-essential \
    curl \
    # OpenCV dependencies
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-0 \
    libgl1-mesa-glx \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの設定
WORKDIR /app

# Poetry のインストール
RUN pip install --upgrade pip && \
    pip install poetry

# Poetry 設定（仮想環境を作成しない）
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 依存関係ファイルのコピー
COPY pyproject.toml poetry.lock ./

# デバッグ情報の表示
RUN echo "=== Python version ===" && \
    python --version && \
    echo "=== Poetry version ===" && \
    poetry --version && \
    echo "=== pyproject.toml content ===" && \
    cat pyproject.toml && \
    echo "=== Poetry check ===" && \
    poetry check || true

# 依存関係のインストール（システム環境に直接）
# エラーを無視せずに各ステップを個別に実行
RUN poetry config virtualenvs.create false

# mainグループのみをインストール（オプショナルグループを除外）
RUN poetry install --only=main --no-root --no-interaction -vvv || \
    (echo "=== Poetry install failed. Showing dependencies ===" && \
     poetry show --tree || true && \
     echo "=== Trying without lock file ===" && \
     poetry install --only=main --no-root --no-interaction --no-ansi || exit 1)

# キャッシュディレクトリのクリーンアップ
RUN rm -rf $POETRY_CACHE_DIR

# アプリケーションコードのコピー
COPY app/ ./app/

# 非rootユーザーの作成
RUN groupadd -r appuser && useradd -r -g appuser appuser

# アップロードディレクトリの作成
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app

# 非rootユーザーに切り替え
USER appuser

# 環境変数
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production

# ポート公開
EXPOSE 8000

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/healthz', timeout=10)" || exit 1

# アプリケーション起動
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
