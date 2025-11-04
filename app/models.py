from pydantic import BaseModel, model_validator
from typing import Optional, List

class TranscriptionResponse(BaseModel):
    transcription: str
    confidence: Optional[float] = None
    processing_time: Optional[float] = None
    word_count: Optional[int] = None
    estimated_duration: Optional[float] = None
    mode: Optional[str] = None
    timeout_used: Optional[int] = None
    asr_provider: Optional[str] = None  # 使用したプロバイダー名
    asr_model: Optional[str] = None  # 使用したモデル名

class FetchAndTranscribeRequest(BaseModel):
    # 新しいインターフェース
    device_id: Optional[str] = None  # デバイスID
    local_date: Optional[str] = None  # 日付（YYYY-MM-DD形式）
    time_blocks: Optional[List[str]] = None  # 特定の時間ブロック（指定しない場合は全時間帯）
    
    # 既存のインターフェース（後方互換性）
    file_paths: Optional[List[str]] = None  # 直接file_pathを指定
    
    # 共通パラメータ
    model: str = "azure"  # azureモデルのみサポート
    
    @model_validator(mode='after')
    def validate_request(self):
        # どちらかのインターフェースが必要
        if self.device_id and self.local_date:
            # 新インターフェース
            return self
        elif self.file_paths:
            # 既存インターフェース
            return self
        else:
            raise ValueError("device_id + local_date または file_paths のどちらかを指定してください") 