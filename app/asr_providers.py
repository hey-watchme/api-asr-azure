"""
ASRプロバイダー抽象化レイヤー

複数のASRプロバイダー（Azure、Groq等）を統一的に扱うための抽象化層。
プロバイダーの切り替えは、このファイルの先頭の定数を変更するだけで可能。
"""

from abc import ABC, abstractmethod
from typing import BinaryIO, Dict, Any, Optional
import os
import tempfile
import threading
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

# ==========================================
# 🔧 現在使用中のASRプロバイダー設定
# ==========================================
# この行を変更するだけでプロバイダーを切り替え可能
CURRENT_PROVIDER = "deepgram"  # "azure", "groq", または "deepgram"
CURRENT_MODEL = "nova-3"  # Azure: "ja-JP", Groq: "whisper-large-v3-turbo", Deepgram: "nova-3"
# ==========================================


class ASRProvider(ABC):
    """ASRプロバイダーの抽象基底クラス"""

    @abstractmethod
    async def transcribe_audio(
        self,
        audio_file: BinaryIO,
        filename: str,
        detailed: bool = False,
        high_accuracy: bool = False
    ) -> Dict[str, Any]:
        """
        音声ファイルを文字起こしする

        Args:
            audio_file (BinaryIO): 音声ファイルのバイナリストリーム
            filename (str): ファイル名
            detailed (bool): 詳細モード
            high_accuracy (bool): 高精度モード

        Returns:
            Dict[str, Any]: 文字起こし結果
                - transcription: 文字起こしテキスト
                - processing_time: 処理時間（秒）
                - confidence: 信頼度（0.0-1.0）
                - word_count: 単語数
                - estimated_duration: 推定音声長（秒）
                - no_speech_detected: 発話なしフラグ（オプション）
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """使用中のプロバイダー名を返す"""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """使用中のモデル名を返す"""
        pass


class AzureProvider(ASRProvider):
    """Azure Speech Services プロバイダー"""

    def __init__(self, model: str = "ja-JP"):
        """
        Args:
            model (str): 言語コード（例: "ja-JP", "en-US"）
        """
        import azure.cognitiveservices.speech as speechsdk  # 遅延インポート

        # Azure Speech Service設定
        self.speech_key = os.getenv("AZURE_SPEECH_KEY")
        self.service_region = os.getenv("AZURE_SERVICE_REGION")

        if not self.speech_key or not self.service_region:
            raise ValueError("AZURE_SPEECH_KEYおよびAZURE_SERVICE_REGIONが設定されていません")

        self._model = model

        # Azure Speech Config
        self.speech_config = speechsdk.SpeechConfig(
            subscription=self.speech_key,
            region=self.service_region
        )

        # 言語設定
        self.speech_config.speech_recognition_language = model

        # 高精度モードのための設定
        try:
            # 1. DICTATION モード（最高精度）
            self.speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceConnection_RecoMode,
                "DICTATION"
            )

            # 2. 詳細結果を要求
            self.speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceResponse_RequestDetailedResultTrueFalse,
                "true"
            )

            # 3. 音声品質の最適化
            self.speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs,
                "5000"
            )
            self.speech_config.set_property(
                speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
                "15000"
            )

            # 4. セグメンテーションの最適化
            self.speech_config.set_property(
                speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs,
                "3000"
            )

            # 5. 句読点の自動挿入
            self.speech_config.enable_dictation = True

        except Exception as e:
            logger.warning(f"一部の高度な設定をスキップしました: {e}")

        logger.info(f"Azure Speech Service初期化完了: region={self.service_region}, language={model}")

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=5),
        retry=retry_if_exception_type(Exception)
    )
    async def transcribe_audio(
        self,
        audio_file: BinaryIO,
        filename: str,
        detailed: bool = False,
        high_accuracy: bool = False
    ) -> Dict[str, Any]:
        """Azure Speech Serviceで音声ファイルを文字起こし（リトライ付き）"""
        import azure.cognitiveservices.speech as speechsdk

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
                high_accuracy_config = speechsdk.SpeechConfig(
                    subscription=self.speech_key,
                    region=self.service_region
                )
                high_accuracy_config.speech_recognition_language = self._model

                try:
                    high_accuracy_config.set_property(
                        speechsdk.PropertyId.SpeechServiceConnection_RecoMode,
                        "DICTATION"
                    )
                    high_accuracy_config.set_property(
                        speechsdk.PropertyId.SpeechServiceResponse_RequestDetailedResultTrueFalse,
                        "true"
                    )
                    high_accuracy_config.set_property(
                        speechsdk.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs,
                        "8000"
                    )
                    high_accuracy_config.set_property(
                        speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
                        "20000"
                    )
                    high_accuracy_config.enable_dictation = True
                    high_accuracy_config.set_property(
                        speechsdk.PropertyId.SpeechServiceResponse_RequestWordLevelTimestamps,
                        "true"
                    )
                except Exception as e:
                    logger.warning(f"高精度設定の一部をスキップ: {e}")

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

            # 認識完了まで待機
            timeout = 600 if high_accuracy else 300
            done.wait(timeout=timeout)

            # 認識停止
            speech_recognizer.stop_continuous_recognition()

            # 処理時間計測終了
            processing_time = time.time() - start_time

            # 一時ファイル削除
            os.unlink(temp_file_path)

            # 結果の分析と適切なレスポンス生成
            if all_results:
                full_transcription = " ".join(all_results)

                # 信頼度計算
                text_length = len(full_transcription)
                base_confidence = 0.05 if high_accuracy else 0.0

                if text_length > 50:
                    confidence = min(0.98, 0.95 + base_confidence)
                elif text_length > 20:
                    confidence = min(0.95, 0.85 + base_confidence)
                elif text_length > 5:
                    confidence = min(0.90, 0.75 + base_confidence)
                else:
                    confidence = min(0.85, 0.60 + base_confidence)

                # 単語数計算
                words = full_transcription.split()
                word_count = len(words)
                estimated_duration = round(processing_time * 0.8, 2)

                result = {
                    "transcription": full_transcription,
                    "processing_time": round(processing_time, 2),
                    "confidence": confidence,
                    "word_count": word_count,
                    "estimated_duration": estimated_duration
                }

                if detailed:
                    result["detailed_mode"] = True

                if high_accuracy:
                    result["mode"] = "high_accuracy"
                    result["timeout_used"] = timeout

                if recognition_errors:
                    result["warnings"] = recognition_errors

                return result

            elif recognition_errors:
                self._handle_recognition_errors(recognition_errors)

            else:
                # 認識結果が空の場合（発話なし）
                return {
                    "transcription": "",
                    "processing_time": round(time.time() - start_time, 2),
                    "confidence": 0.0,
                    "word_count": 0,
                    "estimated_duration": 0.0,
                    "no_speech_detected": True
                }

        except Exception as e:
            if 'temp_file_path' in locals():
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            raise HTTPException(status_code=500, detail=f"Azure音声処理エラー: {str(e)}")

    def _handle_recognition_errors(self, recognition_errors):
        """認識エラーの種類に応じて適切なHTTPExceptionを発生させる"""
        has_no_match = any(err["type"] == "NoMatch" for err in recognition_errors)
        has_canceled = any(err["type"] in ["Canceled", "SessionCanceled"] for err in recognition_errors)

        if has_canceled:
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
            no_match_count = sum(1 for err in recognition_errors if err["type"] == "NoMatch")

            if no_match_count == len(recognition_errors):
                raise HTTPException(
                    status_code=400,
                    detail="音声が認識できませんでした（NoMatch）"
                )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"音声の一部が認識できませんでした（{no_match_count}セグメント）"
                )

        else:
            error_summary = "; ".join([f"{err['type']}: {err.get('detail', '不明')}" for err in recognition_errors])
            raise HTTPException(
                status_code=500,
                detail=f"音声認識で予期しないエラーが発生しました: {error_summary}"
            )

    @property
    def provider_name(self) -> str:
        return "azure"

    @property
    def model_name(self) -> str:
        return f"azure/{self._model}"


class GroqProvider(ASRProvider):
    """Groq Whisper APIプロバイダー"""

    def __init__(self, model: str = "whisper-large-v3-turbo"):
        """
        Args:
            model (str): 使用するGroq Whisperモデル名
                例: "whisper-large-v3-turbo", "whisper-large-v3"
        """
        from groq import Groq  # 遅延インポート

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY環境変数が設定されていません")

        self.client = Groq(api_key=api_key)
        self._model = model

        logger.info(f"Groq Whisper API初期化完了: model={model}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def transcribe_audio(
        self,
        audio_file: BinaryIO,
        filename: str,
        detailed: bool = False,
        high_accuracy: bool = False
    ) -> Dict[str, Any]:
        """Groq Whisper APIで音声ファイルを文字起こし（リトライ付き）"""
        try:
            # 処理時間計測開始
            start_time = time.time()

            # Groq Whisper API呼び出し
            # audio_fileの位置を先頭に戻す（既に読まれている可能性があるため）
            audio_file.seek(0)

            transcription = self.client.audio.transcriptions.create(
                file=(filename, audio_file.read()),
                model=self._model,
                language="ja",  # 日本語として認識（精度向上＋ハルシネーション抑制）
                prompt="日本語の会話。無音や雑音のみの場合は空文字を返してください。",  # ハルシネーション抑制
                temperature=0.0,  # 確定的な出力（ランダム性なし）
                response_format="verbose_json",
            )

            # 処理時間計測終了
            processing_time = time.time() - start_time

            # テキスト取得
            transcription_text = transcription.text.strip() if transcription.text else ""

            # 発話なしの判定
            if not transcription_text:
                return {
                    "transcription": "",
                    "processing_time": round(processing_time, 2),
                    "confidence": 0.0,
                    "word_count": 0,
                    "estimated_duration": 0.0,
                    "no_speech_detected": True
                }

            # 単語数計算
            words = transcription_text.split()
            word_count = len(words)

            # verbose_jsonから追加情報を取得（利用可能な場合）
            duration = getattr(transcription, 'duration', None) or round(processing_time * 0.8, 2)

            # Groqは信頼度を直接提供しないため、テキスト長から推定
            text_length = len(transcription_text)
            if text_length > 50:
                confidence = 0.95
            elif text_length > 20:
                confidence = 0.90
            elif text_length > 5:
                confidence = 0.85
            else:
                confidence = 0.75

            result = {
                "transcription": transcription_text,
                "processing_time": round(processing_time, 2),
                "confidence": confidence,
                "word_count": word_count,
                "estimated_duration": duration
            }

            # verbose_jsonの詳細情報を含める（detailedモード）
            if detailed and hasattr(transcription, 'segments'):
                result["detailed_mode"] = True
                result["segments"] = transcription.segments

            return result

        except Exception as e:
            logger.error(f"❌ Groq Whisper API呼び出しエラー: {e}")
            raise HTTPException(status_code=500, detail=f"Groq音声処理エラー: {str(e)}")

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_name(self) -> str:
        return f"groq/{self._model}"


class DeepgramProvider(ASRProvider):
    """Deepgram Nova APIプロバイダー"""

    def __init__(self, model: str = "nova-3"):
        """
        Args:
            model (str): 使用するDeepgramモデル名
                例: "nova-3", "nova-2", "whisper", "enhanced"
        """
        from deepgram import DeepgramClient  # 遅延インポート

        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            raise ValueError("DEEPGRAM_API_KEY環境変数が設定されていません")

        self.client = DeepgramClient(api_key=api_key)  # キーワード引数で渡す
        self._model = model

        logger.info(f"Deepgram API初期化完了: model={model}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception)
    )
    async def transcribe_audio(
        self,
        audio_file: BinaryIO,
        filename: str,
        detailed: bool = False,
        high_accuracy: bool = False
    ) -> Dict[str, Any]:
        """Deepgram APIで音声ファイルを文字起こし（リトライ付き）"""
        try:
            # 処理時間計測開始
            start_time = time.time()

            # audio_fileの位置を先頭に戻す
            audio_file.seek(0)
            audio_data = audio_file.read()

            # Deepgram APIオプション設定
            options = {
                "model": self._model,
                "language": "ja",  # 日本語
                "punctuate": True,  # 句読点の自動挿入
                "diarize": True,    # 話者分離
                "smart_format": True,  # スマートフォーマット（日付、時刻、数字の自動整形）
                "utterances": True,  # 発話単位での区切り
            }

            # 高精度モードの場合、追加オプションを設定
            if high_accuracy:
                options.update({
                    "tier": "nova",  # 最高精度
                })

            # Deepgram API呼び出し
            response = self.client.listen.rest.v("1").transcribe_file(
                {"buffer": audio_data},
                options
            )

            # 処理時間計測終了
            processing_time = time.time() - start_time

            # レスポンスから文字起こしテキストを取得
            if not response or not response.results:
                return {
                    "transcription": "",
                    "processing_time": round(processing_time, 2),
                    "confidence": 0.0,
                    "word_count": 0,
                    "estimated_duration": 0.0,
                    "no_speech_detected": True
                }

            # チャンネル情報を取得
            channels = response.results.channels
            if not channels or len(channels) == 0:
                return {
                    "transcription": "",
                    "processing_time": round(processing_time, 2),
                    "confidence": 0.0,
                    "word_count": 0,
                    "estimated_duration": 0.0,
                    "no_speech_detected": True
                }

            # 最初のチャンネルの最初の代替案を取得
            alternatives = channels[0].alternatives
            if not alternatives or len(alternatives) == 0:
                return {
                    "transcription": "",
                    "processing_time": round(processing_time, 2),
                    "confidence": 0.0,
                    "word_count": 0,
                    "estimated_duration": 0.0,
                    "no_speech_detected": True
                }

            transcript = alternatives[0].transcript.strip() if alternatives[0].transcript else ""

            # 発話なしの判定
            if not transcript:
                return {
                    "transcription": "",
                    "processing_time": round(processing_time, 2),
                    "confidence": 0.0,
                    "word_count": 0,
                    "estimated_duration": 0.0,
                    "no_speech_detected": True
                }

            # 信頼度を取得（Deepgramは0-1の範囲で提供）
            confidence = alternatives[0].confidence if hasattr(alternatives[0], 'confidence') else 0.0

            # 単語数計算
            words = transcript.split()
            word_count = len(words)

            # 音声の長さを取得（メタデータから）
            duration = 0.0
            if hasattr(response.results, 'metadata') and hasattr(response.results.metadata, 'duration'):
                duration = response.results.metadata.duration

            result = {
                "transcription": transcript,
                "processing_time": round(processing_time, 2),
                "confidence": round(confidence, 2),
                "word_count": word_count,
                "estimated_duration": round(duration, 2) if duration > 0 else round(processing_time * 0.8, 2)
            }

            # 詳細モード：話者分離情報を含める
            if detailed and hasattr(alternatives[0], 'words'):
                result["detailed_mode"] = True

                # 話者ごとに文字起こしを整理
                speakers_info = {}
                for word in alternatives[0].words:
                    if hasattr(word, 'speaker'):
                        speaker_id = word.speaker
                        if speaker_id not in speakers_info:
                            speakers_info[speaker_id] = []
                        speakers_info[speaker_id].append({
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                            "confidence": word.confidence if hasattr(word, 'confidence') else None
                        })

                if speakers_info:
                    result["speakers"] = speakers_info
                    result["speaker_count"] = len(speakers_info)

            return result

        except Exception as e:
            logger.error(f"❌ Deepgram API呼び出しエラー: {e}")
            raise HTTPException(status_code=500, detail=f"Deepgram音声処理エラー: {str(e)}")

    @property
    def provider_name(self) -> str:
        return "deepgram"

    @property
    def model_name(self) -> str:
        return f"deepgram/{self._model}"


class ASRFactory:
    """ASRプロバイダーのファクトリークラス"""

    @staticmethod
    def create(provider: str, model: Optional[str] = None) -> ASRProvider:
        """
        指定されたプロバイダーとモデルでASRProviderインスタンスを作成

        Args:
            provider (str): プロバイダー名 ("azure", "groq", "deepgram")
            model (str, optional): モデル名。Noneの場合はデフォルトを使用

        Returns:
            ASRProvider: 指定されたプロバイダーのインスタンス

        Raises:
            ValueError: 未知のプロバイダー名が指定された場合
        """
        provider = provider.lower()

        if provider == "azure":
            default_model = "ja-JP"
            return AzureProvider(model or default_model)

        elif provider == "groq":
            default_model = "whisper-large-v3-turbo"
            return GroqProvider(model or default_model)

        elif provider == "deepgram":
            default_model = "nova-3"
            return DeepgramProvider(model or default_model)

        else:
            raise ValueError(
                f"未知のプロバイダー: {provider}\n"
                f"対応プロバイダー: azure, groq, deepgram"
            )

    @staticmethod
    def get_current() -> ASRProvider:
        """
        現在設定されているASRプロバイダーを取得

        このファイル先頭の CURRENT_PROVIDER と CURRENT_MODEL 定数を使用

        Returns:
            ASRProvider: 現在のプロバイダーインスタンス
        """
        logger.info(f"🎙️ 使用ASRプロバイダー: {CURRENT_PROVIDER}/{CURRENT_MODEL}")
        return ASRFactory.create(CURRENT_PROVIDER, CURRENT_MODEL)


# 便利な関数：現在のASRプロバイダーを取得
def get_current_asr() -> ASRProvider:
    """現在設定されているASRプロバイダーを取得（エイリアス）"""
    return ASRFactory.get_current()
