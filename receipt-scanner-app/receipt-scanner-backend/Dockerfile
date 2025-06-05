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
    libgl1-mesa-glx \
    # Additional OpenCV dependencies
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgomp1 \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの設定
WORKDIR /app

# Pythonパッケージを直接インストール（Poetryを使わない）
RUN pip install --upgrade pip

# requirements.txtをコピーして依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
