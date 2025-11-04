# Vibe Analysis Transcriber API

マルチプロバイダー対応のASR（自動音声認識）APIです。WatchMeプラットフォームの一部として動作します。

## 🤖 ASRプロバイダー設定

### 設計コンセプト

このAPIは**複数のASRプロバイダーに対応**し、簡単に切り替えられる設計になっています。

**目的**:
- 新しいモデルへの迅速な移行
- コスト最適化（プロバイダーごとに価格が異なる）
- パフォーマンス不良時の即座の切り戻し
- 複数のプロバイダーを事前準備（APIキー設定済み、いつでも切り替え可能）

**特徴**:
- ✅ クライアント側（アプリ・他のAPI）の変更は不要
- ✅ コード1行変更 → git push で切り替え完了
- ✅ 2-3種類のプロバイダーを待機状態で保持可能
- ✅ モデルバージョンアップも同じ手順

### 現在使用中

- プロバイダー: **Deepgram**
- モデル: **nova-3**
- デプロイ日: **2025-11-04**
- ステータス: **✅ 稼働中・動作確認済み**
- SDK バージョン: **deepgram-sdk==3.7.0**

### 対応プロバイダー

| プロバイダー | 対応モデル例 | 環境変数 | 状態 | SDK情報 |
|------------|------------|---------|------|----|
| **Azure** | ja-JP (日本語), en-US (英語) | AZURE_SPEECH_KEY, AZURE_SERVICE_REGION | ✅ 設定済み | azure-cognitiveservices-speech==1.45.0 |
| **Groq** | whisper-large-v3-turbo, whisper-large-v3 | GROQ_API_KEY | ✅ 設定済み | groq>=0.4.0 |
| **Deepgram** | nova-3, nova-2, whisper, enhanced | DEEPGRAM_API_KEY | ✅ **稼働中**（句読点・話者分離対応） | deepgram-sdk==3.7.0 |

### 新しいプロバイダーを追加する方法

#### ⚠️ 必須チェックリスト（3箇所セット）

新しいプロバイダー（例: Deepgram）を追加する際は、**必ず以下の3箇所**を更新してください：

**1. GitHub Secrets に APIキーを追加**
```
リポジトリの Settings > Secrets and variables > Actions
例: DEEPGRAM_API_KEY = your-api-key
```

**2. docker-compose.prod.yml に環境変数を追加**
```yaml
environment:
  - DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}  # ← 追加
```

**3. .github/workflows/deploy-to-ecr.yml を更新**
```yaml
# 3-a. env: セクションに追加
env:
  DEEPGRAM_API_KEY: ${{ secrets.DEEPGRAM_API_KEY }}

# 3-b. .env作成スクリプトに追加
echo "DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}" >> .env
```

**❌ よくある失敗**: GitHub Secretsと.envファイルには追加したが、docker-compose.ymlを忘れる
→ コンテナ起動時に「環境変数が設定されていません」エラーになります

---

### プロバイダー切り替え方法

#### Azure → Groq に切り替える場合

**ステップ1: Groq APIキーの準備**

1. Groq APIキーを取得: https://console.groq.com/
2. 環境変数に追加（ローカル・本番環境の `.env` ファイル）:
   ```bash
   GROQ_API_KEY=gsk-your-api-key
   ```

**ステップ2: プロバイダーを切り替え**

```bash
# app/asr_providers.py を編集
vi app/asr_providers.py
```

変更内容：
```python
# 変更前
CURRENT_PROVIDER = "azure"
CURRENT_MODEL = "ja-JP"

# 変更後
CURRENT_PROVIDER = "groq"
CURRENT_MODEL = "whisper-large-v3-turbo"
```

**ステップ3: デプロイ**

```bash
git add app/asr_providers.py
git commit -m "feat: Switch to Groq whisper-large-v3-turbo"
git push origin main

# CI/CDが自動実行（約5分）
```

**ステップ4: 動作確認**

```bash
# ヘルスチェックでモデルを確認
curl https://api.hey-watch.me/vibe-analysis/transcriber/health | jq

# レスポンス例
# {
#   "status": "healthy",
#   "service": "WatchMe Transcriber API",
#   "asr_provider": "groq",  ← 変わっている
#   "asr_model": "whisper-large-v3-turbo"
# }
```

#### Groq → Azure に切り戻す場合

```python
# app/asr_providers.py
CURRENT_PROVIDER = "azure"  # 1行変更
CURRENT_MODEL = "ja-JP"
```

