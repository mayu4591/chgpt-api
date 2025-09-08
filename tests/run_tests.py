#!/usr/bin/env python3
"""
統合テストランナー
依存関係の有無に関わらず実行可能なテストスイート
"""

import sys
import os
import subprocess
import importlib.util

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def check_dependency(module_name):
    """依存関係の存在確認"""
    spec = importlib.util.find_spec(module_name)
    return spec is not None


def run_basic_tests():
    """基本テスト実行（外部依存なし）"""
    print("=== Running Basic Tests (No Dependencies Required) ===")

    try:
        # 基本テストを実行
        result = subprocess.run([
            sys.executable, "-m", "tests.test_basic"
        ], capture_output=True, text=True, cwd=project_root)

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        return result.returncode == 0

    except Exception as e:
        print(f"Error running basic tests: {e}")
        return False


def run_full_tests():
    """フルテスト実行（依存関係必要）"""
    print("\n=== Checking Dependencies ===")

    # 必要な依存関係をチェック
    dependencies = [
        'fastapi',
        'selenium',
        'pytest',
        'pydantic',
        'uvicorn'
    ]

    missing_deps = []
    for dep in dependencies:
        if not check_dependency(dep):
            missing_deps.append(dep)

    if missing_deps:
        print(f"Missing dependencies: {missing_deps}")
        print("Please install with: pip install -r requirements.txt")
        return False

    print("All dependencies found!")

    print("\n=== Running Full Test Suite ===")

    try:
        # pytestを使用してフルテスト実行
        result = subprocess.run([
            sys.executable, "-m", "pytest", "tests/", "-v"
        ], capture_output=True, text=True, cwd=project_root)

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        return result.returncode == 0

    except Exception as e:
        print(f"Error running full tests: {e}")
        return False


def run_smoke_test():
    """スモークテスト（主要機能の簡易確認）"""
    print("\n=== Running Smoke Test ===")

    try:
        # 主要モジュールのインポートテスト
        from models import ChatMessage, ChatCompletionRequest
        from utils import generate_id, sanitize_message

        # 基本機能テスト
        message = ChatMessage(role="user", content="Test")
        assert message.role == "user"

        request = ChatCompletionRequest(
            model="gpt-3.5-turbo",
            messages=[message]
        )
        assert request.model == "gpt-3.5-turbo"

        # ユーティリティ関数テスト
        test_id = generate_id()
        assert test_id.startswith("chatcmpl-")

        sanitized = sanitize_message("Hello world")
        assert sanitized == "Hello world"

        print("✅ Smoke test passed!")
        return True

    except Exception as e:
        print(f"❌ Smoke test failed: {e}")
        return False


def main():
    """メインテストランナー"""
    print("ChatGPT Selenium API - Test Runner")
    print("=" * 50)

    success_count = 0
    total_tests = 3

    # 1. スモークテスト
    if run_smoke_test():
        success_count += 1

    # 2. 基本テスト
    if run_basic_tests():
        success_count += 1

    # 3. フルテスト（依存関係がある場合のみ）
    if check_dependency('fastapi') and check_dependency('pytest'):
        if run_full_tests():
            success_count += 1
    else:
        print("\n=== Skipping Full Tests (Dependencies Not Available) ===")
        print("Install dependencies with: pip install -r requirements.txt")
        total_tests = 2  # フルテストはスキップ

    # 結果サマリー
    print("\n" + "=" * 50)
    print(f"Test Summary: {success_count}/{total_tests} test suites passed")

    if success_count == total_tests:
        print("🎉 All available tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    exit(main())
