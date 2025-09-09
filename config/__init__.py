import os
from typing import Optional
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """アプリケーション設定"""

    # サーバー設定
    port: int = 8000
    host: str = "0.0.0.0"

    # ブラウザ設定
    browser_type: str = "chrome"  # chrome, firefox
    headless: bool = False
    timeout: int = 30

    # ChatGPT設定
    chatgpt_url: str = "https://chat.openai.com"

    # SeleniumWrapper設定（新規追加）
    chrome_path: str = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    profile_dir_path: str = ""  # 空の場合は一時ディレクトリを使用
    chrome_debug_port: str = ""  # 空の場合は自動選択

    # 自動起動設定（新規追加）
    auto_start_browser: bool = True  # ブラウザ自動起動
    startup_timeout: int = 30  # 起動タイムアウト（秒）

    # 入力処理最適化設定（新規追加）
    input_cleanup_delay: float = 0.8    # clear()後の待機時間（秒）
    safe_send_limit: int = 150          # 安全な単一送信文字数上限
    init_timeout: int = 15              # 初期化タイムアウト（秒）
    residual_cleanup: bool = True       # 残存データクリーンアップ有効/無効

    # ログ設定
    log_level: str = "INFO"

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


# グローバル設定インスタンス
settings = Settings()
