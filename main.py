import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from app.routes import router


# 環境変数読み込み
load_dotenv()

# FastAPIアプリケーション作成
app = FastAPI(
    title="Azure Speech Services API",
    description="Azure Speech Servicesを使用した音声文字起こしAPI",
    version="1.0.0"
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
        "service": "Azure Speech Services API",
        "azure_key_configured": os.getenv("AZURE_SPEECH_KEY", "your-key-here") != "your-key-here",
        "azure_region_configured": os.getenv("AZURE_SERVICE_REGION", "your-region-here") != "your-region-here"
    }

if __name__ == "__main__":
    import uvicorn
    # 本番環境はポート8013、ローカルはPORT環境変数または8008
    port = int(os.getenv("PORT", 8013))
    uvicorn.run(app, host="0.0.0.0", port=port) 