import logging
import json
import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelsResponse,
    ModelInfo,
    HealthResponse,
    ChatCompletionChunk
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


def generate_streaming_response(content: str, request: ChatCompletionRequest):
    """ストリーミングレスポンスを生成"""
    chunk_size = 20  # 文字単位
    response_id = f"chatcmpl-{int(time.time())}"
    created_time = int(time.time())

    # コンテンツを文字単位で分割してストリーミング
    for i in range(0, len(content), chunk_size):
        chunk_content = content[i:i + chunk_size]
        is_last_chunk = i + chunk_size >= len(content)

        chunk_data = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": request.model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": chunk_content
                } if not is_last_chunk else {},
                "finish_reason": None if not is_last_chunk else "stop"
            }]
        }

        yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
        time.sleep(0.1)  # ストリーミング感を演出

    # 最終チャンク（空のdelta）
    final_chunk = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": created_time,
        "model": request.model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop"
        }]
    }
    yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """チャット補完API"""
    try:
        # 詳細なリクエストログ
        logger.info(f"=== Chat Completion Request Details ===")
        logger.info(f"Model: {request.model}")
        logger.info(f"Messages count: {len(request.messages) if request.messages else 0}")
        logger.info(f"Messages: {request.messages}")
        logger.info(f"Temperature: {request.temperature}")
        logger.info(f"Max tokens: {request.max_tokens}")
        logger.info(f"Stream: {request.stream}")
        logger.info(f"Functions: {request.functions}")
        logger.info(f"Tools: {request.tools}")
        logger.info(f"Function call: {request.function_call}")
        logger.info(f"Tool choice: {request.tool_choice}")
        logger.info(f"Stop: {request.stop}")
        logger.info(f"Presence penalty: {request.presence_penalty}")
        logger.info(f"Frequency penalty: {request.frequency_penalty}")
        logger.info(f"Logit bias: {request.logit_bias}")
        logger.info(f"User: {request.user}")
        logger.info(f"Top p: {request.top_p}")
        logger.info(f"N: {request.n}")
        logger.info(f"========================================")

        logger.info(f"Received chat completion request for model: {request.model}")

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

        # ストリーミングが要求された場合
        if request.stream:
            # レスポンスからコンテンツを取得
            content = response.choices[0].message.content if response.choices and response.choices[0].message.content else ""

            # 模擬応答の検出と適切な処理
            if "模擬応答" in content or "mock response" in content:
                # 実際のChatGPT応答が取得できていない場合はエラーレスポンス
                raise HTTPException(
                    status_code=503,
                    detail=create_error_response(
                        "service_unavailable",
                        "ChatGPTサービスが一時的に利用できません。要素の取得に失敗しました。しばらく後に再試行してください。\n\nChatGPT service is temporarily unavailable. Failed to retrieve elements. Please try again later."
                    )
                )

            # ストリーミングレスポンスを返す
            return StreamingResponse(
                generate_streaming_response(content, request),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Content-Type": "text/plain; charset=utf-8"
                }
            )

        # 通常のレスポンス（非ストリーミング）
        # 模擬応答の検出（非ストリーミングでも確認）
        try:
            if response.choices and len(response.choices) > 0:
                choice = response.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'content') and choice.message.content:
                    content = choice.message.content
                    if "模擬応答" in content or "mock response" in content:
                        raise HTTPException(
                            status_code=503,
                            detail=create_error_response(
                                "service_unavailable",
                                "ChatGPTサービスが一時的に利用できません。要素の取得に失敗しました。しばらく後に再試行してください。\n\nChatGPT service is temporarily unavailable. Failed to retrieve elements. Please try again later."
                            )
                        )
        except (AttributeError, IndexError, TypeError):
            # モックオブジェクトや不正な構造の場合は模擬応答チェックをスキップ
            pass

        # レスポンスを辞書形式に変換してから返す（循環参照を回避）
        if isinstance(response, dict):
            # 既に辞書形式の場合はそのまま返す
            return response
        elif hasattr(response, '__dict__'):
            # Mockオブジェクトや通常のオブジェクトの場合は辞書変換
            try:
                return {
                    "id": getattr(response, 'id', 'chatcmpl-unknown'),
                    "object": getattr(response, 'object', 'chat.completion'),
                    "created": getattr(response, 'created', int(time.time())),
                    "model": getattr(response, 'model', request.model),
                    "choices": [
                        {
                            "index": getattr(choice, 'index', 0),
                            "message": {
                                "role": getattr(choice.message, 'role', 'assistant'),
                                "content": getattr(choice.message, 'content', ''),
                                **({"function_call": {
                                    "name": getattr(choice.message.function_call, 'name', ''),
                                    "arguments": getattr(choice.message.function_call, 'arguments', '')
                                }} if hasattr(choice.message, 'function_call') and choice.message.function_call else {}),
                                **({"tool_calls": [
                                    {
                                        "id": getattr(tool_call, 'id', ''),
                                        "type": getattr(tool_call, 'type', 'function'),
                                        "function": {
                                            "name": getattr(tool_call.function, 'name', ''),
                                            "arguments": getattr(tool_call.function, 'arguments', '')
                                        }
                                    } for tool_call in choice.message.tool_calls
                                ]} if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls else {})
                            },
                            "finish_reason": getattr(choice, 'finish_reason', 'stop')
                        } for choice in response.choices
                    ],
                    "usage": {
                        "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0),
                        "completion_tokens": getattr(response.usage, 'completion_tokens', 0),
                        "total_tokens": getattr(response.usage, 'total_tokens', 0)
                    }
                }
            except Exception as conv_error:
                logger.warning(f"Response conversion failed, returning original: {conv_error}")
                return response
        else:
            # その他の場合はそのまま返す
            return response

    except RuntimeError as e:
        # ログイン関連エラーの特別処理
        if "ログイン" in str(e) or "login" in str(e).lower():
            logger.error(f"Authentication error: {e}")
            raise HTTPException(
                status_code=401,
                detail=create_error_response(
                    "authentication_required",
                    "ChatGPTへのログインが必要です。ブラウザでChatGPTにログインしてからAPIを使用してください。"
                )
            )
        else:
            logger.error(f"Runtime error in chat completion: {e}")
            raise HTTPException(
                status_code=500,
                detail=create_error_response(
                    "internal_error",
                    str(e)
                )
            )
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
