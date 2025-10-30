#!/bin/bash
set -e

# =============================================================================
# Vibe Analysis Transcriber (Azure Speech API) 本番環境起動スクリプト
# =============================================================================
# ECRから最新イメージをプルして起動
# =============================================================================

ECR_REPOSITORY="754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-vibe-analysis-transcriber"
AWS_REGION="ap-southeast-2"

echo "=== vibe-analysis-transcriber 本番環境起動 ==="
echo "リポジトリ: $ECR_REPOSITORY"

# watchme-networkの確認（インフラストラクチャ管理体制）
echo "🌐 watchme-networkの確認中..."
if ! docker network ls | grep -q "watchme-network"; then
    echo "⚠️  watchme-networkが存在しません"
    echo "インフラストラクチャを起動してください:"
    echo "  cd /home/ubuntu/watchme-server-configs"
    echo "  docker-compose -f docker-compose.infra.yml up -d"
    exit 1
else
    echo "✅ watchme-networkが確認されました"
fi

# .env ファイルのチェック
if [ ! -f ".env" ]; then
    echo "⚠️  警告: .env ファイルが見つかりません"
    echo "環境変数が設定されていることを確認してください"
fi

# ECRから最新イメージをプル
echo "📦 ECRから最新イメージをプル中..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REPOSITORY

docker pull $ECR_REPOSITORY:latest

# 既存のコンテナを停止・削除（3層アプローチ）
echo "🛑 既存のコンテナを停止・削除中..."

# 1. 実行中コンテナの検索と停止
RUNNING_CONTAINERS=$(docker ps -q --filter "name=vibe-analysis-transcriber")
if [ ! -z "$RUNNING_CONTAINERS" ]; then
    echo "  - 実行中のコンテナを停止: $RUNNING_CONTAINERS"
    docker stop $RUNNING_CONTAINERS
fi

# 2. 全コンテナの削除（停止済み含む）
ALL_CONTAINERS=$(docker ps -aq --filter "name=vibe-analysis-transcriber")
if [ ! -z "$ALL_CONTAINERS" ]; then
    echo "  - コンテナを削除: $ALL_CONTAINERS"
    docker rm -f $ALL_CONTAINERS
fi

# 3. docker-compose管理コンテナの削除
echo "  - docker-compose down実行"
docker-compose -f docker-compose.prod.yml down || true

# コンテナを起動
echo "🚀 本番環境でコンテナを起動中..."
docker-compose -f docker-compose.prod.yml up -d

# 起動確認
echo "⏳ 起動確認中..."
sleep 5

# ヘルスチェック
echo "🏥 ヘルスチェック実行中..."
for i in {1..10}; do
    if curl -s http://localhost:8013/ > /dev/null 2>&1; then
        echo "✅ ヘルスチェック成功！"
        break
    fi
    echo -n "."
    sleep 3
done

# コンテナの状態を表示
echo ""
echo "📊 コンテナ状態:"
docker ps | grep -E "CONTAINER|vibe-analysis-transcriber" || echo "コンテナが見つかりません"

echo ""
echo "=== 起動完了 ==="
echo "内部エンドポイント: http://localhost:8013"
echo "公開URL: https://api.hey-watch.me/vibe-analysis-transcriber/"
echo ""
echo "ログ確認:"
echo "  docker logs -f vibe-analysis-transcriber"