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
from api import router as api_router, get_chatgpt_service


# ロギング設定とインポート不足の修正
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    logger.info("Application lifespan starting...")

    # 設定は既にインポート済み

    try:
        if settings.auto_start_browser:
            logger.info("Auto-starting browser...")
            # get_chatgpt_service()は同期関数なのでawaitは不要
            chatgpt_service = get_chatgpt_service()

            # ブラウザの初期化は同期で行う
            chatgpt_service._initialize_session()

            # 起動タイムアウトを考慮した待機処理
            import asyncio
            await asyncio.sleep(min(settings.startup_timeout, 5))  # 最大5秒待機

            if chatgpt_service.health_check():
                logger.info("Browser auto-start completed successfully")
            else:
                logger.warning("Browser auto-start completed but health check failed")

        yield  # アプリケーション実行中

    except Exception as e:
        logger.error(f"Error during lifespan: {e}")
        yield  # エラーが発生してもアプリケーションは継続
    finally:
        logger.info("Application lifespan ending...")
        # クリーンアップ処理
        try:
            chatgpt_service = get_chatgpt_service()
            chatgpt_service.cleanup()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


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