git push するだけで即座に戻ります。

#### Deepgram に切り替える場合

**ステップ1: Deepgram APIキーの準備**

1. Deepgram APIキーを取得: https://console.deepgram.com/
2. 環境変数に追加（ローカル・本番環境の `.env` ファイル）:
   ```bash
   DEEPGRAM_API_KEY=your-deepgram-api-key
   ```

**ステップ2: プロバイダーを切り替え**

```python
# app/asr_providers.py
CURRENT_PROVIDER = "deepgram"
CURRENT_MODEL = "nova-3"
```

**ステップ3: デプロイ**

```bash
git add app/asr_providers.py
git commit -m "feat: Switch to Deepgram nova-3"
git push origin main

# CI/CDが自動実行（約5分）
```

**Deepgramの特徴**:
- ✅ 句読点の自動挿入 (punctuate)
- ✅ 話者分離 (diarize) - 複数話者を自動識別
- ✅ スマートフォーマット - 日付、時刻、数字の自動整形
- ✅ 発話単位での区切り (utterances)
- ✅ 高精度な信頼度スコア提供

---

## 📚 各プロバイダーの詳細と導入ガイド

### 1. Azure Speech Services

**公式ドキュメント**:
- メインドキュメント: https://docs.microsoft.com/ja-jp/azure/cognitive-services/speech-service/
- Python SDK: https://docs.microsoft.com/ja-jp/python/api/azure-cognitiveservices-speech/

**特徴**:
- ✅ Microsoftが提供する高精度な音声認識サービス
- ✅ 多言語対応（日本語含む100以上の言語）
- ✅ リアルタイム・バッチ処理の両方に対応
- ⚠️ 無料枠の日次クォータ制限あり（UTC 00:00 = JST 09:00 にリセット）

**導入プロセス**:

1. **Azureポータルでリソース作成**:
   - https://portal.azure.com/ にアクセス
   - 「Speech Services」リソースを作成
   - リージョン（例: Japan East）を選択

2. **APIキーとリージョンを取得**:
   ```bash
   AZURE_SPEECH_KEY=your-azure-speech-key
   AZURE_SERVICE_REGION=japaneast
   ```

3. **requirements.txt**:
   ```
   azure-cognitiveservices-speech==1.45.0
   ```

4. **参照すべき情報**:
   - SDK リファレンス: https://docs.microsoft.com/ja-jp/python/api/azure-cognitiveservices-speech/
   - クォータ管理: https://docs.microsoft.com/ja-jp/azure/cognitive-services/speech-service/speech-services-quotas-and-limits

---

### 2. Groq Whisper

**公式ドキュメント**:
- メインサイト: https://groq.com/
- API ドキュメント: https://console.groq.com/docs/
- Python SDK: https://github.com/groq/groq-python

**特徴**:
- ✅ OpenAI Whisper モデルを高速実行（LPU™ 推論エンジン）
- ✅ whisper-large-v3-turbo で高速・高精度
- ✅ シンプルなAPI、使いやすいPython SDK
- ✅ 無料枠が比較的大きい

**導入プロセス**:

1. **Groq APIキーを取得**:
   - https://console.groq.com/ でアカウント作成
   - API Keys セクションでキーを生成

2. **環境変数**:
   ```bash
   GROQ_API_KEY=gsk-your-api-key
   ```

3. **requirements.txt**:
   ```
   groq>=0.4.0
   ```

4. **参照すべき情報**:
   - API リファレンス: https://console.groq.com/docs/api-reference
   - モデル一覧: https://console.groq.com/docs/models
   - Python SDK GitHub: https://github.com/groq/groq-python

---

### 3. Deepgram (現在稼働中) ⭐

**公式ドキュメント**:
- メインドキュメント: https://developers.deepgram.com/docs/
- Getting Started (STT): https://developers.deepgram.com/docs/stt/getting-started
- Python SDK: https://developers.deepgram.com/sdks/python-sdk

**特徴**:
- ✅ **nova-3**: 最新の高精度モデル（2024年リリース）
- ✅ 句読点の自動挿入 (punctuate)
- ✅ 話者分離 (diarize) - 複数話者を自動識別
- ✅ スマートフォーマット - 日付、時刻、数字の自動整形
- ✅ 発話単位での区切り (utterances)
- ✅ 高精度な信頼度スコア提供

**導入プロセス**:

1. **Deepgram APIキーを取得**:
   - https://console.deepgram.com/ でアカウント作成
   - API Keys セクションでキーを生成

