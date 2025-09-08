import unittest
from unittest.mock import Mock, patch
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import ChatMessage, ChatCompletionRequest
from utils import generate_id, sanitize_message, create_error_response


class TestBasicFunctionality(unittest.TestCase):
    """基本機能テストクラス（外部依存なし）"""

    def test_chat_message_creation(self):
        """ChatMessage作成テスト"""
        message = ChatMessage(role="user", content="Test message")
        self.assertEqual(message.role, "user")
        self.assertEqual(message.content, "Test message")

    def test_chat_completion_request_creation(self):
        """ChatCompletionRequest作成テスト"""
        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[ChatMessage(role="user", content="Test")]
        )
        self.assertEqual(request.model, "gpt-3.5-turbo")
        self.assertEqual(len(request.messages), 1)
        self.assertEqual(request.temperature, 1.0)  # デフォルト値

    def test_generate_id_functionality(self):
        """ID生成機能テスト"""
        id1 = generate_id()
        id2 = generate_id()

        self.assertTrue(id1.startswith("chatcmpl-"))
        self.assertTrue(id2.startswith("chatcmpl-"))
        self.assertNotEqual(id1, id2)  # ユニーク性確認

    def test_sanitize_message_normal(self):
        """通常メッセージサニタイズテスト"""
        normal_msg = "Hello world"
        result = sanitize_message(normal_msg)
        self.assertEqual(result, normal_msg)

    def test_sanitize_message_sensitive(self):
        """機密情報サニタイズテスト"""
        sensitive_msg = "My password is secret123"
        result = sanitize_message(sensitive_msg)
        self.assertIn("***REDACTED***", result)

    def test_create_error_response(self):
        """エラーレスポンス作成テスト"""
        error_resp = create_error_response("test_error", "Test message")

        self.assertIn("error", error_resp)
        self.assertEqual(error_resp["error"]["code"], "test_error")
        self.assertEqual(error_resp["error"]["message"], "Test message")
        self.assertEqual(error_resp["error"]["type"], "invalid_request_error")

    def test_boundary_values(self):
        """境界値テスト"""
        # 空文字列
        empty_message = ChatMessage(role="user", content="")
        self.assertEqual(empty_message.content, "")

        # 大きな文字列
        large_content = "x" * 1000
        large_message = ChatMessage(role="user", content=large_content)
        self.assertEqual(len(large_message.content), 1000)

    def test_invalid_role_handling(self):
        """無効なロール処理テスト"""
        # 通常は無効なロールでもモデルは受け入れる（バリデーションは別層で実施）
        message = ChatMessage(role="invalid_role", content="Test")
        self.assertEqual(message.role, "invalid_role")


class TestServiceLogic(unittest.TestCase):
    """サービスロジックテスト（モック使用）"""

    def setUp(self):
        """テストセットアップ"""
        # サービスクラスの import を遅延させる（依存関係回避）
        try:
            from services import ChatGPTService
            self.service_class = ChatGPTService
        except ImportError:
            self.service_class = None

    def test_get_latest_user_message(self):
        """最新ユーザーメッセージ取得テスト"""
        if not self.service_class:
            self.skipTest("Services module not available")

        # モックインスタンス作成
        with patch('services.ChatGPTDriver'):
            service = self.service_class()

            messages = [
                ChatMessage(role="system", content="System message"),
                ChatMessage(role="user", content="First user message"),
                ChatMessage(role="assistant", content="Assistant response"),
                ChatMessage(role="user", content="Latest user message")
            ]

            latest = service._get_latest_user_message(messages)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.content, "Latest user message")

    def test_get_latest_user_message_empty(self):
        """空リストでの最新ユーザーメッセージ取得テスト"""
        if not self.service_class:
            self.skipTest("Services module not available")

        with patch('services.ChatGPTDriver'):
            service = self.service_class()

            empty_messages = []
            latest = service._get_latest_user_message(empty_messages)
            self.assertIsNone(latest)

    def test_estimate_tokens(self):
        """トークン数推定テスト"""
        if not self.service_class:
            self.skipTest("Services module not available")

        with patch('services.ChatGPTDriver'):
            service = self.service_class()

            messages = [
                ChatMessage(role="user", content="Hello world!")  # 12文字
            ]

            tokens = service._estimate_tokens(messages)
            self.assertGreaterEqual(tokens, 1)
            self.assertEqual(tokens, 12 // 4)  # 文字数/4の計算


class TestConfigurationHandling(unittest.TestCase):
    """設定処理テストクラス"""

    def test_default_settings(self):
        """デフォルト設定テスト"""
        try:
            from config import Settings
            settings = Settings()

            self.assertEqual(settings.port, 8000)
            self.assertEqual(settings.host, "0.0.0.0")
            self.assertEqual(settings.browser_type, "chrome")
            self.assertFalse(settings.headless)
            self.assertEqual(settings.timeout, 30)
            self.assertEqual(settings.profile_dir_path, "")  # デフォルト値確認

        except ImportError:
            self.skipTest("Config module not available")

    def test_env_settings(self):
        """環境変数設定テスト"""
        try:
            import os
            from config import Settings

            # 環境変数を設定
            os.environ["PROFILE_DIR_PATH"] = "/test/profile/path"

            # 設定クラスを再インスタンス化
            settings = Settings()

            self.assertEqual(settings.profile_dir_path, "/test/profile/path")

            # 環境変数をクリア
            if "PROFILE_DIR_PATH" in os.environ:
                del os.environ["PROFILE_DIR_PATH"]

        except ImportError:
            self.skipTest("Config module not available")


class TestDriverConfiguration(unittest.TestCase):
    """ドライバー設定テストクラス"""

    def setUp(self):
        """テストセットアップ"""
        try:
            from drivers import ChatGPTDriver
            self.driver_class = ChatGPTDriver
        except ImportError:
            self.driver_class = None

    def test_session_state_management(self):
        """セッション状態管理テスト"""
        if not self.driver_class:
            self.skipTest("Drivers module not available")

        driver = self.driver_class()

        # 初期状態
        self.assertFalse(driver.is_session_active())

        # セッション状態変更（SeleniumWrapper使用）
        from unittest.mock import Mock
        mock_wrapper = Mock()
        mock_wrapper.driver = Mock()
        mock_wrapper.driver.session_id = "test-session-id"

        driver.selenium_wrapper = mock_wrapper
        driver._session_active = True
        self.assertTrue(driver.is_session_active())

        driver._session_active = False
        self.assertFalse(driver.is_session_active())


def run_basic_tests():
    """基本テストのみ実行（外部依存なし）"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 基本機能テストのみ追加
    suite.addTests(loader.loadTestsFromTestCase(TestBasicFunctionality))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


def run_all_tests():
    """全テスト実行"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 全テストクラスを追加
    test_classes = [
        TestBasicFunctionality,
        TestServiceLogic,
        TestConfigurationHandling,
        TestDriverConfiguration
    ]

    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("=== Running Basic Tests (No External Dependencies) ===")
    basic_success = run_basic_tests()

    print("\n=== Running All Tests ===")
    all_success = run_all_tests()

    if basic_success and all_success:
        print("\n✅ All tests passed!")
        exit(0)
    else:
        print("\n❌ Some tests failed!")
        exit(1)
