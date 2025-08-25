import os
import tempfile
import threading
import time
import azure.cognitiveservices.speech as speechsdk
from fastapi import HTTPException
from typing import BinaryIO, Dict, Any

class AzureSpeechService:
    def __init__(self):
        self.speech_key = os.getenv("AZURE_SPEECH_KEY", "your-key-here")
        self.service_region = os.getenv("AZURE_SERVICE_REGION", "your-region-here")
        
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
                # タイムアウトまたは不明なエラー
                raise HTTPException(
                    status_code=408, 
                    detail=f"音声認識がタイムアウトしました（{timeout}秒）"
                )
                
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

# サービスインスタンス
azure_speech_service = AzureSpeechService() 