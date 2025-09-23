# Azure Speech Services API v1 (vibe-transcriber-v2)

Azure Speech Servicesを使用した音声文字起こしAPIです。WatchMeプラットフォームの一部として動作します。

> **注意**: 本番環境では`vibe-transcriber-v2`という名前でECRからDockerイメージとしてデプロイされています。

## ⚠️ Azure Speech Service 利用制限について

### 日次クォータのリセット時間
**Azure Speech Serviceの無料枠または日次利用制限は、UTC 00:00（日本時間 09:00）にリセットされます。**

#### 重要な注意点：
- **制限到達時の挙動**: APIは200を返すが、実際の文字起こし結果が空になる可能性がある
- **リセット時刻**: 
  - UTC 00:00 = 日本時間（JST）09:00
  - 毎日朝9時に新しいクォータが利用可能になる
- **確認された事例**（2025年9月22日）:
  - 08:46 JST: 処理は成功するが結果が空（`has_text: false`）
  - 09:10 JST: UTC日付変更後、正常に処理完了

### 対処方法
1. **処理時間の調整**: 重要な処理は日本時間09:00以降に実行
2. **自動エラー検知**: システムが自動的に利用上限を検知し、`quota_exceeded`ステータスを設定
3. **ステータス確認**: `transcriptions_status`をチェックして処理状態を把握
   - `pending`: 未処理
   - `processing`: 処理中
   - `completed`: 処理完了
   - `failed`: エラー発生
   - `quota_exceeded`: Azure利用上限超過
4. **モニタリング**: Azure ポータルで実際の利用量を確認

## 🐳 本番環境情報

- **ECRリポジトリ**: `754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-api-transcriber-v2`
- **コンテナ名**: `vibe-transcriber-v2`
- **ポート**: 8013
- **公開URL**: `https://api.hey-watch.me/vibe-transcriber-v2/`
- **デプロイ方式**: ECRからDockerイメージをプル

## 🔧 処理制限モード（コスト最適化機能）

### 概要
無駄なAPI利用を削減し、コストを最適化するための処理制限機能を実装しています。特定のデバイスIDと時間帯の組み合わせで音声処理をスキップできます。

### 現在の設定（2025年9月23日）
| デバイスID | 制限時間帯 | 理由 |
|-----------|-----------|------|
| `9f7d6e27-98c3-4c19-bdfb-f7fda58b9a93` | 23:00-05:59 | テストデバイス - 夜間処理制限 |

### 動作仕様
- **ステータス**: 制限対象の処理は`skipped`ステータスが設定されます
- **ログ**: 処理スキップ時に理由付きでログ出力されます
- **拡張性**: 今後、環境変数やデータベース管理への移行を想定した設計

### カスタマイズ方法
`app/services.py`の`RESTRICTED_DEVICES`辞書を編集：
```python
RESTRICTED_DEVICES = {
    'device-id': {
        'skip_hours': [0,1,2,3,4,5],  # スキップする時間（0-23）
        'reason': 'スキップ理由'
    }
}
```

### 注意事項
- この機能は**コスト削減**を目的とした運用制限です
- 本番運用開始後も、必要に応じて制限対象を調整可能
- 将来的には環境変数やDB管理への移行を検討

## 📋 更新履歴

最新の変更履歴は [CHANGELOG.md](./CHANGELOG.md) をご覧ください。

**最新バージョン**: v1.49.0 (2025-09-23)
- 処理制限モード機能を追加
- Quota exceededエラーの検出改善

## 🗄️ データベース設定

### audio_filesテーブル
処理ステータスを管理するテーブルです。以下のステータス値を使用します：

| ステータス | 説明 |
|-----------|------|
| `pending` | 未処理 |
| `processing` | 処理中 |
| `completed` | 処理完了 |
| `failed` | エラー発生 |
| `quota_exceeded` | Azure利用上限超過 |

### vibe_whisperテーブル
文字起こし結果を保存するテーブルです。

```sql
-- テーブル構造
create table public.vibe_whisper (
  device_id text not null,
  date date not null,
  time_block text not null,
  transcription text null,
  status text not null default 'pending'::text,
  created_at timestamp with time zone not null default now(),  -- 処理実行時刻
  constraint vibe_whisper_pkey primary key (device_id, date, time_block),
  constraint vibe_whisper_time_block_check check ((time_block ~ '^[0-2][0-9]-[0-5][0-9]$'::text))
);
```

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

# WatchMeシステム統合設定（v1.46.0で必須）
# Supabase設定 - audio_filesテーブルからファイル情報を取得
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key

# AWS S3設定 - 音声ファイルの取得先
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

## 🚢 本番環境デプロイ

### 前提条件
1. **watchme-networkインフラストラクチャが起動済み**
   ```bash
   cd /home/ubuntu/watchme-server-configs
   docker-compose -f docker-compose.infra.yml up -d
   ```

2. **環境変数ファイル（.env）が配置済み**
   - `/home/ubuntu/vibe-transcriber-v2/.env`

### デプロイ手順

#### 方法1: run-prod.shを使用（推奨）
```bash
# EC2サーバー上で実行
cd /home/ubuntu/vibe-transcriber-v2
./run-prod.sh
```

