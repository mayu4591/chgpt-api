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

    # ログ設定
    log_level: str = "INFO"

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


# グローバル設定インスタンス
settings = Settings()
