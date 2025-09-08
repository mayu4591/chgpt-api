import logging
import time
from typing import Dict, Any


def setup_logging(level: str = "INFO") -> None:
    """ログ設定をセットアップ"""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def generate_id(prefix: str = "chatcmpl") -> str:
    """ユニークIDを生成"""
    import random
    import uuid
    timestamp = str(int(time.time() * 1000000))  # マイクロ秒精度
    random_suffix = str(uuid.uuid4())[:8]  # UUIDの一部を使用
    return f"{prefix}-{timestamp}-{random_suffix}"


def get_current_timestamp() -> int:
    """現在のタイムスタンプを取得"""
    return int(time.time())


def sanitize_message(message: str) -> str:
    """メッセージをサニタイズ"""
    # 機密情報のログ出力を防ぐため、機密性の高い文字列をマスク
    sensitive_patterns = ["password", "token", "key", "secret"]
    sanitized = message
    for pattern in sensitive_patterns:
        if pattern.lower() in message.lower():
            sanitized = sanitized.replace(message, "***REDACTED***")
            break
    return sanitized


def create_error_response(error_code: str, error_message: str) -> Dict[str, Any]:
    """エラーレスポンスを作成"""
    return {
        "error": {
            "code": error_code,
            "message": error_message,
            "type": "invalid_request_error"
        }
    }