#### 方法2: 手動でdocker-composeを使用
```bash
# ECRから最新イメージをプル
aws ecr get-login-password --region ap-southeast-2 | \
  docker login --username AWS --password-stdin \
  754724220380.dkr.ecr.ap-southeast-2.amazonaws.com

docker pull 754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-api-transcriber-v2:latest

# コンテナを起動
docker-compose -f docker-compose.prod.yml up -d
```

### 動作確認
```bash
# ヘルスチェック
curl http://localhost:8013/

# コンテナ状態確認
docker ps | grep vibe-transcriber

# ログ確認
docker logs -f vibe-transcriber-v2
```

### 旧デプロイ手順（参考）

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

**新しいインターフェース（推奨）:**
```bash
curl -X POST "https://api.hey-watch.me/vibe-transcriber-v2/fetch-and-transcribe" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "d067d407-cf73-4174-a9c1-d91fb60d64d0",
    "local_date": "2025-08-26",
    "time_blocks": ["09-00", "09-30"],
    "model": "azure"
  }'
```

**既存インターフェース（後方互換性）:**
```bash
curl -X POST "https://api.hey-watch.me/vibe-transcriber-v2/fetch-and-transcribe" \
  -H "Content-Type: application/json" \
  -d '{
    "file_paths": [
      "files/d067d407-cf73-4174-a9c1-d91fb60d64d0/2025-08-25/23-00/audio.wav"
    ],
    "model": "azure"
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

WatchMeシステム統合エンドポイント - Supabaseからファイル情報を取得してS3から音声ファイルをダウンロード後、文字起こし実行

#### 新しいインターフェース（v1.46.0〜推奨）

**リクエスト:**
```json
{
  "device_id": "d067d407-cf73-4174-a9c1-d91fb60d64d0",
  "local_date": "2025-08-26",
  "time_blocks": ["09-00", "09-30", "10-00"],  // オプション: 特定の時間帯のみ処理
  "model": "azure"
}
```

#### 既存インターフェース（後方互換性維持）

**リクエスト:**
```json
{
  "file_paths": [
    "files/device_id/2025-08-25/23-00/audio.wav"
  ],
  "model": "azure"
}
```

#### 共通レスポンス

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
- **統合システム**: WatchMe Platform (v1.46.0〜)
  - **データベース**: Supabase (Python SDK 2.10.0)
  - **ファイルストレージ**: AWS S3 (boto3 1.35.57)
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
| `処理成功だがデータベースに結果なし` | 状態区別問題 | 下記「データ状態区別」参照 |

### 🎯 データ状態区別の重要性【2025年8月29日追加】

**問題の背景:**
音声処理において「未処理」と「処理済み・発話なし」の状態が混同され、エンジニアが処理状況を正確に把握できない問題が発生しました。

**正しい状態管理:**

| データベースの状態 | 意味 | transcriptions_status | transcription |
|------------------|------|---------------------|---------------|
| **未処理** | まだ音声処理を行っていない | `pending` | （なし） |
| **処理済み・発話なし** | 処理したが音声に発話内容なし | `completed` | `発話なし` |
| **処理済み・発話あり** | 処理して正常な文字起こし取得 | `completed` | `実際の内容` |

**重要な実装ポイント:**
- 空の認識結果は **空文字列ではなく「発話なし」** としてデータベースに保存
- ログ出力で発話有無を明確に表示
- `no_speech_detected`フラグで判別可能

## ⚠️ 開発・運用時の重要な注意事項

### 🔄 正しい開発フロー【必須】

**❌ 絶対にやってはいけないこと:**
- 本番環境のコンテナ内で直接コードを修正する
- 本番環境で`docker exec`を使ってファイルを変更する

**✅ 正しいフロー:**
1. ローカルでコード修正
2. `docker build`でイメージを作成
3. ECRにプッシュ (`aws ecr get-login-password` → `docker push`)
4. EC2サーバーで`docker pull`して最新イメージを取得
5. `docker-compose -f docker-compose.prod.yml`で再デプロイ

### 🐛 デバッグ時の注意点

**問題発生時の調査手順:**
1. **ログで処理フローを確認** - `docker logs vibe-transcriber-v2 --tail 100`
2. **APIレスポンスを確認** - 成功ステータスとデータベース保存の両方をチェック
3. **データベースの実際の状態を確認** - transcriptions_statusとtranscriptionの内容
4. **watchme-network接続状態を確認** - `bash /home/ubuntu/watchme-server-configs/scripts/check-infrastructure.sh`

**データ不整合が起きた場合:**
- 処理は成功しているがデータが期待通りでない場合は、状態区別の問題を疑う
- 空文字列と「発話なし」の違いを確認する

### 🎨 技術的注意事項

- Azure Speech Servicesのキーとリージョンが正しく設定されていることを確認
- 音声ファイルは一時的にサーバーに保存され、処理後に自動削除されます
- 本番環境では必ずDockerコンテナとして実行してください
- SDK 1.45.0以降を使用することを強く推奨します（古いバージョンでは認識精度が低下）
- watchme-networkに`external: true`で接続すること（独自ネットワーク作成禁止）

## 🔗 関連リンク

- [Azure Speech Service ドキュメント](https://docs.microsoft.com/ja-jp/azure/cognitive-services/speech-service/)
- [WatchMe Server Configs](https://github.com/matsumotokaya/watchme-server-configs)
- 本番環境URL: https://api.hey-watch.me/vibe-transcriber-v2/