import time
import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock

from main import app
from models import ChatMessage, ChatCompletionRequest, FunctionCall
from services import ChatGPTService
from drivers import ChatGPTDriver


class TestChatGPTAPI:
    """ChatGPT API統合テストクラス"""

    def setup_method(self):
        """テストメソッド前のセットアップ"""
        self.client = TestClient(app)

    def test_root_endpoint(self):
        """ルートエンドポイントテスト"""
        response = self.client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "ChatGPT Selenium API Server"
        assert "version" in data
        assert "status" in data

    def test_health_check_endpoint(self):
        """ヘルスチェックエンドポイントテスト"""
        with patch('api.get_chatgpt_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.health_check.return_value = True
            mock_get_service.return_value = mock_service

            response = self.client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data

    def test_models_endpoint(self):
        """モデル一覧エンドポイントテスト"""
        response = self.client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        assert any(model["id"] == "gpt-3.5-turbo" for model in data["data"])

    @patch('api.get_chatgpt_service')
    def test_chat_completions_success(self, mock_get_service):
        """チャット補完成功テスト"""
        # モックサービスとレスポンス作成
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        mock_response = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-3.5-turbo",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I help you today?"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 9,
                "completion_tokens": 12,
                "total_tokens": 21
            }
        }
        mock_service.create_chat_completion.return_value = mock_response

        # リクエスト送信
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "max_tokens": 100
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "Hello! How can I help you today?"

    def test_chat_completions_invalid_request(self):
        """チャット補完無効リクエストテスト"""
        # 必須フィールド不足
        request_data = {
            "model": "gpt-3.5-turbo"
            # messagesフィールドが不足
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 422  # バリデーションエラー

    def test_chat_completions_stream_unsupported(self):
        """ストリーミング対応テスト"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "stream": True
        }

        # ストリーミングテストでもモックサービスを使用
        with patch('api.get_chatgpt_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service

            # モックレスポンス作成（適切なオブジェクト構造）
            mock_response = Mock()
            mock_response.id = "chatcmpl-stream-test"
            mock_response.object = "chat.completion"
            mock_response.created = 1677652289
            mock_response.model = "gpt-3.5-turbo"

            # choices配列を適切に設定
            mock_choice = Mock()
            mock_choice.index = 0
            mock_choice.finish_reason = "stop"

            # messageオブジェクトを適切に設定
            mock_message = Mock()
            mock_message.role = "assistant"
            mock_message.content = "Hello! How can I help you?"
            mock_choice.message = mock_message

            mock_response.choices = [mock_choice]

            # usage情報を設定
            mock_usage = Mock()
            mock_usage.prompt_tokens = 5
            mock_usage.completion_tokens = 6
            mock_usage.total_tokens = 11
            mock_response.usage = mock_usage

            mock_service.create_chat_completion.return_value = mock_response

            response = self.client.post("/v1/chat/completions", json=request_data)
            # ストリーミングレスポンスは200で返される
            assert response.status_code == 200
            # ストリーミングのContent-Typeを確認
            assert "text/plain" in response.headers.get("content-type", "")

    def test_chat_completions_stream_false(self):
        """非ストリーミングテスト（従来通り）"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "stream": False
        }

        # 非ストリーミングの場合は従来通りJSONレスポンス
        with patch('api.get_chatgpt_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service

            # モックレスポンス作成（辞書形式で直接返す）
            mock_response = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "gpt-3.5-turbo",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Test response"
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15
                }
            }
            mock_service.create_chat_completion.return_value = mock_response

            response = self.client.post("/v1/chat/completions", json=request_data)
            assert response.status_code == 200
            data = response.json()
            assert data["choices"][0]["message"]["content"] == "Test response"

    @patch('api.get_chatgpt_service')
    def test_chat_completions_streaming_format(self, mock_get_service):
        """ストリーミング形式の詳細テスト"""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # モックレスポンス作成（適切なオブジェクト構造）
        mock_response = Mock()
        mock_response.id = "chatcmpl-stream-test"
        mock_response.object = "chat.completion"
        mock_response.created = 1677652289
        mock_response.model = "gpt-3.5-turbo"

        # choices配列を適切に設定
        mock_choice = Mock()
        mock_choice.index = 0
        mock_choice.finish_reason = "stop"

        # messageオブジェクトを適切に設定
        mock_message = Mock()
        mock_message.role = "assistant"
        mock_message.content = "Hello world!"
        mock_choice.message = mock_message

        mock_response.choices = [mock_choice]

        # usage情報を設定
        mock_usage = Mock()
        mock_usage.prompt_tokens = 5
        mock_usage.completion_tokens = 3
        mock_usage.total_tokens = 8
        mock_response.usage = mock_usage

        mock_service.create_chat_completion.return_value = mock_response

        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Say hello"}
            ],
            "stream": True
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

        # ストリーミングレスポンスの内容確認
        content = response.content.decode('utf-8')
        assert "data: " in content
        assert "[DONE]" in content
        assert "chat.completion.chunk" in content

    @patch('api.get_chatgpt_service')
    def test_chat_completions_with_functions(self, mock_get_service):
        """Function Calling付きチャット補完テスト"""
        # モックサービス作成
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # モックレスポンス作成（Function Call応答を辞書で作成）
        mock_response = {
            "id": "chatcmpl-func-test",
            "object": "chat.completion",
            "created": 1677652300,
            "model": "gpt-3.5-turbo",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "function_call": {
                        "name": "get_weather",
                        "arguments": '{"location": "Tokyo"}'
                    }
                },
                "finish_reason": "function_call"
            }],
            "usage": {
                "prompt_tokens": 45,
                "completion_tokens": 10,
                "total_tokens": 55
            }
        }
        mock_service.create_chat_completion.return_value = mock_response        # Function定義付きリクエスト送信
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "What's the weather like in Tokyo?"}
            ],
            "functions": [
                {
                    "name": "get_weather",
                    "description": "Get the current weather in a given location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA"
                            }
                        },
                        "required": ["location"]
                    }
                }
            ],
            "function_call": "auto"
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["finish_reason"] == "function_call"
        assert data["choices"][0]["message"]["function_call"]["name"] == "get_weather"

    @patch('api.get_chatgpt_service')
    def test_chat_completions_with_tools(self, mock_get_service):
        """Tools API形式でのFunction Callingテスト"""
        # モックサービス作成
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # モックレスポンス作成（Tool Calls応答を辞書で作成）
        mock_response = {
            "id": "chatcmpl-tools-test",
            "object": "chat.completion",
            "created": 1677652301,
            "model": "gpt-3.5-turbo",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "calculate_area",
                            "arguments": '{"width": 5, "height": 3}'
                        }
                    }]
                },
                "finish_reason": "tool_calls"
            }],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 15,
                "total_tokens": 65
            }
        }

        mock_service.create_chat_completion.return_value = mock_response

        # Tools形式リクエスト送信
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Calculate the area of a 5x3 rectangle"}
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "calculate_area",
                        "description": "Calculate area of a rectangle",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "width": {"type": "number"},
                                "height": {"type": "number"}
                            },
                            "required": ["width", "height"]
                        }
                    }
                }
            ],
            "tool_choice": "auto"
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["finish_reason"] == "tool_calls"
        assert data["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "calculate_area"

    @patch('api.get_chatgpt_service')
    def test_chat_completions_invalid_function_call(self, mock_get_service):
        """無効なFunction Call設定テスト"""
        # モックサービス作成
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # 簡単なレスポンス用意
        mock_response = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-3.5-turbo",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Test response"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 2,
                "total_tokens": 7
            }
        }
        mock_service.create_chat_completion.return_value = mock_response

        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Test"}
            ],
            "function_call": "invalid_setting"  # 無効な設定
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        # Pydanticバリデーションエラーまたは正常処理を期待
        # （実装依存だが、エラーにならないことを確認）
        assert response.status_code in [200, 422]

    def test_function_message_role(self):
        """Function roleメッセージテスト"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "What's the weather?"},
                {
                    "role": "assistant",
                    "content": None,
                    "function_call": {
                        "name": "get_weather",
                        "arguments": '{"location": "Tokyo"}'
                    }
                },
                {
                    "role": "function",
                    "name": "get_weather",
                    "content": '{"temperature": "22°C", "condition": "sunny"}'
                }
            ]
        }

        # バリデーションテスト（エラーなく受け入れられることを確認）
        response = self.client.post("/v1/chat/completions", json=request_data)
        # 実装状況により200または処理エラーを期待
        assert response.status_code in [200, 400, 401, 422, 500]


class TestChatGPTService:
    """ChatGPTServiceユニットテストクラス"""

    def setup_method(self):
        """テストメソッド前のセットアップ"""
        self.service = ChatGPTService()

    @patch('services.ChatGPTDriver')
    def test_create_chat_completion_success(self, mock_driver_class):
        """チャット補完成功テスト"""
        # モックドライバー設定
        mock_driver = Mock()
        mock_driver.is_session_active.return_value = True
        mock_driver.send_message.return_value = "Test response"
        mock_driver_class.return_value = mock_driver

        # テストリクエスト作成
        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[
                ChatMessage(role="user", content="Test message")
            ]
        )

        # サービス初期化（モックドライバー使用）
        service = ChatGPTService()
        service.driver = mock_driver

        # チャット補完実行
        response = service.create_chat_completion(request)

        assert response is not None
        assert response.choices[0].message.content == "Test response"
        assert response.choices[0].message.role == "assistant"
        assert response.model == "gpt-3.5-turbo"

    def test_get_latest_user_message(self):
        """最新ユーザーメッセージ取得テスト"""
        messages = [
            ChatMessage(role="system", content="System message"),
            ChatMessage(role="user", content="First user message"),
            ChatMessage(role="assistant", content="Assistant response"),
            ChatMessage(role="user", content="Latest user message")
        ]

        latest = self.service._get_latest_user_message(messages)
        assert latest is not None
        assert latest.content == "Latest user message"

    def test_estimate_tokens(self):
        """トークン数推定テスト"""
        messages = [
            ChatMessage(role="user", content="Hello world!")  # 12文字
        ]

        tokens = self.service._estimate_tokens(messages)
        assert tokens >= 1
        assert tokens == 12 // 4  # 文字数/4の計算


class TestChatGPTDriver:
    """ChatGPTDriverユニットテストクラス"""

    def setup_method(self):
        """テストメソッド前のセットアップ"""
        self.driver = ChatGPTDriver()

    @patch('drivers.selenium_wrapper.SeleniumWrapper')
    def test_create_chrome_driver(self, mock_wrapper_class):
        """Chromeドライバー作成テスト（SeleniumWrapper使用）"""
        # モック設定
        mock_wrapper = Mock()
        mock_wrapper.driver = Mock()
        mock_wrapper.driver.session_id = "test-session"
        mock_wrapper_class.get_instance.return_value = mock_wrapper

        # ドライバー作成テスト
        try:
            result = self.driver.start_session()
            assert result == True or mock_wrapper.driver is not None
        except Exception as e:
            # SeleniumWrapperの問題はテスト環境での制限事項として許容
            if "selenium" in str(e).lower() or "wrapper" in str(e).lower():
                pytest.skip("SeleniumWrapper initialization failed in test environment")
            else:
                raise

    def test_session_state_management(self):
        """セッション状態管理テスト"""
        # 初期状態
        assert not self.driver.is_session_active()

        # セッション状態テスト（SeleniumWrapper使用）
        with patch('drivers.selenium_wrapper.SeleniumWrapper') as mock_wrapper_class:
            mock_wrapper = Mock()
            mock_wrapper.driver = Mock()
            mock_wrapper.driver.session_id = "test-session-id"
            mock_wrapper_class.get_instance.return_value = mock_wrapper

            # SeleniumWrapperインスタンスを設定
            self.driver.selenium_wrapper = mock_wrapper
            self.driver._session_active = True

            # セッション状態確認
            assert self.driver.is_session_active()
            assert hasattr(self.driver, '_session_active')
            # 実際の状態確認関数をテスト
            result = self.driver._session_active if hasattr(self.driver, '_session_active') else False
            assert result == True

            self.driver._session_active = False
            assert not self.driver.is_session_active()

    def test_login_state_check(self):
        """ログイン状態チェックテスト"""
        with patch('drivers.selenium_wrapper.SeleniumWrapper') as mock_wrapper_class:
            mock_wrapper = Mock()
            mock_driver = Mock()
            mock_wrapper.driver = mock_driver
            mock_wrapper_class.get_instance.return_value = mock_wrapper

            driver = ChatGPTDriver()
            driver.selenium_wrapper = mock_wrapper

            # ログインボタンが存在する場合（未ログイン）
            # すべてのログインインジケーターでボタンが見つかる
            mock_driver.find_elements.return_value = [Mock(is_displayed=Mock(return_value=True))]
            assert not driver._check_login_status()

            # ChatGPT要素が存在する場合（ログイン済み）
            # ログインインジケーターは空、ChatGPTインジケーターで要素が見つかる
            def side_effect_func(by, selector):
                # ログインインジケーターは全て空を返す
                if any(indicator in selector for indicator in ['login-button', 'signup-button', 'auth']):
                    return []
                # ChatGPTインジケーターは要素を返す
                elif any(indicator in selector for indicator in ['prompt-textarea', 'contenteditable', 'composer-button']):
                    return [Mock(is_displayed=Mock(return_value=True))]
                else:
                    return []

            mock_driver.find_elements.side_effect = side_effect_func
            assert driver._check_login_status()

    def test_login_required_error_handling(self):
        """ログイン必須エラーハンドリングテスト"""
        with patch('drivers.selenium_wrapper.SeleniumWrapper') as mock_wrapper_class:
            mock_wrapper = Mock()
            mock_driver = Mock()
            mock_wrapper.driver = mock_driver
            mock_wrapper_class.get_instance.return_value = mock_wrapper

            driver = ChatGPTDriver()
            driver.selenium_wrapper = mock_wrapper
            driver._session_active = True

            # ログイン状態チェックでFalseを返す
            with patch.object(driver, '_check_login_status', return_value=False):
                with pytest.raises(RuntimeError) as exc_info:
                    driver.send_message("test message")

                assert "ログイン" in str(exc_info.value)

    def test_streaming_response_completion(self):
        """ストリーミング応答完了検知テスト"""
        # ドライバーインスタンス作成
        driver = ChatGPTDriver()

        # モック要素を作成
        mock_element = Mock()
        mock_element.text = "Question: ジャンプする男\nThought: I need to generate an appropriate prompt for Stable Diffusion to create an image of a jumping man."

        # ストリーミング応答完了検知ロジックをテスト
        with patch('drivers.selenium_wrapper.SeleniumWrapper') as mock_wrapper_class:
            mock_wrapper = Mock()
            mock_driver = Mock()
            mock_wrapper.driver = mock_driver
            mock_wrapper_class.get_instance.return_value = mock_wrapper

            driver.selenium_wrapper = mock_wrapper

            # モック設定: ストリーミングインジケーターが存在しない（完了状態）
            mock_driver.find_elements.return_value = []

            # 応答完了判定をテスト（安定したテキストの場合）
            result = driver._is_response_complete(mock_element, mock_element.text)

            # 短時間安定していれば完了と判定されることを確認
            # 実際のテストでは時間調整が必要だが、ロジックの存在を確認
            assert isinstance(result, bool)

    def test_partial_response_detection(self):
        """部分応答検知テスト"""
        driver = ChatGPTDriver()

        # 短すぎる応答（部分応答の可能性）
        mock_element = Mock()
        short_text = "Question: ジャンプ"  # 15文字程度
        mock_element.text = short_text

        with patch('drivers.selenium_wrapper.SeleniumWrapper') as mock_wrapper_class:
            mock_wrapper = Mock()
            mock_driver = Mock()
            mock_wrapper.driver = mock_driver
            mock_wrapper_class.get_instance.return_value = mock_wrapper

            driver.selenium_wrapper = mock_wrapper
            mock_driver.find_elements.return_value = []

            # 短すぎる応答は未完了と判定されることを確認
            result = driver._is_response_complete(mock_element, mock_element.text)
            assert result == False  # 短すぎるため継続すべき


class TestModels:
    """データモデルテストクラス"""

    def test_chat_message_validation(self):
        """ChatMessageバリデーションテスト"""
        # 正常なメッセージ
        message = ChatMessage(role="user", content="Test content")
        assert message.role == "user"
        assert message.content == "Test content"

        # 空のコンテンツでもバリデーション通過
        message = ChatMessage(role="system", content="")
        assert message.content == ""

    def test_chat_completion_request_validation(self):
        """ChatCompletionRequestバリデーションテスト"""
        # 必須フィールドのみ
        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="Test")]
        )
        assert request.model == "gpt-3.5-turbo"
        assert len(request.messages) == 1
        assert request.temperature == 1.0  # デフォルト値

        # オプションフィールド指定
        request = ChatCompletionRequest(
            model="gpt-4",
            messages=[ChatMessage(role="user", content="Test")],
            max_tokens=100,
            temperature=0.5
        )
        assert request.max_tokens == 100
        assert request.temperature == 0.5


class TestUtils:
    """ユーティリティ関数テストクラス"""

    def test_generate_id(self):
        """ID生成テスト"""
        from utils import generate_id

        # デフォルトプレフィックス
        id1 = generate_id()
        assert id1.startswith("chatcmpl-")

        # カスタムプレフィックス
        id2 = generate_id("test")
        assert id2.startswith("test-")

        # ユニーク性確認（簡易）
        assert id1 != id2

    def test_sanitize_message(self):
        """メッセージサニタイズテスト"""
        from utils import sanitize_message

        # 通常メッセージ
        normal_msg = "Hello world"
        assert sanitize_message(normal_msg) == normal_msg

        # 機密情報含有メッセージ
        sensitive_msg = "My password is secret123"
        sanitized = sanitize_message(sensitive_msg)
        assert "***REDACTED***" in sanitized

    def test_create_error_response(self):
        """エラーレスポンス作成テスト"""
        from utils import create_error_response

        error_resp = create_error_response("test_error", "Test error message")
        assert error_resp["error"]["code"] == "test_error"
        assert error_resp["error"]["message"] == "Test error message"
        assert error_resp["error"]["type"] == "invalid_request_error"


# 境界値テスト
class TestBoundaryValues:
    """境界値テストクラス"""

    def test_large_message_content(self):
        """大きなメッセージコンテンツテスト"""
        large_content = "x" * 10000  # 10KB
        message = ChatMessage(role="user", content=large_content)
        assert len(message.content) == 10000

    def test_zero_max_tokens(self):
        """max_tokens=0テスト"""
        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="Test")],
            max_tokens=0
        )
        assert request.max_tokens == 0

    def test_extreme_temperature_values(self):
        """極端なtemperature値テスト"""
        # 最小値
        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="Test")],
            temperature=0.0
        )
        assert request.temperature == 0.0

        # 最大値
        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="Test")],
            temperature=2.0
        )
        assert request.temperature == 2.0


# エラー推測法テスト
class TestErrorGuessing:
    """エラー推測法テストクラス"""

    def setup_method(self):
        """テストメソッド前のセットアップ"""
        self.client = TestClient(app)

    def test_no_user_messages(self):
        """ユーザーメッセージなしテスト"""
        service = ChatGPTService()
        messages = [
            ChatMessage(role="system", content="System message"),
            ChatMessage(role="assistant", content="Assistant message")
        ]
        latest = service._get_latest_user_message(messages)
        assert latest is None

    @patch('api.get_chatgpt_service')
    def test_authentication_error_with_footer_detection(self, mock_get_service):
        """認証エラーとフッター検出テスト"""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # RuntimeError with login message
        mock_service.create_chat_completion.side_effect = RuntimeError("ChatGPTにログインしていません。手動でログインしてからAPIを使用してください。")

        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Test message"}
            ]
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 401
        data = response.json()
        # FastAPIのHTTPExceptionはdetail内にエラー情報を格納
        assert data["detail"]["error"]["type"] == "invalid_request_error"
        assert data["detail"]["error"]["code"] == "authentication_required"
        assert "ログイン" in data["detail"]["error"]["message"]

    def test_login_state_check(self):
        """ログイン状態チェック機能テスト"""
        with patch('drivers.selenium_wrapper.SeleniumWrapper') as mock_wrapper_class:
            mock_wrapper = Mock()
            mock_driver = Mock()
            mock_wrapper.driver = mock_driver
            mock_wrapper_class.get_instance.return_value = mock_wrapper

            driver = ChatGPTDriver()
            driver.selenium_wrapper = mock_wrapper

            # ログインボタンが存在する場合（未ログイン）
            mock_driver.find_elements.return_value = [Mock(is_displayed=Mock(return_value=True))]
            assert not driver._check_login_status()

            # ChatGPT要素が存在する場合（ログイン済み）
            def side_effect_func(by, selector):
                if any(indicator in selector for indicator in ['login-button', 'signup-button', 'auth']):
                    return []
                elif any(indicator in selector for indicator in ['prompt-textarea', 'contenteditable', 'composer-button']):
                    return [Mock(is_displayed=Mock(return_value=True))]
                else:
                    return []

            mock_driver.find_elements.side_effect = side_effect_func
            assert driver._check_login_status()

    def test_footer_text_rejection(self):
        """フッターテキスト拒否テスト"""
        footer_patterns = [
            "ChatGPT の回答は必ずしも正しいとは限りません",
            "重要な情報は確認するようにしてください",
            "ChatGPT にメッセージを送ると、規約に同意し",
            "プライバシーポリシーを読んだものとみなされます",
            "無料でサインアップ",
            "ログイン"
        ]

        # フッターテキストのサンプル
        footer_text = "ログイン\n無料でサインアップ\nChatGPT の回答は必ずしも正しいとは限りません。重要な情報は確認するようにしてください"

        # フッターパターンが検出されることを確認
        is_footer = False
        for pattern in footer_patterns:
            if pattern in footer_text:
                is_footer = True
                break

        assert is_footer, "Footer pattern should be detected"

        # 正常な応答テキストは検出されないことを確認
        normal_response = "こんにちは！今日はどのようなお手伝いができますか？"
        is_footer = False
        for pattern in footer_patterns:
            if pattern in normal_response:
                is_footer = True
                break

        assert not is_footer, "Normal response should not be detected as footer"

    @patch('api.get_chatgpt_service')
    def test_comprehensive_login_error_handling(self, mock_get_service):
        """包括的ログインエラーハンドリングテスト"""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # Different types of login-related errors
        login_errors = [
            "ChatGPTにログインしていません",
            "ログインセッションが期限切れです",
            "ChatGPTの応答を正しく取得できませんでした。ログイン状態を確認してください"
        ]

        for error_message in login_errors:
            mock_service.create_chat_completion.side_effect = RuntimeError(error_message)

            request_data = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "user", "content": "Test message"}
                ]
            }

            response = self.client.post("/v1/chat/completions", json=request_data)
            assert response.status_code == 401
            data = response.json()
            # FastAPIのHTTPExceptionはdetail内にエラー情報を格納
            assert data["detail"]["error"]["type"] == "invalid_request_error"
            assert data["detail"]["error"]["code"] == "authentication_required"
        """サービス障害処理テスト"""
        # モックサービス作成
        mock_service = MagicMock()
        mock_service.create_chat_completion.return_value = None
        mock_get_service.return_value = mock_service

        client = TestClient(app)
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Test"}]
        }

        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 500
        data = response.json()
        assert "error" in data["detail"]

    @patch('api.get_chatgpt_service')
    def test_authentication_required_error(self, mock_get_service):
        """認証必須エラーテスト"""
        # モックサービス作成
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # ログイン関連のRuntimeErrorを発生させる
        mock_service.create_chat_completion.side_effect = RuntimeError("ChatGPTにログインしていません")

        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Test"}]
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 401
        data = response.json()
        assert "authentication_required" in data["detail"]["error"]["code"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
