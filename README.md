# Azure Speech Services API v1

Azure Speech Servicesを使用した音声文字起こしAPIです。WatchMeプラットフォームの一部として動作します。

## 📋 更新履歴

### 2025年8月26日 - v1.45.0
- **Azure Speech SDK を最新版にアップグレード**: 1.34.0 → 1.45.0
- **音声認識の問題を解決**: SDK更新により認識精度が大幅に向上
- **本番環境で動作確認済み**: vibe-transcriber-v2として稼働中

## 🚀 セットアップ

### 1. 仮想環境の作成と有効化

```bash
cd /Users/kaya.matsumoto/api_azure-speech_v1
python3 -m venv venv
source venv/bin/activate
```

### 2. 依存関係のインストール

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 環境変数の設定

`.env`ファイルを作成して以下を設定：

```bash
# Azure Speech Service設定（必須）
AZURE_SPEECH_KEY=your-azure-speech-key
AZURE_SERVICE_REGION=japaneast

# Supabase設定（本番環境で必要）
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key

# AWS S3設定（本番環境で必要）
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
S3_BUCKET_NAME=watchme-vault
AWS_REGION=us-east-1
```

## 🧪 テスト手順

### ローカルテスト

1. **音声ファイルを準備**
   - テスト用のWAVファイルを用意（例：`/Users/kaya.matsumoto/Desktop/audio.wav`）

2. **テストスクリプトを実行**

```bash
# 仮想環境を有効化
source venv/bin/activate

# 環境変数をクリア（システムに古い設定が残っている場合）
unset AZURE_SERVICE_REGION
unset AZURE_SPEECH_KEY

# テスト実行
python test_transcribe.py
```

期待される出力：
```
✅ テスト成功！
認識結果: [音声の内容]
```

### APIサーバーのローカル起動

```bash
# 仮想環境で起動
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8008 --reload
```

## 🌐 本番環境へのデプロイ

### 現在の本番環境構成

- **コンテナ名**: vibe-transcriber-v2
- **ポート**: 8013
- **エンドポイント**: https://api.hey-watch.me/vibe-transcriber-v2/
- **EC2サーバー**: 3.24.16.82

### デプロイ手順

#### 1. SDKアップグレード（緊急修正の場合）

```bash
# EC2サーバーにSSH接続
ssh -i ~/watchme-key.pem ubuntu@3.24.16.82

# コンテナ内でSDKをアップグレード
docker exec vibe-transcriber-v2 pip install --upgrade azure-cognitiveservices-speech==1.45.0

# コンテナを再起動
docker restart vibe-transcriber-v2

# ログを確認
docker logs -f vibe-transcriber-v2
```

#### 2. 完全なデプロイ（コード変更を含む場合）

```bash
# 1. Dockerイメージをビルド
docker build -t vibe-transcriber-v2 .

# 2. ECRにプッシュ（AWSの認証情報が必要）
aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com
docker tag vibe-transcriber-v2:latest 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-api-transcriber-v2:latest
docker push 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-api-transcriber-v2:latest

# 3. EC2サーバーで新しいイメージをプル
ssh -i ~/watchme-key.pem ubuntu@3.24.16.82
docker pull 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-api-transcriber-v2:latest

# 4. コンテナを更新
docker stop vibe-transcriber-v2
docker rm vibe-transcriber-v2
docker run -d \
  --name vibe-transcriber-v2 \
  --network watchme-network \
  -p 8013:8013 \
  --env-file /home/ubuntu/vibe-transcriber-v2/.env \
  754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-api-transcriber-v2:latest
```

### 動作確認

#### 1. APIの生存確認

```bash
# ローカルから
curl https://api.hey-watch.me/vibe-transcriber-v2/

# 期待される応答
{
  "name": "Azure Speech Service API for WatchMe",
  "version": "2.0.0",
  "engine": "Azure Speech Service"
}
```

#### 2. 実際のファイルで処理テスト

```bash
curl -X POST "https://api.hey-watch.me/vibe-transcriber-v2/fetch-and-transcribe" \
  -H "Content-Type: application/json" \
  -d '{
    "file_paths": [
      "files/d067d407-cf73-4174-a9c1-d91fb60d64d0/2025-08-25/23-00/audio.wav"
    ]
  }'
```

#### 3. ログで認識結果を確認

```bash
# EC2サーバーで
ssh -i ~/watchme-key.pem ubuntu@3.24.16.82
docker logs vibe-transcriber-v2 --tail 50 | grep "認識"
```

## 📡 API エンドポイント

### POST /analyze/azure

音声ファイルを直接アップロードして文字起こし（ローカルAPI用）

**リクエスト:**
- `file`: 音声ファイル (.wav, .mp3, .m4a)
- 最大ファイルサイズ: 25MB

### POST /fetch-and-transcribe

S3から音声ファイルをダウンロードして文字起こし（本番環境用）

**リクエスト:**
```json
{
  "file_paths": [
    "files/device_id/2025-08-25/23-00/audio.wav"
  ]
}
```

**レスポンス:**
```json
{
  "status": "success",
  "summary": {
    "total_files": 1,
    "pending_processed": 1,
    "errors": 0
  },
  "processed_files": ["..."],
  "execution_time_seconds": 8.0,
  "message": "1件中1件を正常に処理しました"
}
```

## 🔧 技術仕様

- **Python**: 3.11以上
- **フレームワーク**: FastAPI
- **音声認識**: Azure Speech Services SDK 1.45.0
- **対応形式**: .wav, .mp3, .m4a
- **言語**: 日本語 (ja-JP)
- **ポート**: 
  - ローカル: 8008
  - 本番: 8013

## 🐛 トラブルシューティング

### 音声が認識されない場合

1. **環境変数の確認**
```bash
# システムに古い環境変数が残っていないか確認
echo $AZURE_SERVICE_REGION
echo $AZURE_SPEECH_KEY

# 必要に応じてクリア
unset AZURE_SERVICE_REGION
unset AZURE_SPEECH_KEY
```

2. **SDKバージョンの確認**
```bash
pip list | grep azure-cognitiveservices-speech
# 1.45.0 であることを確認
```

3. **ログの確認**
```bash
# 本番環境
docker logs vibe-transcriber-v2 --tail 100

# ローカル
python test_transcribe.py
```

### よくあるエラーと対処法

| エラー | 原因 | 対処法 |
|-------|------|--------|
| `WS_OPEN_ERROR_UNDERLYING_IO_ERROR` | リージョンまたはキーが無効 | .envファイルを確認 |
| `SPXERR_SWITCH_MODE_NOT_ALLOWED` | 互換性のない設定 | Conversationモードの設定を削除 |
| `空の結果` | SDKバージョンが古い | SDK 1.45.0にアップグレード |

## 📝 注意事項

- Azure Speech Servicesのキーとリージョンが正しく設定されていることを確認
- 音声ファイルは一時的にサーバーに保存され、処理後に自動削除されます
- 本番環境では必ずDockerコンテナとして実行してください
- SDK 1.45.0以降を使用することを強く推奨します（古いバージョンでは認識精度が低下）

## 🔗 関連リンク

- [Azure Speech Service ドキュメント](https://docs.microsoft.com/ja-jp/azure/cognitive-services/speech-service/)
- [WatchMe Server Configs](https://github.com/matsumotokaya/watchme-server-configs)
- 本番環境URL: https://api.hey-watch.me/vibe-transcriber-v2/