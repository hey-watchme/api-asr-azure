import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.routes import router
from app.asr_providers import CURRENT_PROVIDER, CURRENT_MODEL


# 環境変数読み込み
load_dotenv()

# FastAPIアプリケーション作成
app = FastAPI(
    title="WatchMe Transcriber API",
    description="マルチプロバイダー対応の音声文字起こしAPI (Azure, Groq)",
    version="2.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(router)

# 静的ファイル配信
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    """トップページにリダイレクト"""
    return RedirectResponse(url="/static/index.html")

@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {
        "status": "healthy",
        "service": "WatchMe Transcriber API",
        "asr_provider": CURRENT_PROVIDER,
        "asr_model": CURRENT_MODEL,
        "version": "2.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    # ローカル・本番環境ともにポート8013で統一
    port = 8013
    uvicorn.run(app, host="0.0.0.0", port=port) 