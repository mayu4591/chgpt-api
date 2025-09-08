#!/usr/bin/env python3
"""
Function Calling機能のテストコード
"""

import unittest
import json
from unittest.mock import Mock, patch
from models import (
    ChatMessage,
    ChatCompletionRequest,
    FunctionDefinition,
    ToolDefinition,
    FunctionCall
)


class TestFunctionCalling(unittest.TestCase):
    """Function Calling機能テストクラス"""

    def setUp(self):
        """テストセットアップ"""
        try:
            from services import ChatGPTService
            self.service_class = ChatGPTService
        except ImportError:
            self.service_class = None

    def test_function_definition_creation(self):
        """Function定義作成テスト"""
        func_def = FunctionDefinition(
            name="get_weather",
            description="Get current weather",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        )

        self.assertEqual(func_def.name, "get_weather")
        self.assertEqual(func_def.description, "Get current weather")
        self.assertIn("location", func_def.parameters["properties"])

    def test_function_call_creation(self):
        """Function Call作成テスト"""
        func_call = FunctionCall(
            name="get_weather",
            arguments='{"location": "Tokyo"}'
        )

        self.assertEqual(func_call.name, "get_weather")
        self.assertEqual(func_call.arguments, '{"location": "Tokyo"}')

    def test_chat_message_with_function_call(self):
        """Function Call付きChatMessageテスト"""
        func_call = FunctionCall(
            name="get_weather",
            arguments='{"location": "Tokyo"}'
        )

        message = ChatMessage(
            role="assistant",
            content=None,
            function_call=func_call
        )

        self.assertEqual(message.role, "assistant")
        self.assertIsNone(message.content)
        self.assertEqual(message.function_call.name, "get_weather")

    def test_function_role_message(self):
        """Function roleメッセージテスト"""
        message = ChatMessage(
            role="function",
            name="get_weather",
            content='{"temperature": "22°C", "condition": "sunny"}'
        )

        self.assertEqual(message.role, "function")
        self.assertEqual(message.name, "get_weather")
        self.assertIn("temperature", message.content)

    def test_chat_completion_request_with_functions(self):
        """Functions付きChatCompletionRequestテスト"""
        func_def = FunctionDefinition(
            name="get_weather",
            description="Get current weather",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        )

        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[
                ChatMessage(role="user", content="What's the weather in Tokyo?")
            ],
            functions=[func_def],
            function_call="auto"
        )

        self.assertEqual(len(request.functions), 1)
        self.assertEqual(request.functions[0].name, "get_weather")
        self.assertEqual(request.function_call, "auto")

    def test_tools_api_format(self):
        """Tools API形式テスト"""
        func_def = FunctionDefinition(
            name="get_weather",
            description="Get current weather",
            parameters={"type": "object", "properties": {}}
        )

        tool_def = ToolDefinition(
            type="function",
            function=func_def
        )

        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[
                ChatMessage(role="user", content="What's the weather?")
            ],
            tools=[tool_def],
            tool_choice="auto"
        )

        self.assertEqual(len(request.tools), 1)
        self.assertEqual(request.tools[0].type, "function")
        self.assertEqual(request.tools[0].function.name, "get_weather")

    @patch('services.ChatGPTDriver')
    def test_function_context_building(self, mock_driver_class):
        """Function定義コンテキスト構築テスト"""
        if not self.service_class:
            self.skipTest("Services module not available")

        # モックドライバー設定
        mock_driver = Mock()
        mock_driver.is_session_active.return_value = True
        mock_driver_class.return_value = mock_driver

        service = self.service_class()
        service.driver = mock_driver

        func_def = FunctionDefinition(
            name="get_weather",
            description="Get current weather",
            parameters={"type": "object"}
        )

        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="Test")],
            functions=[func_def]
        )

        context = service._build_function_context(request)

        self.assertIn("get_weather", context)
        self.assertIn("Get current weather", context)
        self.assertIn("function_call", context)

    @patch('services.ChatGPTDriver')
    def test_function_call_detection(self, mock_driver_class):
        """Function Call検出テスト"""
        if not self.service_class:
            self.skipTest("Services module not available")

        mock_driver = Mock()
        mock_driver_class.return_value = mock_driver

        service = self.service_class()

        # Function定義
        func_def = FunctionDefinition(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object"}
        )

        # Function Callを含むレスポンス（より明確なJSON形式）
        response_with_call = '{"function_call": {"name": "get_weather", "arguments": "{\\"location\\": \\"Tokyo\\"}"}}'

        function_call = service._detect_function_call(response_with_call, [func_def])

        self.assertIsNotNone(function_call)
        self.assertEqual(function_call["name"], "get_weather")
        self.assertIn("Tokyo", function_call["arguments"])

    def test_boundary_values_function_calling(self):
        """Function Calling境界値テスト"""
        # 空のFunction定義
        request_empty_functions = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="Test")],
            functions=[]
        )
        self.assertEqual(len(request_empty_functions.functions), 0)

        # Noneのfunction_call
        request_none_call = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="Test")],
            function_call=None
        )
        self.assertIsNone(request_none_call.function_call)

    def test_complex_function_parameters(self):
        """複雑なFunction パラメータテスト"""
        complex_params = {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state"
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature unit"
                },
                "details": {
                    "type": "object",
                    "properties": {
                        "include_forecast": {"type": "boolean"},
                        "days": {"type": "integer", "minimum": 1, "maximum": 7}
                    }
                }
            },
            "required": ["location"]
        }

        func_def = FunctionDefinition(
            name="get_detailed_weather",
            description="Get detailed weather information",
            parameters=complex_params
        )

        self.assertEqual(func_def.name, "get_detailed_weather")
        self.assertEqual(len(func_def.parameters["properties"]), 3)
        self.assertIn("celsius", func_def.parameters["properties"]["unit"]["enum"])


class TestFunctionCallingIntegration(unittest.TestCase):
    """Function Calling統合テストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.maxDiff = None  # diff制限を無効化

    def test_complete_function_call_flow(self):
        """完全なFunction Call フローテスト"""
        # 1. Function定義付きリクエスト
        func_def = FunctionDefinition(
            name="calculate_area",
            description="Calculate area of a rectangle",
            parameters={
                "type": "object",
                "properties": {
                    "width": {"type": "number"},
                    "height": {"type": "number"}
                },
                "required": ["width", "height"]
            }
        )

        initial_request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[
                ChatMessage(role="user", content="Calculate area of 5x3 rectangle")
            ],
            functions=[func_def],
            function_call="auto"
        )

        # 2. Function Call応答のシミュレーション
        function_call_message = ChatMessage(
            role="assistant",
            content=None,
            function_call=FunctionCall(
                name="calculate_area",
                arguments='{"width": 5, "height": 3}'
            )
        )

        # 3. Function実行結果付きの継続リクエスト
        continuation_request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[
                ChatMessage(role="user", content="Calculate area of 5x3 rectangle"),
                function_call_message,
                ChatMessage(
                    role="function",
                    name="calculate_area",
                    content="15"
                )
            ]
        )

        # テスト実行
        self.assertEqual(initial_request.functions[0].name, "calculate_area")
        self.assertEqual(function_call_message.function_call.name, "calculate_area")
        self.assertEqual(continuation_request.messages[2].content, "15")


def run_function_calling_tests():
    """Function Callingテストのみ実行"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Function Callingテストを追加
    suite.addTests(loader.loadTestsFromTestCase(TestFunctionCalling))
    suite.addTests(loader.loadTestsFromTestCase(TestFunctionCallingIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    run_function_calling_tests()
