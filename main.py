#!/usr/bin/env python3
"""
ChatGPT Selenium API Server
メインエントリポイント
"""

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import settings
from utils import setup_logging
from api import router as api_router, chatgpt_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフサイクル管理"""
    # スタートアップ
    setup_logging(settings.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Starting ChatGPT Selenium API Server")

    yield

    # シャットダウン
    logger.info("Shutting down ChatGPT Selenium API Server")
    from api import chatgpt_service
    if chatgpt_service is not None:
        chatgpt_service.cleanup()


# FastAPIアプリケーション作成
app = FastAPI(
    title="ChatGPT Selenium API",
    description="SeleniumでChatGPTを制御するOpenAI互換API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では適切なオリジンを設定
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# APIルーターを登録
app.include_router(api_router)


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "ChatGPT Selenium API Server",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "chat_completions": "/v1/chat/completions",
            "models": "/v1/models",
            "health": "/v1/health",
            "chrome_status": "/v1/chrome/status"
        },
        "note": "Chrome will be automatically started on first API request"
    }


def main():
    """メイン関数"""
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    main()
