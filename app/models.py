from pydantic import BaseModel
from typing import Optional

class TranscriptionResponse(BaseModel):
    transcription: str
    confidence: Optional[float] = None
    processing_time: Optional[float] = None
    word_count: Optional[int] = None
    estimated_duration: Optional[float] = None
    mode: Optional[str] = None
    timeout_used: Optional[int] = None 