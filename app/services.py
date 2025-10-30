import os
import tempfile
import time
from fastapi import HTTPException
from typing import BinaryIO, Dict, Any, List, Set
import boto3
from botocore.exceptions import ClientError
from supabase import create_client, Client
from dotenv import load_dotenv
import logging
from datetime import datetime
from app.asr_providers import get_current_asr, CURRENT_PROVIDER, CURRENT_MODEL

# 環境変数読み込み
load_dotenv()

# ロギング設定
logger = logging.getLogger(__name__)

class TranscriberService:
    def __init__(self):
        # ASRプロバイダーを取得
        self.asr_provider = get_current_asr()
        logger.info(f"ASRプロバイダー初期化完了: {self.asr_provider.provider_name}/{self.asr_provider.model_name}")

        # Supabase設定
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URLおよびSUPABASE_KEYが設定されていません")

        self.supabase: Client = create_client(supabase_url, supabase_key)
        logger.info(f"Supabase接続設定完了: {supabase_url}")

        # AWS S3設定
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.s3_bucket_name = os.getenv('S3_BUCKET_NAME', 'watchme-vault')
        aws_region = os.getenv('AWS_REGION', 'us-east-1')

        if not aws_access_key_id or not aws_secret_access_key:
            raise ValueError("AWS_ACCESS_KEY_IDおよびAWS_SECRET_ACCESS_KEYが設定されていません")

        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )
        logger.info(f"AWS S3接続設定完了: バケット={self.s3_bucket_name}, リージョン={aws_region}")
    async def fetch_and_transcribe_files(self, request):
        """S3から音声ファイルを取得してASRプロバイダーで文字起こし実行"""
        from app.models import FetchAndTranscribeRequest  # 循環インポート回避
        
        start_time = time.time()
        
        # リクエストの処理
        if request.device_id and request.local_date:
            # 新しいインターフェース: device_id + local_date + time_blocks
            logger.info(f"新インターフェース使用: device_id={request.device_id}, local_date={request.local_date}, time_blocks={request.time_blocks}")
            
            # audio_filesテーブルから該当するファイルを検索
            # すべてのファイルを取得（ステータスに関係なく処理可能にする）
            # 明示的に処理を指定した場合は、completedも含めて再処理できるようにする
            query = self.supabase.table('audio_files') \
                .select('file_path, device_id, recorded_at, local_date, time_block, transcriptions_status') \
                .eq('device_id', request.device_id) \
                .eq('local_date', request.local_date)
            
            # time_blocksが指定されている場合はフィルタを追加
            if request.time_blocks:
                query = query.in_('time_block', request.time_blocks)
            
            # クエリ実行
            try:
                response = query.execute()
                audio_files = response.data
                logger.info(f"audio_filesテーブルから{len(audio_files)}件のファイルを取得")
            except Exception as e:
                logger.error(f"audio_filesテーブルのクエリエラー: {str(e)}")
                raise HTTPException(status_code=500, detail=f"データベースクエリエラー: {str(e)}")
            
            # file_pathsリストを構築
            file_paths = [file['file_path'] for file in audio_files]
            
            if not file_paths:
                execution_time = time.time() - start_time
                return {
                    "status": "success",
                    "summary": {
                        "total_files": 0,
                        "already_completed": 0,
                        "pending_processed": 0,
                        "errors": 0
                    },
                    "device_id": request.device_id,
                    "local_date": request.local_date,
                    "time_blocks_requested": request.time_blocks,
                    "processed_time_blocks": [],
                    "execution_time_seconds": round(execution_time, 1),
                    "message": "処理対象のファイルがありません（全て処理済みまたは該当なし）"
                }
        
        elif request.file_paths:
            # 既存のインターフェース: file_pathsを直接指定
            logger.info(f"既存インターフェース使用: file_paths={len(request.file_paths)}件")
            file_paths = request.file_paths
            audio_files = None  # 後方互換性のため
        
        else:
            # ここに来ることはない（model_validatorで検証済み）
            raise HTTPException(
                status_code=400,
                detail="device_id + local_dateまたはfile_pathsのどちらかを指定してください"
            )
        
        if not file_paths:
            # file_pathsが空の場合は、処理対象なしとして正常終了
            execution_time = time.time() - start_time
            
            return {
                "status": "success",
                "summary": {
                    "total_files": 0,
                    "already_completed": 0,
                    "pending_processed": 0,
                    "errors": 0
                },
                "processed_files": [],
                "execution_time_seconds": round(execution_time, 1),
                "message": "処理対象のファイルがありません"
            }
        
        logger.info(f"処理対象: {len(file_paths)}件のファイル")
        
        # 処理対象ファイルの情報を構築
        files_to_process = []
        device_ids = set()
        dates = set()
        
        # 新インターフェースの場合
        if audio_files:
            for audio_file in audio_files:
                files_to_process.append({
                    'file_path': audio_file['file_path'],
                    'device_id': audio_file['device_id'],
                    'local_date': audio_file['local_date'],
                    'time_block': audio_file['time_block']
                })
                device_ids.add(audio_file['device_id'])
                dates.add(audio_file['local_date'])
        
        # 既存インターフェースの場合（file_pathから情報を抽出）
        else:
            for file_path in file_paths:
                # file_pathから情報を抽出
                # 例: files/d067d407-cf73-4174-a9c1-d91fb60d64d0/2025-07-19/14-30/audio.wav
                parts = file_path.split('/')
                if len(parts) >= 5:
                    device_id = parts[1]  # d067d407-cf73-4174-a9c1-d91fb60d64d0
                    date_part = parts[2]  # 2025-07-19
                    time_part = parts[3]  # 14-30
                    
                    device_ids.add(device_id)
                    dates.add(date_part)
                    
                    files_to_process.append({
                        'file_path': file_path,
                        'device_id': device_id,
                        'local_date': date_part,
                        'time_block': time_part
                    })
        
        # 実際の音声ダウンロードと文字起こし処理
        # 処理結果を記録
        successfully_transcribed = []
        error_files = []
        
        for audio_file in files_to_process:
            try:
                file_path = audio_file['file_path']
                time_block = audio_file['time_block']
                local_date = audio_file['local_date']
                device_id = audio_file['device_id']
                
                # ===== 処理制限モード（コスト削減のための運用制限） =====
                # 特定デバイスの夜間処理をスキップ
                # 今後の運用で必要に応じて環境変数化やDB管理への移行を検討
                
                # 制限対象デバイス設定（現在はハードコード、将来的には環境変数やDB管理へ）
                RESTRICTED_DEVICES = {
                    '9f7d6e27-98c3-4c19-bdfb-f7fda58b9a93': {
                        'skip_hours': list(range(23, 24)) + list(range(0, 6)),  # 23:00-05:59をスキップ
                        'reason': 'テストデバイス - 夜間処理制限'
                    }
                    # 今後、必要に応じて他のデバイスも追加可能
                    # 'device-id-2': {'skip_hours': [0,1,2,3,4,5], 'reason': '別の理由'}
                }
                
                # デバイスが制限対象かチェック
                if device_id in RESTRICTED_DEVICES:
                    hour = int(time_block.split('-')[0])
                    device_config = RESTRICTED_DEVICES[device_id]
                    
                    if hour in device_config['skip_hours']:
                        # 処理をスキップ
                        logger.info(f"⏭️ 処理制限モード: {device_id} - {time_block} - 理由: {device_config['reason']}")
                        
                        # ステータスを'skipped'に更新（将来的に専用ステータスの追加も検討）
                        try:
                            self.supabase.table('audio_files') \
                                .update({'transcriptions_status': 'skipped'}) \
                                .eq('file_path', file_path) \
                                .execute()
                            logger.info(f"ステータスを'skipped'に更新: {file_path}")
                        except Exception as status_update_error:
                            logger.error(f"ステータス更新エラー: {str(status_update_error)}")
                        
                        # 次のファイルへ
                        continue
                
                # ===== 処理制限モードここまで =====
                
                # 一時ファイルに音声データをダウンロード
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    tmp_file_path = tmp_file.name
                    
                    try:
                        # S3からファイルをダウンロード（file_pathをそのまま使用）
                        self.s3_client.download_file(self.s3_bucket_name, file_path, tmp_file_path)

                        # ASRプロバイダーで文字起こし
                        with open(tmp_file_path, 'rb') as audio_file_handle:
                            transcription_result = await self.asr_provider.transcribe_audio(
                                audio_file_handle,
                                os.path.basename(file_path),
                                detailed=False,
                                high_accuracy=True  # 高精度モード使用
                            )
                        
                        transcription = transcription_result["transcription"].strip()
                        
                        # Azure利用上限チェック（200応答だが結果が空で、発話検出フラグもない場合）
                        is_quota_exceeded = False
                        if not transcription and not transcription_result.get("no_speech_detected", False):
                            # 現在時刻をチェック（UTC）
                            import pytz
                            from datetime import datetime as dt
                            current_utc = dt.now(pytz.UTC)
                            current_jst = current_utc.astimezone(pytz.timezone('Asia/Tokyo'))
                            
                            # 日本時間で0:00-9:00の間の場合、利用上限の可能性が高い
                            if current_jst.hour < 9:
                                is_quota_exceeded = True
                                logger.warning(f"⚠️ Azure利用上限に達した可能性があります（JST: {current_jst.strftime('%H:%M')}）")
                                logger.warning(f"   日本時間09:00以降に再実行してください")
                        
                        # 発話なしの判定と明確な区別
                        final_transcription = transcription if transcription else "発話なし"
                        
                        # vibe_whisperテーブルに保存（発話なしの場合は明確に「発話なし」を保存）
                        data = {
                            "device_id": device_id,
                            "date": local_date,  # リクエストから受け取った日付をそのまま使用
                            "time_block": time_block,
                            "transcription": final_transcription,
                            "created_at": datetime.utcnow().isoformat()  # 現在のUTC時刻をISO形式で保存
                        }
                        
                        # upsert（既存データは更新、新規データは挿入）- リトライ付き
                        max_retries = 3
                        retry_count = 0
                        upsert_success = False
                        
                        while retry_count < max_retries and not upsert_success:
                            try:
                                if retry_count > 0:
                                    logger.info(f"Supabase upsert retry {retry_count}/{max_retries}")
                                    time.sleep(1 * retry_count)  # 1秒, 2秒, 3秒の遅延
                                
                                response = self.supabase.table('vibe_whisper').upsert(data).execute()
                                
                                # レスポンスログ
                                status_code = getattr(response, 'status_code', 'N/A')
                                logger.info(f"Supabase upsert response: data={response.data}, count={response.count}, status_code={status_code}")
                                
                                # データが返ってこない場合のハンドリング
                                if not response.data:
                                    logger.warning(f"⚠️ Supabase upsert returned no data (attempt {retry_count + 1}/{max_retries})")
                                    logger.warning(f"   - Request Payload: {data}")
                                    
                                    # データが空でも、既存レコードの更新の場合は成功とみなす
                                    # vibe_whisperテーブルから既存レコードを確認
                                    check_response = self.supabase.table('vibe_whisper') \
                                        .select('*') \
                                        .eq('device_id', device_id) \
                                        .eq('date', local_date) \
                                        .eq('time_block', time_block) \
                                        .execute()
                                    
                                    if check_response.data:
                                        logger.info("✅ Existing record found - treating as successful update")
                                        upsert_success = True
                                    else:
                                        retry_count += 1
                                        if retry_count >= max_retries:
                                            raise Exception(f"Supabase upsert failed after {max_retries} attempts")
                                else:
                                    upsert_success = True
                                    
                            except Exception as e:
                                logger.error(f"Supabase upsert error (attempt {retry_count + 1}): {str(e)}")
                                retry_count += 1
                                if retry_count >= max_retries:
                                    raise
                        
                        # audio_filesテーブルのtranscriptions_statusをcompletedに更新
                        try:
                            update_response = self.supabase.table('audio_files') \
                                .update({'transcriptions_status': 'completed'}) \
                                .eq('file_path', file_path) \
                                .execute()
                            
                            # 更新が成功したかチェック
                            if update_response.data:
                                logger.info(f"✅ audio_filesテーブルのステータス更新成功: {len(update_response.data)}件更新")
                                logger.info(f"   file_path: {file_path}")
                            else:
                                logger.warning(f"⚠️ audio_filesテーブルのステータス更新: 対象レコードが見つかりません")
                                logger.warning(f"   file_path: {file_path}")
                                
                        except Exception as update_error:
                            logger.error(f"❌ audio_filesテーブルのステータス更新エラー: {str(update_error)}")
                            logger.error(f"   file_path: {file_path}")
                        
                        successfully_transcribed.append({
                            'file_path': file_path,
                            'time_block': time_block
                        })
                        
                        # 処理結果に応じたログ出力
                        provider_info = f"{self.asr_provider.provider_name}/{self.asr_provider.model_name}"
                        if transcription:
                            logger.info(f"✅ {file_path}: 文字起こし完了・Supabase保存済み ({provider_info}) - 発話内容: {len(transcription)}文字")
                        else:
                            logger.info(f"✅ {file_path}: 処理完了・発話なし・Supabase保存済み ({provider_info}) - 「発話なし」として保存")
                    
                    finally:
                        # 一時ファイルを削除
                        if os.path.exists(tmp_file_path):
                            os.unlink(tmp_file_path)
            
            except ClientError as e:
                error_msg = f"{audio_file['file_path']}: S3エラー - {str(e)}"
                logger.error(f"❌ {error_msg}")
                error_files.append(audio_file)
                
                # エラー時にステータスを更新
                try:
                    self.supabase.table('audio_files') \
                        .update({'transcriptions_status': 'failed'}) \
                        .eq('file_path', audio_file['file_path']) \
                        .execute()
                    logger.info(f"ステータスを'failed'に更新: {audio_file['file_path']}")
                except Exception as status_update_error:
                    logger.error(f"ステータス更新エラー: {str(status_update_error)}")
            
            except Exception as e:
                error_message = str(e)
                logger.error(f"❌ {audio_file['file_path']}: エラー - {error_message}")
                error_files.append(audio_file)
                
                # エラー時にステータスを更新
                try:
                    # Quota exceededエラーの判定（エラーメッセージから検出）
                    if "quota exceeded" in error_message.lower():
                        status = 'quota_exceeded'
                        logger.warning(f"⚠️ Azure利用上限エラーを検出しました")
                    else:
                        status = 'failed'
                    
                    self.supabase.table('audio_files') \
                        .update({'transcriptions_status': status}) \
                        .eq('file_path', audio_file['file_path']) \
                        .execute()
                    logger.info(f"ステータスを'{status}'に更新: {audio_file['file_path']}")
                except Exception as status_update_error:
                    logger.error(f"ステータス更新エラー: {str(status_update_error)}")
        
        # 処理結果を返す
        execution_time = time.time() - start_time
        
        # レスポンスの構築（インターフェースによって異なる）
        if request.device_id and request.local_date:
            # 新インターフェースのレスポンス
            return {
                "status": "success",
                "summary": {
                    "total_files": len(file_paths),
                    "pending_processed": len(successfully_transcribed),
                    "errors": len(error_files)
                },
                "device_id": request.device_id,
                "local_date": request.local_date,
                "time_blocks_requested": request.time_blocks,
                "processed_time_blocks": [f['time_block'] for f in successfully_transcribed],
                "error_time_blocks": [f['time_block'] for f in error_files] if error_files else None,
                "execution_time_seconds": round(execution_time, 1),
                "message": f"{len(file_paths)}件中{len(successfully_transcribed)}件を{self.asr_provider.provider_name}で正常に処理しました",
                "asr_provider": self.asr_provider.provider_name,
                "asr_model": self.asr_provider.model_name
            }
        else:
            # 既存インターフェースのレスポンス（後方互換性）
            return {
                "status": "success",
                "summary": {
                    "total_files": len(file_paths),
                    "pending_processed": len(successfully_transcribed),
                    "errors": len(error_files)
                },
                "processed_files": [f['file_path'] for f in successfully_transcribed],
                "processed_time_blocks": [f['time_block'] for f in successfully_transcribed],
                "error_files": [f['file_path'] for f in error_files] if error_files else None,
                "execution_time_seconds": round(execution_time, 1),
                "message": f"{len(file_paths)}件中{len(successfully_transcribed)}件を{self.asr_provider.provider_name}で正常に処理しました",
                "asr_provider": self.asr_provider.provider_name,
                "asr_model": self.asr_provider.model_name
            }

# サービスインスタンス
transcriber_service = TranscriberService() 