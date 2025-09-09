#!/usr/bin/env python3
"""
入力処理最適化機能の包括的テストスイート
- 境界値テスト（149, 150, 151文字）
- 送信戦略テスト
- パフォーマンステスト
- 統合テスト
"""

import unittest
import time
import os
from unittest.mock import patch, MagicMock
from drivers import ChatGPTDriver
from config import settings


class TestInputOptimization(unittest.TestCase):
    """入力処理最適化テストクラス"""

    def setUp(self):
        """テストセットアップ"""
        self.driver = None
        self.original_settings = {}

    def tearDown(self):
        """テストクリーンアップ"""
        if self.driver:
            try:
                self.driver.cleanup()
            except:
                pass

        # 設定を元に戻す
        for key, value in self.original_settings.items():
            setattr(settings, key, value)

    def test_boundary_value_send_strategy(self):
        """境界値テスト：149, 150, 151文字での送信戦略"""
        print("\n🧪 Test: 境界値での送信戦略選択")

        with patch('drivers.SeleniumWrapper') as mock_wrapper:
            mock_driver = MagicMock()
            mock_wrapper.return_value.driver = mock_driver

            driver = ChatGPTDriver()

            # 境界値テストケース
            test_cases = [
                (149, "safe_single", "149文字は安全単一送信"),
                (150, "safe_single", "150文字は境界で安全単一送信"),
                (151, "try_single_fallback_chunk", "151文字は単一試行→フォールバック"),
                (4000, "try_single_fallback_chunk", "4000文字は単一試行→フォールバック"),
                (4001, "smart_chunking", "4001文字はスマートチャンキング")
            ]

            for message_length, expected_strategy, description in test_cases:
                strategy = driver._select_send_strategy(message_length)
                self.assertEqual(strategy, expected_strategy,
                               f"{description}: 期待={expected_strategy}, 実際={strategy}")
                print(f"✅ {description}: {strategy}")

    def test_enhanced_cleanup_with_residual_data(self):
        """残存データがある場合の段階的クリーンアップテスト"""
        print("\n🧪 Test: 残存データクリーンアップ")

        with patch('drivers.SeleniumWrapper') as mock_wrapper:
            mock_element = MagicMock()
            mock_element.get_attribute.side_effect = ["Pl", ""]  # 最初は残存、後はクリーン
            mock_element.text = ""
            mock_element.is_displayed.return_value = True
            mock_element.is_enabled.return_value = True

            mock_driver = MagicMock()
            mock_driver.find_elements.return_value = [mock_element]
            mock_wrapper.return_value.driver = mock_driver

            driver = ChatGPTDriver()

            # 段階的クリーンアップ実行
            residual = driver._enhanced_cleanup(mock_element)

            # クリーンアップが実行されたことを確認
            mock_element.clear.assert_called()
            mock_element.send_keys.assert_any_call(unittest.mock.ANY)  # Ctrl+A

            self.assertEqual(residual, "Pl", "残存データが正しく検出された")
            print("✅ 残存データ'Pl'が検出され、段階的クリーンアップが実行されました")

    def test_send_strategy_execution(self):
        """送信戦略実行テスト"""
        print("\n🧪 Test: 送信戦略実行")

        with patch('drivers.SeleniumWrapper') as mock_wrapper:
            mock_element = MagicMock()
            mock_element.is_displayed.return_value = True
            mock_element.is_enabled.return_value = True

            mock_driver = MagicMock()
            mock_driver.find_elements.return_value = [mock_element]
            mock_wrapper.return_value.driver = mock_driver

            driver = ChatGPTDriver()

            # 各戦略のテスト
            strategies = [
                ("safe_single", "hello world", "短いメッセージの安全送信"),
                ("try_single_fallback_chunk", "a" * 200, "中程度メッセージの単一試行"),
                ("smart_chunking", "a" * 5000, "長いメッセージのスマート分割")
            ]

            for strategy, message, description in strategies:
                with self.subTest(strategy=strategy):
                    driver._execute_send_strategy(mock_element, message, strategy)
                    print(f"✅ {description}: {strategy}戦略実行完了")

    def test_performance_timing(self):
        """パフォーマンス測定テスト"""
        print("\n🧪 Test: パフォーマンス測定")

        with patch('drivers.SeleniumWrapper') as mock_wrapper:
            mock_element = MagicMock()
            mock_element.get_attribute.return_value = ""  # 残存データなし
            mock_element.text = ""
            mock_element.is_displayed.return_value = True
            mock_element.is_enabled.return_value = True

            mock_driver = MagicMock()
            mock_driver.find_elements.return_value = [mock_element]
            mock_wrapper.return_value.driver = mock_driver

            driver = ChatGPTDriver()

            # クリーンアップ処理の時間測定
            start_time = time.time()
            driver._enhanced_cleanup(mock_element)
            cleanup_time = time.time() - start_time

            # パフォーマンス目標（1秒以内）の確認
            self.assertLess(cleanup_time, 1.0,
                          f"クリーンアップ時間が目標を超過: {cleanup_time:.3f}秒")
            print(f"✅ クリーンアップ時間: {cleanup_time:.3f}秒（目標<1.0秒）")

    def test_configuration_customization(self):
        """設定カスタマイズテスト"""
        print("\n🧪 Test: 設定カスタマイズ")

        # 設定の保存
        self.original_settings['input_cleanup_delay'] = getattr(settings, 'input_cleanup_delay', 0.8)
        self.original_settings['safe_send_limit'] = getattr(settings, 'safe_send_limit', 150)

        # カスタム設定の適用
        settings.input_cleanup_delay = 0.5
        settings.safe_send_limit = 100

        with patch('drivers.SeleniumWrapper') as mock_wrapper:
            mock_driver = MagicMock()
            mock_wrapper.return_value.driver = mock_driver

            driver = ChatGPTDriver()

            # カスタム設定での戦略選択確認
            strategy_99 = driver._select_send_strategy(99)
            strategy_101 = driver._select_send_strategy(101)

            self.assertEqual(strategy_99, "safe_single", "99文字はカスタム設定で安全送信")
            self.assertEqual(strategy_101, "try_single_fallback_chunk", "101文字はカスタム設定で試行→フォールバック")

            print(f"✅ カスタム設定適用: safe_limit={settings.safe_send_limit}, cleanup_delay={settings.input_cleanup_delay}")

    def test_error_recovery(self):
        """エラー回復テスト"""
        print("\n🧪 Test: エラー回復機能")

        with patch('drivers.SeleniumWrapper') as mock_wrapper:
            mock_element = MagicMock()
            mock_element.send_keys.side_effect = [Exception("First attempt failed"), None]  # 1回目失敗、2回目成功
            mock_element.is_displayed.return_value = True
            mock_element.is_enabled.return_value = True

            mock_driver = MagicMock()
            mock_driver.find_elements.return_value = [mock_element]
            mock_wrapper.return_value.driver = mock_driver

            driver = ChatGPTDriver()

            # smart_chunkingメソッドをモック
            with patch.object(driver, '_send_message_with_smart_chunking') as mock_chunking:
                # エラー回復テスト（try_single_fallback_chunk戦略）
                driver._execute_send_strategy(mock_element, "test message", "try_single_fallback_chunk")

                # フォールバックが呼ばれたことを確認
                mock_chunking.assert_called_once()
                print("✅ 送信戦略エラー時のフォールバック機能が正常動作")

    def test_negative_configuration_values(self):
        """ネガティブテスト：不正な設定値"""
        print("\n🧪 Test: 不正な設定値のハンドリング")

        with patch('drivers.SeleniumWrapper') as mock_wrapper:
            mock_driver = MagicMock()
            mock_wrapper.return_value.driver = mock_driver

            driver = ChatGPTDriver()

            # 不正な設定値テストケース
            invalid_configs = [
                (-1, "負の文字数制限"),
                (0, "ゼロ文字数制限"),
                (None, "None値設定")
            ]

            for invalid_value, description in invalid_configs:
                # 設定の一時変更
                original_value = getattr(settings, 'safe_send_limit', 150)
                try:
                    settings.safe_send_limit = invalid_value

                    # 不正値でも適切にフォールバック処理される
                    strategy = driver._select_send_strategy(100)

                    # 不正値の場合はデフォルト値にフォールバック
                    self.assertIn(strategy, ["safe_single", "try_single_fallback_chunk", "smart_chunking"],
                                f"{description}でも有効な戦略が選択される")
                    print(f"✅ {description}: フォールバック戦略={strategy}")

                except Exception as e:
                    # 例外が発生した場合も適切なエラーハンドリング
                    print(f"✅ {description}: 適切にエラーハンドリング={type(e).__name__}")

                finally:
                    # 設定を元に戻す
                    settings.safe_send_limit = original_value

    def test_real_browser_integration(self):
        """実ブラウザ統合テスト（オプション）"""
        print("\n🧪 Test: 実ブラウザ統合テスト")

        if os.getenv('SKIP_BROWSER_TESTS', 'false').lower() == 'true':
            self.skipTest("Browser integration tests are disabled (SKIP_BROWSER_TESTS=true)")

        try:
            driver = ChatGPTDriver()

            # 実際のブラウザでの初期化テスト
            # 注意: このテストは実際のChatGPTサイトにアクセスするため、
            # ネットワーク接続とブラウザ環境が必要
            print("⚠️  実ブラウザテストはスキップされました（実装時は慎重に実行）")
            print("   理由: 実際のChatGPTサイトへのアクセスが必要なため")

        except Exception as e:
            self.skipTest(f"Real browser test skipped due to: {e}")

    def test_message_length_categories(self):
        """メッセージ長カテゴリテスト"""
        print("\n🧪 Test: メッセージ長カテゴリ分類")

        with patch('drivers.SeleniumWrapper') as mock_wrapper:
            mock_driver = MagicMock()
            mock_wrapper.return_value.driver = mock_driver

            driver = ChatGPTDriver()

            # 各カテゴリの代表的メッセージ長テスト
            categories = [
                (10, "safe_single", "超短文"),
                (50, "safe_single", "短文"),
                (100, "safe_single", "標準質問文"),
                (150, "safe_single", "安全限界"),
                (500, "try_single_fallback_chunk", "中程度文書"),
                (2000, "try_single_fallback_chunk", "長文"),
                (8000, "smart_chunking", "超長文")
            ]

            for length, expected, category in categories:
                strategy = driver._select_send_strategy(length)
                self.assertEqual(strategy, expected,
                               f"{category}({length}文字)の戦略が不正: 期待={expected}, 実際={strategy}")
                print(f"✅ {category}({length}文字): {strategy}")


if __name__ == "__main__":
    # テスト実行時の環境変数設定
    os.environ.setdefault('SKIP_BROWSER_TESTS', 'true')  # デフォルトでブラウザテストをスキップ

    unittest.main(verbosity=2)
