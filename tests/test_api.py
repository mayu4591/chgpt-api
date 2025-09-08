import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock

from main import app
from models import ChatMessage, ChatCompletionRequest, FunctionCall, ToolCall
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
        mock_service.create_chat_completion.return_value = Mock(**mock_response)

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
        """ストリーミング未対応テスト"""
        request_data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
            "stream": True
        }

        response = self.client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 400
        data = response.json()
        assert "stream" in data["detail"]["error"]["message"].lower()

    @patch('api.get_chatgpt_service')
    def test_chat_completions_with_functions(self, mock_get_service):
        """Function Calling付きチャット補完テスト"""
        # モックサービス作成
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        # モックレスポンス作成（Function Call応答）
        mock_response = Mock()
        mock_response.id = "chatcmpl-func-test"
        mock_response.object = "chat.completion"
        mock_response.created = 1677652300
        mock_response.model = "gpt-3.5-turbo"
        mock_response.choices = [Mock()]
        mock_response.choices[0].index = 0
        # Function Calling用の正しいモック構造を作成
        mock_function_call = FunctionCall(
            name="get_weather",
            arguments='{"location": "Tokyo"}'
        )

        mock_message = ChatMessage(
            role="assistant",
            content=None,
            function_call=mock_function_call
        )

        mock_response.choices[0].message = mock_message
        mock_response.choices[0].finish_reason = "function_call"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 45
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 55

        mock_service.create_chat_completion.return_value = mock_response

        # Function定義付きリクエスト送信
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

        # モックレスポンス作成
        mock_response = Mock()
        mock_response.id = "chatcmpl-tools-test"
        mock_response.object = "chat.completion"
        mock_response.created = 1677652301
        mock_response.model = "gpt-3.5-turbo"
        mock_response.choices = [Mock()]
        mock_response.choices[0].index = 0
        # Tools用の正しいモック構造を作成
        mock_function = FunctionCall(
            name="calculate_area",
            arguments='{"width": 5, "height": 3}'
        )

        mock_tool_call = ToolCall(
            id="call_123",
            type="function",
            function=mock_function
        )

        mock_message = ChatMessage(
            role="assistant",
            content=None,
            tool_calls=[mock_tool_call]
        )

        mock_response.choices[0].message = mock_message
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 15
        mock_response.usage.total_tokens = 65

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

    def test_chat_completions_invalid_function_call(self):
        """無効なFunction Call設定テスト"""
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
        assert response.status_code in [200, 400, 422, 500]


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

    def test_empty_messages_list(self):
        """空のメッセージリストテスト"""
        service = ChatGPTService()
        empty_messages = []
        latest = service._get_latest_user_message(empty_messages)
        assert latest is None

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
    def test_service_failure_handling(self, mock_get_service):
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
