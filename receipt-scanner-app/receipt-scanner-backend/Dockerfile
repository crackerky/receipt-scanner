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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリの設定
WORKDIR /app

# Pythonパッケージを直接インストール（Poetryを使わない）
RUN pip install --upgrade pip

# 依存関係を直接インストール
RUN pip install \
    fastapi[standard]==0.115.12 \
    "psycopg[binary]>=3.2.9" \
    python-multipart==0.0.20 \
    pillow==11.2.1 \
    pytesseract==0.3.13 \
    langchain-openai==0.3.16 \
    python-dotenv==1.1.0 \
    langchain==0.3.25 \
    requests \
    uvicorn[standard]

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
