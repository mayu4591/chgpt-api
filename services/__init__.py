import logging
from typing import Optional, List
from models import ChatMessage, ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChoice, ChatCompletionUsage
from drivers import ChatGPTDriver
from utils import generate_id, get_current_timestamp

logger = logging.getLogger(__name__)


class ChatGPTService:
    """ChatGPT制御サービスクラス"""

    def __init__(self):
        self.driver = ChatGPTDriver()
        # セッション初期化を遅延させる（APIリクエスト時に初期化）
        # self._initialize_session()  # この行をコメントアウト

    def _initialize_session(self) -> None:
        """セッションを初期化"""
        try:
            if not self.driver.start_session():
                logger.error("Failed to initialize ChatGPT session")
        except Exception as e:
            logger.error(f"Error initializing session: {e}")

    def create_chat_completion(self, request: ChatCompletionRequest) -> Optional[ChatCompletionResponse]:
        """チャット補完を作成（Function Calling対応）"""
        try:
            # セッションが無効な場合は再初期化
            if not self.driver.is_session_active():
                logger.info("Session inactive, reinitializing...")
                self._initialize_session()
                if not self.driver.is_session_active():
                    logger.error("Failed to reinitialize session")
                    return None

            # Function Calling対応
            if request.functions or request.tools:
                return self._handle_function_calling(request)

            # 通常のチャット処理
            return self._handle_regular_chat(request)

        except Exception as e:
            logger.error(f"Error creating chat completion: {e}")
            return None

    def _handle_regular_chat(self, request: ChatCompletionRequest) -> Optional[ChatCompletionResponse]:
        """通常のチャット処理"""
        # メッセージを構築（最後のユーザーメッセージのみを送信）
        user_message = self._get_latest_user_message(request.messages)
        if not user_message:
            logger.error("No user message found in request")
            return None

        # ChatGPTにメッセージを送信
        response_content = self.driver.send_message(user_message.content)
        if not response_content:
            logger.error("Failed to get response from ChatGPT")
            return None

        # レスポンスを構築
        response = self._build_response(request, response_content)
        return response

    def _handle_function_calling(self, request: ChatCompletionRequest) -> Optional[ChatCompletionResponse]:
        """Function Calling処理"""
        try:
            # Function定義をChatGPTに送信
            function_context = self._build_function_context(request)

            # メッセージにFunction定義を含めて送信
            user_message = self._get_latest_user_message(request.messages)
            if not user_message:
                logger.error("No user message found in request")
                return None

            # Function定義付きでメッセージを構築
            enhanced_message = self._build_function_message(user_message.content or '', function_context)

            # ChatGPTに送信
            response_content = self.driver.send_message(enhanced_message)
            if not response_content:
                logger.error("Failed to get response from ChatGPT")
                # Function Calling失敗時は通常のエラーレスポンスを返す
                return self._build_error_response(request, "Failed to process function calling request")

            # Function Callを検出
            function_call = self._detect_function_call(response_content, request.functions or self._extract_functions_from_tools(request.tools))

            if function_call:
                # Function Callレスポンスを構築
                return self._build_function_call_response(request, function_call, response_content)
            else:
                # Function Callが検出されない場合、通常のレスポンスとして返す
                logger.info("No function call detected, returning regular response")
                return self._build_response(request, response_content)

        except Exception as e:
            logger.error(f"Error handling function calling: {e}")
            return self._build_error_response(request, f"Function calling error: {str(e)}")

    def _build_error_response(self, request: ChatCompletionRequest, error_message: str) -> ChatCompletionResponse:
        """エラーレスポンスを構築"""
        from models import ChatMessage, ChatCompletionChoice

        # エラーメッセージを作成
        message = ChatMessage(
            role="assistant",
            content=f"I apologize, but I encountered an error while processing your request: {error_message}"
        )

        choice = ChatCompletionChoice(
            index=0,
            message=message,
            finish_reason="stop"
        )

        # 使用量を推定
        usage = ChatCompletionUsage(
            prompt_tokens=len(' '.join(msg.content or '' for msg in request.messages)) // 4,
            completion_tokens=len(error_message) // 4,
            total_tokens=0
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        response = ChatCompletionResponse(
            id=generate_id(),
            created=get_current_timestamp(),
            model=request.model,
            choices=[choice],
            usage=usage
        )

        return response

    def _build_function_context(self, request: ChatCompletionRequest) -> str:
        """Function定義のコンテキストを構築"""
        functions = request.functions or self._extract_functions_from_tools(request.tools)
        if not functions:
            return ""

        # より自然なプロンプトエンジニアリングを使用
        context = "I have access to the following functions that I can call to help answer your question:\n\n"

        for func in functions:
            context += f"Function: {func.name}\n"
            context += f"Description: {func.description}\n"

            # パラメータをわかりやすく説明
            if hasattr(func, 'parameters') and func.parameters:
                params = func.parameters.get('properties', {})
                required = func.parameters.get('required', [])

                context += "Parameters:\n"
                for param_name, param_info in params.items():
                    param_type = param_info.get('type', 'string')
                    param_desc = param_info.get('description', '')
                    is_required = param_name in required
                    req_text = " (required)" if is_required else " (optional)"
                    context += f"  - {param_name} ({param_type}){req_text}: {param_desc}\n"

            context += "\n"

        context += "When you need to call a function, please respond with a JSON object in this exact format:\n"
        context += '{"function_call": {"name": "function_name", "arguments": "{\\"parameter\\": \\"value\\"}"}}\n\n'
        context += "Make sure to use proper JSON formatting with escaped quotes in the arguments.\n\n"

        return context

    def _extract_functions_from_tools(self, tools: Optional[List]) -> List:
        """Tools形式からFunction定義を抽出"""
        if not tools:
            return []
        return [tool.function for tool in tools if tool.type == "function"]

    def _build_function_message(self, user_content: str, function_context: str) -> str:
        """Function定義を含むメッセージを構築"""
        return f"{function_context}\nUser request: {user_content}"

    def _detect_function_call(self, response_content: str, functions: List) -> Optional[dict]:
        """レスポンスからFunction Callを検出"""
        import json
        import re

        # JSON形式のfunction_callを検索（ネストしたJSONにも対応）
        # パターン1: {"function_call": ...} の形式
        pattern1 = r'\{[^}]*"function_call"[^}]*"name"[^}]*"arguments"[^}]*\}'
        matches = re.findall(pattern1, response_content, re.DOTALL)

        for match in matches:
            try:
                parsed = json.loads(match)
                if "function_call" in parsed:
                    func_call = parsed["function_call"]
                    # 関数名が定義済み関数に含まれているかチェック
                    if any(f.name == func_call.get("name") for f in functions):
                        return func_call
            except json.JSONDecodeError:
                continue

        # パターン2: より複雑なJSON構造に対応
        try:
            # 全体をJSONとして解析を試行
            lines = response_content.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{') and 'function_call' in line:
                    try:
                        parsed = json.loads(line)
                        if "function_call" in parsed:
                            func_call = parsed["function_call"]
                            if any(f.name == func_call.get("name") for f in functions):
                                return func_call
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        return None

    def _build_function_call_response(self, request: ChatCompletionRequest, function_call: dict, response_content: str) -> ChatCompletionResponse:
        """Function Callレスポンスを構築"""
        from models import ChatMessage, ChatCompletionChoice, FunctionCall

        # Function Callメッセージを作成
        message = ChatMessage(
            role="assistant",
            content=None,
            function_call=FunctionCall(
                name=function_call["name"],
                arguments=function_call["arguments"]
            )
        )

        choice = ChatCompletionChoice(
            index=0,
            message=message,
            finish_reason="function_call"
        )

        # 使用量を推定
        # 基本的な使用量推定
        usage = ChatCompletionUsage(
            prompt_tokens=len(' '.join(msg.content or '' for msg in request.messages)) // 4,
            completion_tokens=len(response_content) // 4,
            total_tokens=0
        )
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        response = ChatCompletionResponse(
            id=generate_id(),
            created=get_current_timestamp(),
            model=request.model,
            choices=[choice],
            usage=usage
        )

        return response

    def _get_latest_user_message(self, messages: List[ChatMessage]) -> Optional[ChatMessage]:
        """最新のユーザーメッセージを取得"""
        for message in reversed(messages):
            if message.role == "user":
                return message
        return None

    def _build_response(self, request: ChatCompletionRequest, content: str) -> ChatCompletionResponse:
        """レスポンスオブジェクトを構築"""
        # 使用量を推定（実際の値は取得困難なため概算）
        prompt_tokens = self._estimate_tokens(request.messages)
        completion_tokens = self._estimate_tokens([ChatMessage(role="assistant", content=content)])

        choice = ChatCompletionChoice(
            index=0,
            message=ChatMessage(role="assistant", content=content),
            finish_reason="stop"
        )

        usage = ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens
        )

        return ChatCompletionResponse(
            id=generate_id(),
            created=get_current_timestamp(),
            model=request.model,
            choices=[choice],
            usage=usage
        )

    def _estimate_tokens(self, messages: List[ChatMessage]) -> int:
        """トークン数を推定（簡易版）"""
        total_chars = sum(len(msg.content or '') for msg in messages)
        # 英語の場合、約4文字で1トークンと仮定
        return max(1, total_chars // 4)

    def health_check(self) -> bool:
        """ヘルスチェック"""
        return self.driver.is_session_active()

    def cleanup(self) -> None:
        """リソースのクリーンアップ"""
        if self.driver:
            self.driver.close_session()
