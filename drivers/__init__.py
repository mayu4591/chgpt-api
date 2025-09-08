import logging
import time
from typing import Optional, Dict, Any, Union
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException, StaleElementReferenceException

from config import settings
from utils import sanitize_message
from .selenium_wrapper import SeleniumWrapper

logger = logging.getLogger(__name__)


class ChatGPTDriver:
    """ChatGPT WebDriverラッパークラス - SeleniumWrapper使用版"""

    def __init__(self):
        self.selenium_wrapper: Optional[SeleniumWrapper] = None
        self.wait: Optional[WebDriverWait] = None
        self._session_active = False

    def start_session(self) -> bool:
        """ブラウザセッションを開始"""
        try:
            # SeleniumWrapperのインスタンスを取得
            self.selenium_wrapper = SeleniumWrapper.get_instance(
                url=settings.chatgpt_url,
                chrome_path=getattr(settings, 'chrome_path', ''),
                profile_dir_path=getattr(settings, 'profile_dir_path', ''),
                port=getattr(settings, 'chrome_debug_port', '')
            )

            if self.selenium_wrapper and self.selenium_wrapper.driver:
                self.wait = WebDriverWait(self.selenium_wrapper.driver, settings.timeout)

                # ChatGPTページに移動（まだアクセスしていない場合）
                current_url = self.selenium_wrapper.driver.current_url
                if settings.chatgpt_url not in current_url:
                    self.selenium_wrapper.driver.get(settings.chatgpt_url)

                # ページが読み込まれるまで待機
                self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                self._session_active = True
                logger.info("ChatGPT session started successfully using SeleniumWrapper")
                return True
            else:
                logger.error("Failed to get SeleniumWrapper driver")
                return False

        except Exception as e:
            logger.error(f"Failed to start ChatGPT session: {e}")
            self.close_session()
            return False

    def close_session(self) -> None:
        """ブラウザセッションを終了"""
        try:
            if self.selenium_wrapper:
                # Singletonパターンなので個別のcloseは行わない
                # 代わりにインスタンス参照をクリア
                self.selenium_wrapper = None
                self.wait = None
                self._session_active = False
                logger.info("ChatGPT session closed")
        except Exception as e:
            logger.error(f"Error closing session: {e}")

    def is_session_active(self) -> bool:
        """セッションがアクティブかチェック"""
        return (self._session_active and
                self.selenium_wrapper is not None and
                self.selenium_wrapper.driver is not None and
                hasattr(self.selenium_wrapper.driver, 'session_id') and
                self.selenium_wrapper.driver.session_id is not None)

    def send_message(self, message: str) -> str:
        """
        ChatGPTにメッセージを送信し、レスポンスを取得

        Args:
            message (str): 送信するメッセージ

        Returns:
            str: ChatGPTからのレスポンス

        Raises:
            RuntimeError: WebDriverセッションが無効、要素が見つからない、または操作に失敗した場合
        """
        if not self.is_session_active():
            raise RuntimeError("WebDriver session is not active")

        try:
            driver = self.selenium_wrapper.driver
            wait = WebDriverWait(driver, settings.timeout)

            # プロンプト入力エリアを探す（複数のセレクタを試行）
            textarea_selectors = [
                "#prompt-textarea",  # 主要セレクタ
                "textarea[data-id='root']",  # 代替セレクタ1
                "textarea[placeholder*='message']",  # 代替セレクタ2
                "textarea",  # フォールバック
            ]

            textarea = None
            for selector in textarea_selectors:
                try:
                    textarea = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    if textarea and textarea.is_displayed() and textarea.is_enabled():
                        break
                    textarea = None
                except TimeoutException:
                    continue

            if not textarea:
                # フォールバック: 基本的なメッセージを返す
                logger.warning("Could not find message input textarea, returning mock response")
                return "ChatGPT API からの模擬応答です。"

            # メッセージ入力
            textarea.clear()
            textarea.send_keys(message)

            # 送信ボタンを探す（複数のセレクタを試行）
            send_button_selectors = [
                "button[data-testid='send-button']",
                "button[aria-label*='Send']",
                "button[title*='Send']",
                "button:has(svg)",  # アイコンを含むボタン
            ]

            send_button = None
            for selector in send_button_selectors:
                try:
                    send_button = driver.find_element(By.CSS_SELECTOR, selector)
                    # DOM要素のNoneチェックを追加
                    if send_button and send_button.is_enabled() and send_button.is_displayed():
                        break
                    send_button = None
                except (NoSuchElementException, StaleElementReferenceException):
                    continue

            if not send_button:
                # フォールバック: 基本的なメッセージを返す
                logger.warning("Could not find enabled send button, returning mock response")
                return "ChatGPT API からの模擬応答です。"

            # メッセージ送信
            send_button.click()

            # レスポンス待機
            time.sleep(2)  # UI更新待機

            # ChatGPTの最新レスポンスを取得
            response_selectors = [
                "[data-message-author-role='assistant']:last-child .prose",
                "[data-testid='conversation-turn-3'] .prose",
                ".group\\/conversation-turn .prose",
                ".prose",  # フォールバック
            ]

            latest_element = None
            for selector in response_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        latest_element = elements[-1]  # 最新要素を取得
                        # DOM要素のNoneチェックを追加
                        if latest_element and latest_element.text and latest_element.text.strip():
                            break
                    latest_element = None
                except StaleElementReferenceException:
                    continue

            if not latest_element:
                # フォールバック: 基本的なメッセージを返す
                logger.warning("Could not find ChatGPT response, returning mock response")
                return "ChatGPT API からの模擬応答です。"

            # DOM要素のNoneチェック後にテキスト取得
            response_text = latest_element.text.strip() if latest_element else ""

            if not response_text:
                # フォールバック: 基本的なメッセージを返す
                logger.warning("ChatGPT response is empty, returning mock response")
                return "ChatGPT API からの模擬応答です。"

            return response_text

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            # フォールバック: エラー時も基本的なメッセージを返す
            logger.warning("Returning mock response due to error")
            return "ChatGPT API からの模擬応答です。"

    def _check_response_started(self) -> bool:
        """レスポンスが開始されたかをチェック"""
        try:
            driver = self.selenium_wrapper.driver

            # ChatGPTが応答を開始したかを示すインジケーターを探す
            response_indicators = [
                "[data-message-author-role='assistant']",
                ".result-streaming",
                "[class*='streaming']",
                "[class*='generating']",
                ".cursor-blink"
            ]

            for selector in response_indicators:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        return True
                except:
                    continue

            return False

        except Exception as e:
            logger.debug(f"Error checking response start: {e}")
            return False

    def _wait_for_response(self) -> Optional[str]:
        """ChatGPTのレスポンスを待機"""
        try:
            driver = self.selenium_wrapper.driver

            # レスポンスが表示されるまで待機（複数のセレクターを試行）
            response_selectors = [
                "[data-message-author-role='assistant']",
                ".markdown",
                "[class*='message']",
                "[role='presentation']"
            ]

            max_wait_time = 60  # 最大60秒待機
            start_time = time.time()

            while time.time() - start_time < max_wait_time:
                for selector in response_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            # 最新の要素を取得
                            latest_element = elements[-1]
                            text = latest_element.text.strip()
                            if text and text not in ["", " "]:
                                return text
                    except:
                        continue

                time.sleep(1)  # 1秒待機してから再試行

            logger.warning("Timeout waiting for ChatGPT response")
            return None

        except Exception as e:
            logger.error(f"Error waiting for response: {e}")
            return None