2. **環境変数**:
   ```bash
   DEEPGRAM_API_KEY=your-deepgram-api-key
   ```

3. **requirements.txt**:
   ```
   deepgram-sdk==3.7.0
   ```

   ⚠️ **重要**: バージョンを `==3.7.0` に固定すること
   - `>=3.0.0` を指定すると v5.x がインストールされ、APIが異なる
   - 公式ドキュメントは v3.x 向けと v5.x 向けが混在している

4. **コード例** (SDK v3.7.0):
   ```python
   from deepgram import DeepgramClient, PrerecordedOptions

   client = DeepgramClient(api_key=api_key)

   options = PrerecordedOptions(
       model="nova-3",
       language="ja",
       punctuate=True,
       diarize=True,
       smart_format=True,
       utterances=True,
   )

   response = client.listen.rest.v("1").transcribe_file(
       source={"buffer": audio_data},
       options=options
   )
   ```

5. **参照すべき情報**:
   - **Getting Started**: https://developers.deepgram.com/docs/stt/getting-started
   - **Pre-recorded Audio**: https://developers.deepgram.com/docs/pre-recorded-audio
   - **Playground（公式サンプルコード）**: https://playground.deepgram.com/
     - ⚠️ Playgroundのコードが最も正確（ドキュメントよりも信頼できる）
   - Python SDK v3 Migration Guide: https://developers.deepgram.com/sdks/python-sdk/v2-to-v3-migration
   - モデル一覧: https://developers.deepgram.com/docs/models-overview

6. **トラブルシューティング時の注意点**:
   - SDK v3.7.0 の正しいAPI: `client.listen.rest.v("1").transcribe_file()`
   - SDK v5.x の場合: `client.listen.v1.media.transcribe_file()` （異なるAPI）
   - ドキュメントが混在しているため、**必ずPlaygroundで確認**すること

---

## 🎯 運用方法

> **重要**: このAPIは**Dockerコンテナ**で運用されています
> - **本番環境**: EC2上でDockerコンテナとして稼働
> - **コンテナ名**: `vibe-analysis-transcriber`
> - **ECRリポジトリ**: `watchme-vibe-analysis-transcriber`
> - **ローカル開発**: venv環境はオプション（テスト用）

---

## 🗺️ ルーティング詳細

| 項目 | 値 | 説明 |
|------|-----|------|
| **🏷️ サービス名** | Vibe Transcriber API | マルチプロバイダー対応音声文字起こし |
| **📦 機能** | ASR (音声認識) | Groq Whisper / Azure Speech Services |
| **🤖 現在のプロバイダー** | Groq | whisper-large-v3-turbo |
| | | |
| **🌐 外部アクセス（Nginx）** | | |
| └ 公開エンドポイント | `https://api.hey-watch.me/vibe-analysis/transcriber/` | ✅ 統一命名規則に準拠（2025-10-28） |
| └ Nginx設定ファイル | `/etc/nginx/sites-available/api.hey-watch.me` | |
| └ proxy_pass先 | `http://localhost:8013/` | 内部転送先 |
| └ タイムアウト | 180秒 | read/connect/send |
| | | |
| **🔌 API内部エンドポイント** | | |
| └ ヘルスチェック | `/health` | GET |
| └ **S3統合（重要）** | `/fetch-and-transcribe` | POST - Lambdaから呼ばれる |
| └ ルート情報 | `/` | GET - API情報表示 |
| | | |
| **🐳 Docker/コンテナ** | | |
| └ コンテナ名 | `vibe-analysis-transcriber` | `docker ps`で表示される名前 |
| └ ポート（内部） | 8013 | コンテナ内 |
| └ ポート（公開） | `127.0.0.1:8013:8013` | ローカルホストのみ |
| └ ヘルスチェック | `/health` | Docker healthcheck |
| | | |
| **☁️ AWS ECR** | | |
| └ リポジトリ名 | `watchme-vibe-analysis-transcriber` | ✅ 統一済み |
| └ リージョン | ap-southeast-2 (Sydney) | |
| └ URI | `754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-vibe-analysis-transcriber:latest` | |
| | | |
| **⚙️ systemd** | | |
| └ サービス名 | `vibe-analysis-transcriber.service` | ✅ 統一済み |
| └ 起動コマンド | `docker-compose up -d` | |
| └ 自動起動 | enabled | サーバー再起動時に自動起動 |
| | | |
| **📂 ディレクトリ** | | |
| └ ソースコード | `/Users/kaya.matsumoto/projects/watchme/api/vibe-analysis/transcriber-v2` | ローカル |
| └ GitHubリポジトリ | `hey-watchme/api-vibe-analysis-transcriber-v2` | |
| └ EC2配置場所 | Docker内部のみ（ディレクトリなし） | ECR経由デプロイ |
| | | |
| **🔗 呼び出し元** | | |
| └ Lambda関数 | `watchme-audio-worker` | 30分ごと |
| └ 呼び出しURL | ✅ `https://api.hey-watch.me/vibe-analysis/transcriber/fetch-and-transcribe` | **統一命名規則に準拠（2025-10-28修正）** |
| └ 環境変数 | `API_BASE_URL=https://api.hey-watch.me` | Lambda内 |

