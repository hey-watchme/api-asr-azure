#!/usr/bin/env python3
"""
Azure Speech Service テストスクリプト
SDK 1.45.0対応版
"""

import os
import sys
from dotenv import load_dotenv
import azure.cognitiveservices.speech as speechsdk
import logging

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 環境変数を読み込み
load_dotenv()

def test_azure_speech(audio_file_path: str):
    """音声ファイルを文字起こしテスト"""
    
    # Azure設定
    azure_speech_key = os.getenv('AZURE_SPEECH_KEY')
    azure_service_region = os.getenv('AZURE_SERVICE_REGION')
    
    if not azure_speech_key or not azure_service_region:
        logger.error("Azure認証情報が設定されていません")
        return None
    
    logger.info(f"テスト開始: {audio_file_path}")
    logger.info(f"Azure Region: {azure_service_region}")
    logger.info(f"SDK Version: 1.45.0")
    
    try:
        # Speech設定
        speech_config = speechsdk.SpeechConfig(
            subscription=azure_speech_key,
            region=azure_service_region
        )
        speech_config.speech_recognition_language = "ja-JP"
        
        # ファイルから直接AudioConfigを作成（最も確実な方法）
        audio_config = speechsdk.audio.AudioConfig(filename=audio_file_path)
        
        # 認識器を作成
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=speech_config,
            audio_config=audio_config
        )
        
        logger.info("単発認識を開始...")
        
        # 単発認識（短い音声用）
        result = speech_recognizer.recognize_once()
        
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            logger.info(f"✅ 認識成功: {result.text}")
            return result.text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            logger.warning("❌ 音声が認識できませんでした")
            logger.warning(f"NoMatch詳細: {result.no_match_details}")
            return None
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = speechsdk.CancellationDetails(result)
            logger.error(f"❌ 認識がキャンセルされました: {cancellation.reason}")
            if cancellation.reason == speechsdk.CancellationReason.Error:
                logger.error(f"エラー詳細: {cancellation.error_details}")
            return None
            
    except Exception as e:
        logger.error(f"エラー: {str(e)}", exc_info=True)
        return None


if __name__ == "__main__":
    # テスト用音声ファイル
    test_file = "/Users/kaya.matsumoto/Desktop/audio.wav"
    
    if not os.path.exists(test_file):
        logger.error(f"テストファイルが見つかりません: {test_file}")
        sys.exit(1)
    
    logger.info("=" * 50)
    logger.info("Azure Speech Service テスト (SDK 1.45.0)")
    logger.info("=" * 50)
    
    result = test_azure_speech(test_file)
    
    if result:
        print("\n✅ テスト成功！")
        print(f"認識結果: {result}")
    else:
        print("\n❌ テスト失敗")
        print("Azure設定を確認してください")