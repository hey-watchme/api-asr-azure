import os
import tempfile
import threading
import time
import azure.cognitiveservices.speech as speechsdk
from fastapi import HTTPException
from typing import BinaryIO, Dict, Any, List, Set
import boto3
from botocore.exceptions import ClientError
from supabase import create_client, Client
from dotenv import load_dotenv
import logging
from datetime import datetime

# 環境変数読み込み
load_dotenv()

# ロギング設定
logger = logging.getLogger(__name__)

class AzureSpeechService:
    def __init__(self):
        # Azure Speech Service設定
        self.speech_key = os.getenv("AZURE_SPEECH_KEY", "your-key-here")
        self.service_region = os.getenv("AZURE_SERVICE_REGION", "your-region-here")
        
        # Supabase設定
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URLおよびSUPABASE_KEYが設定されていません")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
        print(f"Supabase接続設定完了: {supabase_url}")
        
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
        print(f"AWS S3接続設定完了: バケット={self.s3_bucket_name}, リージョン={aws_region}")
        
        # Azure Speech Config
        self.speech_config = speechsdk.SpeechConfig(
            subscription=self.speech_key, 
            region=self.service_region
        )
        
        # 言語設定（日本語）
        self.speech_config.speech_recognition_language = "ja-JP"
        
        # 高精度モードのための設定
        try:
            # 1. DICTATION モード（最高精度、時間重視しない）
            self.speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_RecoMode, "DICTATION")
            
            # 2. 詳細結果を要求
            self.speech_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_RequestDetailedResultTrueFalse, "true")
            
            # 3. 音声品質の最適化（長時間待機）
            self.speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "5000")
            self.speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "15000")
            
            # 4. セグメンテーションの最適化
            self.speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "3000")
            
            # 5. 句読点の自動挿入
            self.speech_config.enable_dictation = True
            
        except Exception as e:
            # 一部の設定が利用できない場合はスキップ
            print(f"一部の高度な設定をスキップしました: {e}")
    
    async def transcribe_audio(self, audio_file: BinaryIO, filename: str, detailed: bool = False, high_accuracy: bool = False) -> Dict[str, Any]:
        """音声ファイルを文字起こしする"""
        try:
            # 一時ファイルに保存
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file:
                content = audio_file.read()
                temp_file.write(content)
                temp_file_path = temp_file.name
            
            # Azure Speech Recognition
            audio_input = speechsdk.AudioConfig(filename=temp_file_path)
            
            # 高精度モードの場合、専用設定を適用
            if high_accuracy:
                # 高精度用の設定をコピー
                high_accuracy_config = speechsdk.SpeechConfig(
                    subscription=self.speech_key, 
                    region=self.service_region
                )
                high_accuracy_config.speech_recognition_language = "ja-JP"
                
                try:
                    # 最高精度設定
                    high_accuracy_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_RecoMode, "DICTATION")
                    high_accuracy_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_RequestDetailedResultTrueFalse, "true")
                    high_accuracy_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs, "8000")
                    high_accuracy_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "20000")
                    high_accuracy_config.enable_dictation = True
                    
                    # N-Best結果を取得（複数候補から最適を選択）
                    high_accuracy_config.set_property(speechsdk.PropertyId.SpeechServiceResponse_RequestWordLevelTimestamps, "true")
                    
                except Exception as e:
                    print(f"高精度設定の一部をスキップ: {e}")
                
                speech_recognizer = speechsdk.SpeechRecognizer(
                    speech_config=high_accuracy_config, 
                    audio_config=audio_input
                )
            else:
                speech_recognizer = speechsdk.SpeechRecognizer(
                    speech_config=self.speech_config, 
                    audio_config=audio_input
                )
            
            # 処理時間計測開始
            start_time = time.time()
            
            # 長時間音声認識のための設定
            all_results = []
            recognition_errors = []
            done = threading.Event()
            
            def handle_final_result(evt):
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    all_results.append(evt.result.text)
                elif evt.result.reason == speechsdk.ResultReason.NoMatch:
                    recognition_errors.append({
                        "type": "NoMatch",
                        "detail": "音声セグメントが認識できませんでした"
                    })
                elif evt.result.reason == speechsdk.ResultReason.Canceled:
                    cancellation_details = evt.result.cancellation_details
                    recognition_errors.append({
                        "type": "Canceled",
                        "reason": str(cancellation_details.reason),
                        "error_details": cancellation_details.error_details or "詳細なし"
                    })
            
            def handle_canceled(evt):
                # セッション全体のキャンセル
                cancellation_details = evt.cancellation_details
                recognition_errors.append({
                    "type": "SessionCanceled",
                    "reason": str(cancellation_details.reason),
                    "error_details": cancellation_details.error_details or "詳細なし"
                })
                done.set()
            
            def handle_session_stopped(evt):
                done.set()
            
            # イベントハンドラーを設定
            speech_recognizer.recognized.connect(handle_final_result)
            speech_recognizer.canceled.connect(handle_canceled)
            speech_recognizer.session_stopped.connect(handle_session_stopped)
            
            # 連続音声認識開始
            speech_recognizer.start_continuous_recognition()
            
            # 認識完了まで待機（高精度モードは最大10分）
            timeout = 600 if high_accuracy else 300  # 高精度: 10分, 通常: 5分
            done.wait(timeout=timeout)
            
            # 認識停止
            speech_recognizer.stop_continuous_recognition()
            
            # 処理時間計測終了
            processing_time = time.time() - start_time
            
            # 一時ファイル削除
            os.unlink(temp_file_path)
            
            # 結果の分析と適切なレスポンス生成
            if all_results:
                # 成功: 認識結果がある場合
                full_transcription = " ".join(all_results)
                
                # 基本的な信頼度計算（常に含める）
                text_length = len(full_transcription)
                base_confidence = 0.05 if high_accuracy else 0.0  # 高精度モードボーナス
                
                if text_length > 50:
                    confidence = min(0.98, 0.95 + base_confidence)
                elif text_length > 20:
                    confidence = min(0.95, 0.85 + base_confidence)
                elif text_length > 5:
                    confidence = min(0.90, 0.75 + base_confidence)
                else:
                    confidence = min(0.85, 0.60 + base_confidence)
                
                # 基本的な単語数計算
                words = full_transcription.split()
                word_count = len(words)
                estimated_duration = round(processing_time * 0.8, 2)
                
                # 結果の構築（常に基本情報を含める）
                result = {
                    "transcription": full_transcription,
                    "processing_time": round(processing_time, 2),
                    "confidence": confidence,
                    "word_count": word_count,
                    "estimated_duration": estimated_duration
                }
                
                # 詳細モードの場合、追加情報を含める
                if detailed:
                    # 詳細モードでは追加の統計情報を含める
                    result["detailed_mode"] = True
                
                # 高精度モードの情報を追加
                if high_accuracy:
                    result["mode"] = "high_accuracy"
                    result["timeout_used"] = timeout
                
                # 部分的なエラーがあった場合は警告として含める
                if recognition_errors:
                    result["warnings"] = recognition_errors
                
                return result
            
            elif recognition_errors:
                # 失敗: エラーの種類に応じて適切なHTTPステータスを返す
                self._handle_recognition_errors(recognition_errors)
            
            else:
                # 認識結果が空の場合（発話なし）
                return {
                    "transcription": "",  # 空文字列として返す（「発話なし」は呼び出し側で設定）
                    "processing_time": round(time.time() - start_time, 2),
                    "confidence": 0.0,
                    "word_count": 0,
                    "estimated_duration": 0.0,
                    "no_speech_detected": True  # 発話なしフラグを追加
                }
                
        except Exception as e:
            # 一時ファイルが残っている場合は削除
            if 'temp_file_path' in locals():
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            raise HTTPException(status_code=500, detail=f"音声処理エラー: {str(e)}")
    
    def _handle_recognition_errors(self, recognition_errors):
        """認識エラーの種類に応じて適切なHTTPExceptionを発生させる"""
        # 最も重要なエラーを特定
        has_no_match = any(err["type"] == "NoMatch" for err in recognition_errors)
        has_canceled = any(err["type"] in ["Canceled", "SessionCanceled"] for err in recognition_errors)
        
        if has_canceled:
            # キャンセルエラーの詳細を取得
            canceled_errors = [err for err in recognition_errors if err["type"] in ["Canceled", "SessionCanceled"]]
            error_details = []
            
            for err in canceled_errors:
                if err.get("error_details"):
                    error_details.append(f"{err['type']}: {err['reason']} - {err['error_details']}")
                else:
                    error_details.append(f"{err['type']}: {err['reason']}")
            
            raise HTTPException(
                status_code=500,
                detail=f"音声認識がキャンセルされました: {'; '.join(error_details)}"
            )
        
        elif has_no_match:
            # NoMatchエラーの場合
            no_match_count = sum(1 for err in recognition_errors if err["type"] == "NoMatch")
            
            if no_match_count == len(recognition_errors):
                # すべてがNoMatchの場合
                raise HTTPException(
                    status_code=400,
                    detail="音声が認識できませんでした（NoMatch）。音声が不明瞭、無音、または対応していない言語の可能性があります。"
                )
            else:
                # 一部がNoMatchの場合
                raise HTTPException(
                    status_code=400,
                    detail=f"音声の一部が認識できませんでした（{no_match_count}セグメント）。音声品質を確認してください。"
                )
        
        else:
            # その他の不明なエラー
            error_summary = "; ".join([f"{err['type']}: {err.get('detail', '不明')}" for err in recognition_errors])
            raise HTTPException(
                status_code=500,
                detail=f"音声認識で予期しないエラーが発生しました: {error_summary}"
            )
    
    async def fetch_and_transcribe_files(self, request):
        """S3から音声ファイルを取得してAzure Speech Serviceで文字起こし実行"""
        from app.models import FetchAndTranscribeRequest  # 循環インポート回避
        
        start_time = time.time()
        
        # リクエストの処理
        if request.device_id and request.local_date:
            # 新しいインターフェース: device_id + local_date + time_blocks
            logger.info(f"新インターフェース使用: device_id={request.device_id}, local_date={request.local_date}, time_blocks={request.time_blocks}")
            
            # audio_filesテーブルから該当するファイルを検索
            query = self.supabase.table('audio_files') \
                .select('file_path, device_id, recorded_at, local_date, time_block, transcriptions_status') \
                .eq('device_id', request.device_id) \
                .eq('local_date', request.local_date) \
                .eq('transcriptions_status', 'pending')
            
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
                        
                        # Azure Speech Serviceで文字起こし
                        with open(tmp_file_path, 'rb') as audio_file_handle:
                            transcription_result = await self.transcribe_audio(
                                audio_file_handle, 
                                os.path.basename(file_path),
                                detailed=False,
                                high_accuracy=True  # Azure Speech Service高精度モード使用
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
                        
                        # upsert（既存データは更新、新規データは挿入）
                        response = self.supabase.table('vibe_whisper').upsert(data).execute()
                        
                        # ★★★ 改善されたエラーハンドリングとロギング ★★★
                        
                        # 1. 常にレスポンスの主要な情報をログに出力し、成功・失敗両方のパターンを記録
                        #    getattrを使い、存在しない属性でエラーが出ないようにする
                        status_code = getattr(response, 'status_code', 'N/A')
                        logger.info(f"Supabase upsert response: data={response.data}, count={response.count}, status_code={status_code}")
                        
                        # 2. 堅牢なエラーチェック
                        #    - upsert成功時は通常、dataに挿入/更新されたレコード(配列)が返る。
                        #    - 失敗時や何も起きなかった場合は data が空になることがある。
                        #    - ここでは「dataに何も返ってこなかった」場合を失敗の疑いとして検知する。
                        if not response.data:
                            # 失敗と断定する前に追加情報をログに出力
                            logger.warning("⚠️ Supabase upsert returned no data. This might indicate an error or an empty operation.")
                            logger.warning(f"   - Request Payload: {data}")
                            logger.warning(f"   - Full Response Object: {response}")
                            
                            # 50%の確率で失敗する問題のデバッグのため、これをクリティカルなエラーとして扱い、
                            # audio_files のステータスが 'completed' になるのを防ぐ。
                            # もし「データがなくても正常」なケースがある場合は、このロジックの再検討が必要。
                            raise Exception("Supabase upsert returned no data, treating as failure to prevent data inconsistency.")
                        
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
                        if transcription:
                            logger.info(f"✅ {file_path}: 文字起こし完了・Supabase保存済み (Azure Speech Service) - 発話内容: {len(transcription)}文字")
                        else:
                            logger.info(f"✅ {file_path}: 処理完了・発話なし・Supabase保存済み (Azure Speech Service) - 「発話なし」として保存")
                    
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
                "message": f"{len(file_paths)}件中{len(successfully_transcribed)}件をAzure Speech Serviceで正常に処理しました"
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
                "message": f"{len(file_paths)}件中{len(successfully_transcribed)}件をAzure Speech Serviceで正常に処理しました"
            }

# サービスインスタンス
azure_speech_service = AzureSpeechService() 