### ✅ 統一命名規則への対応完了（2025-10-28）

**API命名統一タスクに基づき、以下を修正**:

1. **Nginxエンドポイント**: `/vibe-analysis/transcription/` → `/vibe-analysis/transcriber/`
2. **Lambda関数**: URL修正完了（watchme-audio-worker）
3. **統一原則**: `/{domain}/{service}/` に準拠
   - domain: `vibe-analysis`
   - service: `transcriber`

**修正完了ファイル**:
- ✅ `/watchme/server-configs/sites-available/api.hey-watch.me`
- ✅ `/watchme/server-configs/lambda-functions/watchme-audio-worker/lambda_function.py`
- ✅ `/watchme/api/vibe-analysis/transcriber-v2/README.md`（このファイル）

---

## ⚠️ Azure Speech Service 利用制限について

### 日次クォータのリセット時間
**Azure Speech Serviceの無料枠または日次利用制限は、UTC 00:00（日本時間 09:00）にリセットされます。**

#### 重要な注意点：
- **制限到達時の挙動**: APIは200を返すが、実際のASR結果が空になる可能性がある
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

- **ECRリポジトリ**: `754724220380.dkr.ecr.ap-southeast-2.amazonaws.com/watchme-vibe-analysis-transcriber`
- **コンテナ名**: `vibe-analysis-transcriber`
- **ポート**: 8013
- **公開URL**: `https://api.hey-watch.me/vibe-analysis-transcriber/`
- **デプロイ方式**: GitHub Actions CI/CDパイプラインによる自動デプロイ

## 📋 更新履歴

**最新バージョン**: v2.0.0 (2025-10-31)
- ✅ マルチプロバイダー対応に移行
- ✅ Groq Whisper API対応（whisper-large-v3-turbo）
- ✅ プロバイダー抽象化レイヤー実装
- ✅ Azure / Groq切り替えを1行変更で実現
- ✅ CI/CD環境変数管理の改善

**v1.49.0** (2025-09-23)
- 処理制限モード機能を追加
- Quota exceededエラーの検出改善

詳細は [CHANGELOG.md](./CHANGELOG.md) をご覧ください。

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
ASR結果を保存するテーブルです。

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

## 🐳 本番環境での運用（推奨）

**このAPIは本番環境でDockerコンテナとして運用されています。**

### 環境変数の設定

`.env`ファイルを作成して以下を設定：

```bash
# Azure Speech Service設定（Azureプロバイダー使用時のみ必須）
AZURE_SPEECH_KEY=your-azure-speech-key
AZURE_SERVICE_REGION=japaneast

# Groq API設定（Groqプロバイダー使用時のみ必須）
GROQ_API_KEY=gsk-your-groq-api-key

# Deepgram API設定（Deepgramプロバイダー使用時のみ必須）
DEEPGRAM_API_KEY=your-deepgram-api-key

# WatchMeシステム統合設定（必須）
# Supabase設定 - audio_filesテーブルからファイル情報を取得
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key

# AWS S3設定 - 音声ファイルの取得先
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
S3_BUCKET_NAME=watchme-vault
AWS_REGION=us-east-1
```

**注意**: プロバイダーの指定は `app/asr_providers.py` で行います（環境変数ではありません）。

## 🌐 本番環境へのデプロイ

### 現在の本番環境構成

- **コンテナ名**: vibe-analysis-transcriber
- **ポート**: 8013
- **エンドポイント**: https://api.hey-watch.me/vibe-analysis-transcriber/
- **EC2サーバー**: 3.24.16.82

## 🚢 本番環境デプロイ

### 前提条件
1. **watchme-networkインフラストラクチャが起動済み**
   ```bash
   cd /home/ubuntu/watchme-server-configs
   docker-compose -f docker-compose.infra.yml up -d
   ```

