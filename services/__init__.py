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

        except RuntimeError as e:
            # ログイン関連のエラーをより明確にする
            if "ログイン" in str(e) or "login" in str(e).lower():
                logger.error(f"Authentication error: {e}")
                raise RuntimeError("ChatGPTへのログインが必要です。ブラウザで手動ログインを行ってからAPIを使用してください。")
            elif "応答が見つかりません" in str(e) or "フッター" in str(e):
                logger.error(f"Response parsing error: {e}")
                raise RuntimeError("ChatGPTの応答を正しく取得できませんでした。ログイン状態を確認してください。")
            else:
                logger.error(f"Runtime error in chat completion: {e}")
                raise e
        except Exception as e:
            logger.error(f"Error creating chat completion: {e}")
            return None

    def _handle_regular_chat(self, request: ChatCompletionRequest) -> Optional[ChatCompletionResponse]:
        """通常のチャット処理"""
        # 全メッセージを処理（systemメッセージも含む）
        combined_message = self._build_combined_message(request.messages)
        if not combined_message:
            logger.error("No valid message found in request")
            return None

        logger.info(f"Combined message to send: {combined_message[:200]}...")

        # ChatGPTにメッセージを送信
        response_content = self.driver.send_message(combined_message)
        if not response_content:
            logger.error("Failed to get response from ChatGPT")
            return None

        # レスポンスの詳細ログ（デバッグ用）
        logger.info(f"Raw ChatGPT response length: {len(response_content)} characters")
        logger.info(f"Raw ChatGPT response preview: {response_content[:200]}...")
        if len(response_content) > 200:
            logger.info(f"Raw ChatGPT response ending: ...{response_content[-100:]}")

        # "I am thinking" メッセージの検出と完全除去（強化版）
        thinking_patterns = [
            "I am thinking about how to help you",
            "I'm thinking about how to help you",
            "Let me think about how to help you"
        ]

        for pattern in thinking_patterns:
            if pattern in response_content:
                logger.warning(f"Detected thinking message pattern: {pattern}")
                # パターンを完全に除去
                import re
                cleaned_response = re.sub(re.escape(pattern) + r"[.\s]*", "", response_content, flags=re.IGNORECASE)
                if cleaned_response.strip():
                    response_content = cleaned_response.strip()
                    logger.info(f"Cleaned response: {response_content}")
                else:
                    # フィルタリング後に内容がない場合は再試行
                    logger.error(f"No content remaining after filtering '{pattern}' message - possible incomplete response")
                    return None

        # レスポンスを構築
        response = self._build_response(request, response_content)
        return response

    def _handle_function_calling(self, request: ChatCompletionRequest) -> Optional[ChatCompletionResponse]:
        """Function Calling処理"""
        try:
            # Function定義をChatGPTに送信
            function_context = self._build_function_context(request)

            # 全メッセージを適切に処理
            combined_message = self._build_combined_message(request.messages)
            if not combined_message:
                logger.error("No valid message found in request")
                return None

            # Function定義付きでメッセージを構築
            enhanced_message = self._build_function_message(combined_message, function_context)

            logger.info(f"Enhanced Function Calling message: {enhanced_message[:300]}...")

            # ChatGPTに送信
            response_content = self.driver.send_message(enhanced_message)
            if not response_content:
                logger.error("Failed to get response from ChatGPT")
                # Function Calling失敗時は通常のエラーレスポンスを返す
                return self._build_error_response(request, "Failed to process function calling request")

            logger.info(f"Function Calling raw response: {response_content}")

            # Function Call検出用の関数リストを取得
            functions = request.functions or self._extract_functions_from_tools(request.tools)

            # Function Callを検出
            function_call = self._detect_function_call(response_content, functions)

            if function_call:
                # Tools APIの場合はTool Callsレスポンス、Function APIの場合はFunction Callレスポンス
                if request.tools:
                    return self._build_tool_call_response(request, function_call, response_content)
                else:
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

    def _build_function_message(self, combined_content: str, function_context: str) -> str:
        """Function定義を含むメッセージを構築"""
        return f"{function_context}\n{combined_content}"

    def _detect_function_call(self, response_content: str, functions: List) -> Optional[dict]:
        """レスポンスからFunction Callを検出（Action形式対応強化版）"""
        import json
        import re

        # パターン1: Action: {...} 形式の検出（優先）
        action_pattern = r'Action:\s*\{[^}]*"action"\s*:\s*"([^"]+)"[^}]*"action_input"\s*:\s*(\{[^}]*\}|"[^"]*")[^}]*\}'
        action_matches = re.findall(action_pattern, response_content, re.DOTALL | re.IGNORECASE)
        
        for match in action_matches:
            try:
                action_name = match[0].strip()
                action_input = match[1].strip()
                
                # action_inputがJSON文字列の場合は解析
                if action_input.startswith('{'):
                    try:
                        action_input_dict = json.loads(action_input)
                        action_arguments = json.dumps(action_input_dict, ensure_ascii=False)
                    except json.JSONDecodeError:
                        action_arguments = action_input
                elif action_input.startswith('"') and action_input.endswith('"'):
                    # 文字列の場合はそのまま使用（クォートを除去）
                    action_arguments = action_input[1:-1]
                else:
                    action_arguments = action_input
                
                # 関数名が定義済み関数に含まれているかチェック
                if any(f.name == action_name for f in functions):
                    logger.info(f"Detected Action format function call: {action_name}")
                    return {
                        "name": action_name,
                        "arguments": action_arguments
                    }
                    
            except Exception as e:
                logger.debug(f"Error parsing Action format: {e}")
                continue

        # パターン2: より柔軟なAction形式（シンプル版）
        simple_action_pattern = r'Action:\s*([a-zA-Z_][a-zA-Z0-9_]*)'
        simple_matches = re.findall(simple_action_pattern, response_content, re.IGNORECASE)
        
        for action_name in simple_matches:
            if any(f.name == action_name for f in functions):
                logger.info(f"Detected simple Action format function call: {action_name}")
                # 引数を推測して抽出（次の行やJSON部分から）
                args_pattern = r'Action:\s*' + re.escape(action_name) + r'[^\{]*(\{[^}]*\})'
                args_match = re.search(args_pattern, response_content, re.DOTALL | re.IGNORECASE)
                
                if args_match:
                    try:
                        arguments = json.loads(args_match.group(1))
                        return {
                            "name": action_name,
                            "arguments": json.dumps(arguments, ensure_ascii=False)
                        }
                    except json.JSONDecodeError:
                        pass
                
                # 引数が見つからない場合は空のオブジェクト
                return {
                    "name": action_name,
                    "arguments": "{}"
                }

        # パターン3: JSON形式のfunction_callを検索（ネストしたJSONにも対応）
        # パターン3-1: {"function_call": ...} の形式
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

        # パターン3-2: より複雑なJSON構造に対応
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
        """Function Callレスポンスを構築（Action形式対応強化版）"""
        from models import ChatMessage, ChatCompletionChoice, FunctionCall

        # Action形式の場合、適切なContentも含める
        action_detected = "Action:" in response_content
        
        # レスポンス内容の処理
        if action_detected:
            # Action形式の場合、Actionより前の部分をcontentとして保持
            import re
            action_pattern = r'(.*?)Action:\s*\{[^}]*\}'
            match = re.search(action_pattern, response_content, re.DOTALL | re.IGNORECASE)
            content_before_action = match.group(1).strip() if match else None
            
            # 空でない場合のみcontentを設定
            message_content = content_before_action if content_before_action else None
        else:
            # 通常のfunction_call形式の場合はcontentをnullに設定
            message_content = None

        # Function Callメッセージを作成
        message = ChatMessage(
            role="assistant",
            content=message_content,
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

        logger.info(f"Built Function Call response for {function_call['name']} (Action format: {action_detected})")
        return response

    def _build_tool_call_response(self, request: ChatCompletionRequest, function_call: dict, response_content: str) -> ChatCompletionResponse:
        """Tool Call レスポンスを構築（Action形式対応強化版）"""
        from models import ChatMessage, ChatCompletionChoice, ToolCall, FunctionCall
        from utils import generate_id

        # Action形式の場合、適切なContentも含める
        action_detected = "Action:" in response_content
        
        # レスポンス内容の処理
        if action_detected:
            # Action形式の場合、Actionより前の部分をcontentとして保持
            import re
            action_pattern = r'(.*?)Action:\s*\{[^}]*\}'
            match = re.search(action_pattern, response_content, re.DOTALL | re.IGNORECASE)
            content_before_action = match.group(1).strip() if match else None
            
            # 空でない場合のみcontentを設定
            message_content = content_before_action if content_before_action else None
        else:
            # 通常のtool_call形式の場合はcontentをnullに設定
            message_content = None

        # Tool Call IDを生成
        tool_call_id = generate_id("call")

        # Tool Call オブジェクトを作成
        tool_call = ToolCall(
            id=tool_call_id,
            type="function",
            function=FunctionCall(
                name=function_call["name"],
                arguments=function_call["arguments"]
            )
        )

        # Tool Call メッセージを作成
        message = ChatMessage(
            role="assistant",
            content=message_content,
            tool_calls=[tool_call]
        )

        choice = ChatCompletionChoice(
            index=0,
            message=message,
            finish_reason="tool_calls"
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

        logger.info(f"Built Tool Call response for {function_call['name']} (Action format: {action_detected})")
        return response

    def _get_latest_user_message(self, messages: List[ChatMessage]) -> Optional[ChatMessage]:
        """最新のユーザーメッセージを取得"""
        for message in reversed(messages):
            if message.role == "user":
                return message
        return None

    def _build_combined_message(self, messages: List[ChatMessage]) -> str:
        """システムメッセージとユーザーメッセージを組み合わせた文字列を構築（分離防止強化版）"""
        system_messages = []
        user_messages = []
        assistant_messages = []

        for message in messages:
            if message.role == "system" and message.content:
                system_messages.append(message.content)
            elif message.role == "user" and message.content:
                user_messages.append(message.content)
            elif message.role == "assistant" and message.content:
                assistant_messages.append(message.content)

        # メッセージを組み合わせ（システムメッセージ分離防止強化）
        combined_parts = []

        # システムプロンプトがある場合は適切に統合
        if system_messages and user_messages:
            # システムメッセージとユーザーメッセージを密接に統合
            system_content = " ".join(system_messages)
            latest_user_message = user_messages[-1]
            
            # 分離しにくい形式で統合（改行ではなくスペースで区切り、文脈を連続させる）
            integrated_message = f"{system_content} Please respond to this user request: {latest_user_message}"
            combined_parts.append(integrated_message)
            
            logger.info(f"Built integrated message to prevent system message separation: {len(system_content)} sys chars + {len(latest_user_message)} user chars")
            
        elif system_messages:
            # システムメッセージのみの場合
            combined_parts.append(" ".join(system_messages))
        elif user_messages:
            # ユーザーメッセージのみの場合
            latest_user_message = user_messages[-1]
            combined_parts.append(f"User: {latest_user_message}")

        if not combined_parts:
            return ""

        # 単一の統合されたメッセージとして返す
        combined_message = " ".join(combined_parts)
        
        # 分離リスクの警告
        if len(combined_message) > 4000:
            logger.warning(f"Combined message is {len(combined_message)} chars - may trigger chunking and potential system message separation")
        
        return combined_message

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
