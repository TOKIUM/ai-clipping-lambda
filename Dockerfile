FROM python:3.12-slim

WORKDIR /app

# 必要なパッケージをインストール
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libffi-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 依存関係をコピーしてインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# 環境変数の設定
ENV PYTHONPATH=/app
ENV ENVIRONMENT=development
ENV LOG_LEVEL=INFO

CMD ["python", "-m", "pytest", "-xvs", "tests/"]
