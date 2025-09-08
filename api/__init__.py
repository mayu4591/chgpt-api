import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelsResponse,
    ModelInfo,
    HealthResponse
)
from services import ChatGPTService
from utils import get_current_timestamp, create_error_response

logger = logging.getLogger(__name__)

# ルーターの作成
router = APIRouter()

# サービスインスタンス（遅延初期化）
chatgpt_service: Optional[ChatGPTService] = None


def get_chatgpt_service() -> ChatGPTService:
    """ChatGPTサービスのインスタンスを取得（遅延初期化）"""
    global chatgpt_service
    if chatgpt_service is None:
        logger.info("Initializing ChatGPT Service...")
        logger.info("🚀 Starting Chrome browser for ChatGPT automation...")
        chatgpt_service = ChatGPTService()
        logger.info("✅ Chrome browser successfully started and ready!")
        logger.info("💡 Chrome is running in the background with remote debugging enabled")
    return chatgpt_service


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(request: ChatCompletionRequest):
    """チャット補完API"""
    try:
        logger.info(f"Received chat completion request for model: {request.model}")

        # ストリーミングは現在未対応
        if request.stream:
            raise HTTPException(
                status_code=400,
                detail=create_error_response(
                    "unsupported_parameter",
                    "Streaming is not currently supported"
                )
            )

        # チャット補完を実行
        response = get_chatgpt_service().create_chat_completion(request)

        if not response:
            raise HTTPException(
                status_code=500,
                detail=create_error_response(
                    "internal_error",
                    "Failed to generate chat completion"
                )
            )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat completion: {e}")
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                "internal_error",
                "An unexpected error occurred"
            )
        )


@router.get("/v1/models", response_model=ModelsResponse)
async def list_models():
    """利用可能なモデル一覧API"""
    try:
        # ChatGPTのWebインターフェースで利用可能なモデルを返す
        models = [
            ModelInfo(
                id="gpt-3.5-turbo",
                created=1677610602,
                owned_by="openai"
            ),
            ModelInfo(
                id="gpt-4",
                created=1687882411,
                owned_by="openai"
            ),
            ModelInfo(
                id="gpt-4-turbo-preview",
                created=1706037612,
                owned_by="openai"
            )
        ]

        return ModelsResponse(data=models)

    except Exception as e:
        logger.error(f"Error listing models: {e}")
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                "internal_error",
                "Failed to retrieve models"
            )
        )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """ヘルスチェックAPI"""
    try:
        is_healthy = get_chatgpt_service().health_check()
        status = "healthy" if is_healthy else "unhealthy"

        return HealthResponse(
            status=status,
            timestamp=get_current_timestamp()
        )

    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return HealthResponse(
            status="unhealthy",
            timestamp=get_current_timestamp()
        )


@router.get("/v1/chrome/status")
async def get_chrome_status():
    """Chrome起動状態確認API"""
    try:
        global chatgpt_service
        if chatgpt_service is None:
            return {
                "chrome_status": "not_started",
                "message": "Chrome has not been started yet. Make your first API call to initialize.",
                "timestamp": get_current_timestamp()
            }

        is_active = chatgpt_service.health_check()
        return {
            "chrome_status": "active" if is_active else "inactive",
            "message": "Chrome is running and ready for requests" if is_active else "Chrome is not responding",
            "timestamp": get_current_timestamp()
        }

    except Exception as e:
        logger.error(f"Error checking Chrome status: {e}")
        return {
            "chrome_status": "error",
            "message": f"Error checking Chrome status: {str(e)}",
            "timestamp": get_current_timestamp()
        }