2. **環境変数ファイル（.env）が配置済み**
   - `/home/ubuntu/vibe-analysis-transcriber/.env`

### デプロイ手順

#### 方法1: GitHub Actions自動デプロイ（推奨）
```bash
# ローカルでコードをpush
git push origin main

# GitHub Actionsが自動的にEC2にデプロイ
```

#### 方法2: 手動でrun-prod.shを使用
```bash
# EC2サーバー上で実行
cd /home/ubuntu/vibe-analysis-transcriber
./run-prod.sh
```

### 動作確認
```bash
# ヘルスチェック
curl http://localhost:8013/

# コンテナ状態確認
docker ps | grep vibe-analysis-transcriber

# ログ確認
docker logs -f vibe-analysis-transcriber
```

### 緊急時の手動デプロイ手順

#### SDKアップグレード（緊急修正の場合）

```bash
# EC2サーバーにSSH接続
ssh -i ~/watchme-key.pem ubuntu@3.24.16.82

# コンテナ内でSDKをアップグレード
docker exec vibe-analysis-transcriber pip install --upgrade azure-cognitiveservices-speech==1.45.0

# コンテナを再起動
docker restart vibe-analysis-transcriber

# ログを確認
docker logs -f vibe-analysis-transcriber
```

### 動作確認

#### 1. APIの生存確認

```bash
# ローカルから
curl https://api.hey-watch.me/vibe-analysis-transcriber/

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
curl -X POST "https://api.hey-watch.me/vibe-analysis-transcriber/fetch-and-transcribe" \
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
curl -X POST "https://api.hey-watch.me/vibe-analysis-transcriber/fetch-and-transcribe" \
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
docker logs vibe-analysis-transcriber --tail 50 | grep "認識"
```

## 📡 API エンドポイント

### POST /analyze/azure

音声ファイルを直接アップロードしてASR処理（ローカルAPI用）

**リクエスト:**
- `file`: 音声ファイル (.wav, .mp3, .m4a)
- 最大ファイルサイズ: 25MB

### POST /fetch-and-transcribe

WatchMeシステム統合エンドポイント - Supabaseからファイル情報を取得してS3から音声ファイルをダウンロード後、ASR実行

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

## 💻 ローカル開発環境（オプション）

**注意: ローカル開発環境はオプションです。本番環境ではDockerコンテナを使用してください。**

### 1. 仮想環境の作成と有効化

```bash
cd /Users/kaya.matsumoto/projects/watchme/api/vibe-analysis/transcriber-v2
python3 -m venv venv
source venv/bin/activate
```

### 2. 依存関係のインストール

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 環境変数の設定

上記「本番環境での運用」セクションの環境変数設定を参照してください。

### 4. ローカルでの起動

```bash
# 仮想環境で起動
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8013 --reload
```

### 5. ローカルテスト

```bash
# 仮想環境を有効化
source venv/bin/activate

# テスト実行
python test_transcribe.py
```

期待される出力：
```
✅ テスト成功！
認識結果: [音声の内容]
```

---

## 🔧 技術仕様

- **Python**: 3.11以上
- **フレームワーク**: FastAPI
- **ASRプロバイダー**:
  - Azure Speech Services SDK 1.45.0
  - Groq Whisper API (groq>=0.4.0)
- **統合システム**: WatchMe Platform (v2.0.0〜)
  - **データベース**: Supabase (Python SDK 2.10.0)
  - **ファイルストレージ**: AWS S3 (boto3 1.35.57)
- **対応形式**: .wav, .mp3, .m4a
- **対応言語**: 日本語、英語など（プロバイダーによる）
- **ポート**: 8013（ローカル・本番環境で統一）

## 📦 依存関係

主要なパッケージ：
```txt
azure-cognitiveservices-speech==1.45.0  # Azure ASR
groq>=0.4.0                             # Groq Whisper API
fastapi==0.115.12
uvicorn==0.34.2
pydantic==2.11.5
boto3==1.35.57                          # AWS S3
supabase==2.10.0                        # Supabase Python SDK
tenacity>=8.2.0                         # リトライ処理
pytz==2024.1                            # タイムゾーン処理
```

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
| **処理済み・発話あり** | 処理して正常なASR結果取得 | `completed` | `実際の内容` |

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
1. **ログで処理フローを確認** - `docker logs vibe-analysis-transcriber --tail 100`
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
- 本番環境URL: https://api.hey-watch.me/vibe-analysis-transcriber/