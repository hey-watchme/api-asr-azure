from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from app.models import TranscriptionResponse, FetchAndTranscribeRequest
from app.services import azure_speech_service
import time
import logging

# ロギング設定
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/analyze/azure", response_model=TranscriptionResponse)
async def analyze_audio(
    file: UploadFile = File(...),
    detailed: bool = Query(False, description="詳細な結果（信頼度、統計情報）を取得"),
    high_accuracy: bool = Query(False, description="高精度モード（時間がかかりますが精度が向上）")
):
    """Azure Speech Servicesを使用して音声ファイルを文字起こしする"""
    
    # ファイル形式チェック
    allowed_extensions = ['.wav', '.mp3', '.m4a']
    file_extension = None
    
    if file.filename:
        file_extension = '.' + file.filename.split('.')[-1].lower()
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"サポートされていないファイル形式です。対応形式: {', '.join(allowed_extensions)}"
            )
    else:
        raise HTTPException(status_code=400, detail="ファイル名が指定されていません")
    
    # ファイルサイズチェック（25MB制限）
    if file.size and file.size > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="ファイルサイズが25MBを超えています")
    
    try:
        # 音声文字起こし実行
        result = await azure_speech_service.transcribe_audio(
            file.file, 
            file.filename, 
            detailed=detailed, 
            high_accuracy=high_accuracy
        )
        
        return TranscriptionResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"予期しないエラーが発生しました: {str(e)}")

@router.post("/fetch-and-transcribe")
async def fetch_and_transcribe(request: FetchAndTranscribeRequest):
    """WatchMeシステムのメイン処理エンドポイント（Azure Speech Service版）"""
    start_time = time.time()
    
    # サポートされているモデルの確認
    if request.model not in ["azure"]:
        raise HTTPException(
            status_code=400,
            detail=f"サポートされていないモデル: {request.model}. 対応モデル: azure"
        )
    
    # Azure Speech Service処理を実行
    try:
        result = await azure_speech_service.fetch_and_transcribe_files(request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"fetch_and_transcribe エラー: {str(e)}")
        raise HTTPException(status_code=500, detail=f"予期しないエラーが発生しました: {str(e)}") 