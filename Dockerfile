FROM python:3.11-slim

WORKDIR /app

# システムパッケージの更新とcurlのインストール
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 依存関係のコピーとインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# ポート8013を公開
EXPOSE 8013

# アプリケーション起動コマンド
CMD ["python", "main.py"]