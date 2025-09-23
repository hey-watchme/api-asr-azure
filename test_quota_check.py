#!/usr/bin/env python3
"""
Azure Speech Service クォータエラーチェックスクリプト
現在のAPIの状態とクォータエラーの検出を確認します
"""
import asyncio
import logging
from datetime import datetime
import pytz
from app.services import AzureSpeechService

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

async def test_transcription():
    """テスト音声ファイルで文字起こしをテスト"""
    service = AzureSpeechService()
    
    # 現在時刻を表示（JST）
    current_utc = datetime.now(pytz.UTC)
    current_jst = current_utc.astimezone(pytz.timezone('Asia/Tokyo'))
    
    print("\n" + "="*60)
    print("Azure Speech Service クォータチェック")
    print("="*60)
    print(f"現在時刻 (JST): {current_jst.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"現在時刻 (UTC): {current_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-"*60)
    
    # テストファイルを使用
    test_file = "test_audio.wav"
    
    try:
        with open(test_file, 'rb') as audio_file:
            print(f"\n📁 テストファイル: {test_file}")
            print("🎤 文字起こし処理を開始...")
            
            result = await service.transcribe_audio(
                audio_file,
                test_file,
                detailed=False,
                high_accuracy=True
            )
            
            print("\n✅ 処理成功！")
            print(f"文字起こし結果: {result.get('transcription', '(空)')}")
            print(f"処理時間: {result.get('processing_time', 0)}秒")
            print(f"信頼度: {result.get('confidence', 0)}")
            
            if result.get('warnings'):
                print("\n⚠️ 警告:")
                for warning in result['warnings']:
                    print(f"  - {warning}")
            
            print("\n✨ Azureサービスは正常に動作しています")
            
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ エラーが発生しました: {error_msg}")
        
        # クォータエラーの判定
        if "429" in error_msg or "quota" in error_msg.lower() or "limit" in error_msg.lower() or "利用上限" in error_msg:
            print("\n🚫 Azure利用上限エラーが検出されました")
            print("   → 日本時間09:00以降に再実行してください")
            print(f"   → 現在のJST: {current_jst.strftime('%H:%M')}")
            if current_jst.hour < 9:
                wait_hours = 9 - current_jst.hour
                print(f"   → 約{wait_hours}時間後に再実行をお勧めします")
        else:
            print("\n⚠️ その他のエラーです（クォータエラーではありません）")
            print(f"   詳細: {error_msg}")

if __name__ == "__main__":
    print("\n🔍 Azure Speech Service クォータチェックツール")
    print("このツールはAzure Speech Serviceの利用可能状態を確認します\n")
    
    asyncio.run(test_transcription())
    print("\n" + "="*60)
    print("テスト完了")
    print("="*60 + "\n")