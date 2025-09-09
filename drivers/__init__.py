import logging
import time
from typing import Optional, Dict, Any, Union, List

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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

                # ログイン状態をチェック
                if not self._check_login_status():
                    logger.warning("ChatGPT is not logged in. Please log in manually or configure auto-login.")
                    return False

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

    def _check_login_status(self) -> bool:
        """ChatGPTのログイン状態をチェック"""
        try:
            driver = self.selenium_wrapper.driver

            # ログイン状態の判定
            # 1. ログインボタンが存在しない = ログイン済み
            login_indicators = [
                "button[data-testid='login-button']",
                "button[data-testid='signup-button']",
                "a[href*='auth']",
                "text:Login",
                "text:ログイン"
            ]

            for indicator in login_indicators:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, indicator)
                    if elements and any(el.is_displayed() for el in elements):
                        logger.warning(f"Login required: found {indicator}")
                        return False
                except:
                    continue

            # 2. ChatGPT固有の要素が存在する = ログイン済み
            chatgpt_indicators = [
                "#prompt-textarea",
                "[contenteditable='true']",
                "[data-testid='composer-button-search']",
                "[aria-label*='音声モード']"
            ]

            for indicator in chatgpt_indicators:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, indicator)
                    if elements and any(el.is_displayed() for el in elements):
                        logger.info(f"ChatGPT interface detected: {indicator}")
                        return True
                except:
                    continue

            logger.warning("Could not determine login status definitively")
            return False

        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return False

    def _wait_for_login(self, timeout: int = 60) -> bool:
        """ユーザーの手動ログインを待機"""
        try:
            logger.info("Waiting for manual login...")
            start_time = time.time()

            while time.time() - start_time < timeout:
                if self._check_login_status():
                    logger.info("Login detected successfully")
                    return True
                time.sleep(2)

            logger.error("Login timeout exceeded")
            return False

        except Exception as e:
            logger.error(f"Error waiting for login: {e}")
            return False

    def is_session_active(self) -> bool:
        """セッションがアクティブかチェック"""
        return (self._session_active and
                self.selenium_wrapper is not None and
                self.selenium_wrapper.driver is not None and
                hasattr(self.selenium_wrapper.driver, 'session_id') and
                self.selenium_wrapper.driver.session_id is not None)

    def send_message(self, message: str) -> str:
        """
        ChatGPTにメッセージを送信し、応答を取得する（入力処理最適化版）

        Args:
            message (str): 送信するメッセージ

        Returns:
            str: ChatGPTからの応答

        Raises:
            RuntimeError: ログインセッション期限切れまたは応答取得失敗
        """
        try:
            logger.info(f"Starting optimized message sending: {len(message)} chars")

            # ログイン状態を確認
            if not self._check_login_status():
                raise RuntimeError("ChatGPTのログインセッションが期限切れです。再ログインしてからAPIを使用してください。")

            # 最適化された入力操作の安全な実行
            def optimized_input_operation():
                input_element = self._find_input_element()
                
                # 段階的クリーンアップ処理
                residual_data = self._enhanced_cleanup(input_element)
                if residual_data:
                    logger.warning(f"Residual data was cleaned: '{residual_data}'")
                
                # 送信戦略の選択と実行
                strategy = self._select_send_strategy(len(message))
                logger.debug(f"Selected send strategy: {strategy}")
                
                self._execute_send_strategy(input_element, message, strategy)
                return input_element

            logger.debug("Performing optimized input operation...")
            self.safe_element_operation(optimized_input_operation)
            time.sleep(0.5)  # 入力完了待機

            # 送信操作の安全な実行（既存のロジックを維持）
            send_successful = False
            send_attempts = 0
            max_send_attempts = 2

            def send_operation():
                nonlocal send_successful, send_attempts

                send_attempts += 1
                if send_successful:
                    logger.debug("Send already successful, skipping duplicate operation")
                    return True

                if send_attempts > max_send_attempts:
                    logger.warning("Maximum send attempts reached, preventing consecutive sends")
                    return True

                send_button = self._find_send_button()
                if send_button:
                    send_button.click()
                    logger.info("✅ Send button clicked successfully")
                    send_successful = True
                    return True
                else:
                    # Enterキーフォールバック
                    input_element = self._find_input_element()
                    input_element.send_keys(Keys.RETURN)
                    logger.info("✅ Used Enter key to send message")
                    send_successful = True
                    return False

            logger.debug("Performing safe send operation...")
            try:
                self.safe_element_operation(send_operation, max_retries=2, retry_delay=0.5)
            except StaleElementReferenceException as e:
                if send_successful:
                    logger.info("Send operation completed despite StaleElementReferenceException")
                else:
                    logger.error(f"Send operation failed with StaleElementReferenceException: {e}")
                    raise RuntimeError(f"送信操作中にStaleElementReferenceExceptionが発生しました: {e}")

            # 送信成功の確認
            if send_successful:
                logger.info("✅ Message sending completed successfully")
            else:
                logger.warning("⚠️ Send operation completed but success flag not set")

            time.sleep(1)  # 送信処理待機

            # 応答待機処理（既存のロジックを維持）
            logger.info("Waiting for ChatGPT response to start...")

            class ResponseStarted:
                def __init__(self, driver_instance):
                    self.driver_instance = driver_instance

                def __call__(self, driver):
                    return self.driver_instance._check_response_started()

            response_started = False

            # 段階的待機戦略
            wait_phases = [
                (3, "Quick response detection"),
                (7, "Standard response detection"),
                (15, "Extended response detection")
            ]

            driver = self.selenium_wrapper.driver
            for timeout_seconds, phase_description in wait_phases:
                logger.debug(f"{phase_description} - waiting up to {timeout_seconds} seconds")
                try:
                    response_started = WebDriverWait(driver, timeout_seconds).until(
                        ResponseStarted(self)
                    )
                    if response_started:
                        logger.info(f"Response detected in {phase_description} phase")
                        break
                except TimeoutException:
                    logger.debug(f"{phase_description} phase timed out, trying next phase")
                    continue

            if not response_started:
                ui_state = self._analyze_ui_state()
                error_message = "Response timeout after all detection phases (3s+7s+15s=25s total)."
                error_message += f" UI State Analysis: {ui_state}"
                logger.error(error_message)
                raise RuntimeError(f"ChatGPTの応答開始が25秒以内に検出されませんでした。{error_message}")

            logger.info("Response started successfully, waiting for completion...")

            # ChatGPTの最新レスポンスを取得（既存のロジックを維持）
            response_selectors = [
                "[data-message-author-role='assistant']:last-child div[class*='markdown']",
                "[data-message-author-role='assistant']:last-child div.prose",
                "[data-message-author-role='assistant']:last-child",
                ".result-streaming",
                "[class*='streaming']",
                "[class*='generating']",
                "div[class*='prose']",
                "div[class*='markdown']",
            ]

            response_element = None
            response_text = ""

            # 応答完了まで待機（既存のロジックを維持）
            max_response_wait = 600
            response_start_time = time.time()
            last_text_update = response_start_time
            last_stop_button_check = response_start_time

            logger.info("Starting stop-button monitoring for response completion...")

            while time.time() - response_start_time < max_response_wait:
                # 各セレクターで応答要素を探す
                for selector in response_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            candidate_element = elements[-1]
                            if candidate_element and candidate_element.is_displayed():
                                current_text = candidate_element.text.strip()
                                if current_text:
                                    response_element = candidate_element
                                    if current_text != response_text:
                                        response_text = current_text
                                        last_text_update = time.time()
                                        logger.debug(f"Updated response text ({len(current_text)} chars)")
                                    logger.debug(f"Found response with selector: {selector}")
                                    break
                    except (StaleElementReferenceException, NoSuchElementException):
                        continue

                # stop-button監視
                current_time = time.time()
                if current_time - last_stop_button_check >= 1.0:
                    try:
                        stop_buttons = driver.find_elements(By.CSS_SELECTOR, '[data-testid="stop-button"]')
                        if stop_buttons:
                            active_stop_button = False
                            for button in stop_buttons:
                                if button.is_displayed() and button.is_enabled():
                                    active_stop_button = True
                                    break

                            if active_stop_button:
                                logger.debug("Stop button detected - response still in progress")
                                last_stop_button_check = current_time
                                time.sleep(0.5)
                                continue
                            else:
                                logger.debug("Stop button exists but not active")
                        else:
                            logger.debug("No stop button found - checking response completion")

                        last_stop_button_check = current_time
                    except Exception as e:
                        logger.debug(f"Error checking stop button: {e}")

                if response_element:
                    # 応答が完了しているかチェック
                    def check_completion():
                        return self._is_response_complete(response_element, response_text)

                    try:
                        if self.safe_element_operation(check_completion, max_retries=2, retry_delay=0.5):
                            logger.info("Response completion detected, applying additional delay...")
                            time.sleep(1.5)
                            logger.info("Response completed with additional delay")
                            break
                    except StaleElementReferenceException:
                        response_element = None
                        continue

                    # テキストが更新されていない時間をチェック
                    text_idle_time = time.time() - last_text_update
                    if text_idle_time > 15:
                        logger.warning(f"No text updates for {text_idle_time:.1f}s, checking if complete")
                        try:
                            if self.safe_element_operation(check_completion, max_retries=2, retry_delay=0.5):
                                logger.info("Response appears complete (no recent updates), applying additional delay...")
                                time.sleep(1.5)
                                logger.info("Response completed after idle period")
                                break
                        except StaleElementReferenceException:
                            response_element = None
                            continue

                    # まだ進行中の場合、新しいテキストがあるかチェック
                    def get_current_text():
                        return response_element.text.strip() if response_element else ""

                    try:
                        new_text = self.safe_element_operation(get_current_text, max_retries=2, retry_delay=0.5)
                        if new_text != response_text and len(new_text) > len(response_text):
                            response_text = new_text
                            last_text_update = time.time()
                            logger.debug(f"Response text updated: {len(response_text)} chars")
                    except StaleElementReferenceException:
                        response_element = None
                        continue

                # 短い間隔で再チェック
                time.sleep(0.5)

            if response_element and response_text:
                logger.info(f"Got response: {response_text[:100]}...")
                return response_text

            # レスポンスが見つからない場合
            if not self._check_login_status():
                logger.error("Login session expired during message processing")
                raise RuntimeError("ChatGPTのログインセッションが期限切れです。再ログインしてからAPIを使用してください。")

            logger.error("Could not find ChatGPT response element")
            raise RuntimeError("ChatGPTからの応答が見つかりません。ログイン状態を確認するか、ページが正しく読み込まれているかを確認してください。")

        except Exception as e:
            error_details = self._collect_exception_details(e)
            logger.error(f"Error sending message: {error_details['message']}")
            logger.debug(f"Exception details: {error_details['full_info']}")

            if "ログイン" in str(e):
                raise RuntimeError(str(e))
            else:
                raise RuntimeError(f"メッセージ送信中にエラーが発生しました: {error_details['message']}")
    
    def _enhanced_cleanup(self, input_element) -> str:
        """段階的クリーンアップ処理（最適化版）"""
        try:
            # 段階1: 標準クリーンアップ
            input_element.clear()
            time.sleep(settings.input_cleanup_delay if hasattr(settings, 'input_cleanup_delay') else 0.8)
            
            # 段階2: 残存データ検出
            current_text = input_element.get_attribute('value') or input_element.text
            residual_data = current_text.strip() if current_text else ""
            
            if residual_data:
                logger.warning(f"Residual data detected: '{residual_data}' - performing enhanced cleanup")
                
                # 段階3: 強制クリーンアップ（キーボードコンビネーション）
                input_element.send_keys(Keys.CONTROL + "a")  # 全選択
                time.sleep(0.1)
                input_element.send_keys(Keys.DELETE)         # 削除
                time.sleep(0.3)
                
                return residual_data
            
            return ""
            
        except Exception as e:
            logger.error(f"Enhanced cleanup failed: {e}")
            return ""
    
    def _select_send_strategy(self, message_length: int) -> str:
        """送信戦略選択（科学的根拠に基づく）"""
        safe_limit = getattr(settings, 'safe_send_limit', 150)
        
        if message_length <= safe_limit:
            return "safe_single"
        elif message_length <= 4000:
            return "try_single_fallback_chunk"
        else:
            return "smart_chunking"
    
    def _execute_send_strategy(self, input_element, message: str, strategy: str):
        """選択された送信戦略の実行"""
        try:
            if strategy == "safe_single":
                # 短いメッセージは確実に単一送信
                input_element.send_keys(message)
                logger.debug(f"Executed safe_single strategy: {len(message)} chars")
            
            elif strategy == "try_single_fallback_chunk":
                # 単一送信試行、失敗時はチャンキング
                try:
                    input_element.send_keys(message)
                    logger.debug(f"Executed try_single strategy successfully: {len(message)} chars")
                except Exception as e:
                    logger.warning(f"Single send failed: {e}, falling back to chunking")
                    self._send_message_with_smart_chunking(input_element, message)
            
            elif strategy == "smart_chunking":
                # 長いメッセージはスマート分割
                self._send_message_with_smart_chunking(input_element, message)
                logger.debug(f"Executed smart_chunking strategy: {len(message)} chars")
            
            else:
                # デフォルトフォールバック
                logger.warning(f"Unknown strategy '{strategy}', using default")
                input_element.send_keys(message)
                
        except Exception as e:
            logger.error(f"Strategy execution failed: {e}")
            raise RuntimeError(f"送信戦略の実行に失敗しました: {e}")

    def _send_message_with_chunking(self, input_element, message: str):
        """
        長いメッセージを適切に送信（システムメッセージ分離防止対応版）

        Args:
            input_element: テキスト入力要素
            message (str): 送信するメッセージ
        """
        max_chunk_size = 4000  # 一度に送信する最大文字数

        if len(message) <= max_chunk_size:
            # 短いメッセージは通常通り送信（単一操作）
            input_element.send_keys(message)
            logger.debug(f"Sent message directly: {len(message)} chars")
        else:
            # 長いメッセージでも分割送信を避けてシステムメッセージ分離を防ぐ
            logger.warning(f"Message very long ({len(message)} chars), attempting single send to avoid system message separation")

            # システムメッセージ分離防止：長いメッセージでも一括送信を試行
            try:
                input_element.send_keys(message)
                logger.info(f"Successfully sent long message as single unit: {len(message)} chars")
            except Exception as e:
                logger.error(f"Failed to send long message as single unit: {e}")
                # フォールバック：分割が必要な場合のみ、改行位置での分割を試行
                logger.info("Attempting smart chunking with line-break boundaries...")
                self._send_message_with_smart_chunking(input_element, message)

    def _send_message_with_smart_chunking(self, input_element, message: str):
        """
        スマート分割送信（改行位置での分割によりシステムメッセージ分離を最小化）

        Args:
            input_element: テキスト入力要素
            message (str): 送信するメッセージ
        """
        max_chunk_size = 3500  # より安全なサイズに縮小

        # 改行位置での分割を優先
        paragraphs = message.split('\n\n')
        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            if len(current_chunk + paragraph) <= max_chunk_size:
                if current_chunk:
                    current_chunk += '\n\n' + paragraph
                else:
                    current_chunk = paragraph
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = paragraph

                # パラグラフ自体が長い場合は文レベルで分割
                if len(current_chunk) > max_chunk_size:
                    sentences = current_chunk.split('. ')
                    chunks.extend(self._split_sentences(sentences, max_chunk_size))
                    current_chunk = ""

        if current_chunk:
            chunks.append(current_chunk)

        # 分割送信実行（システムメッセージ分離警告付き）
        logger.warning(f"Smart chunking required: {len(chunks)} chunks. This may cause system message separation.")

        for i, chunk in enumerate(chunks):
            input_element.send_keys(chunk)
            logger.debug(f"Sent smart chunk {i+1}/{len(chunks)}: {len(chunk)} chars")

            # チャンク間の適切な待機（Stop button監視）
            if i < len(chunks) - 1:  # 最後のチャンク以外
                logger.info("Waiting for stop button to disappear before sending next chunk...")
                self._wait_for_stop_button_disappear()
                time.sleep(1.0)  # 追加の安全待機

    def _contains_system_message(self, message: str) -> bool:
        """メッセージにシステムメッセージが含まれているかチェック"""
        system_indicators = [
            "Respond to the human as helpfully and accurately as possible",
            "You are a helpful assistant",
            "As an AI assistant",
            "Please respond to this user request:"
        ]

        return any(indicator in message for indicator in system_indicators)

    def _send_message_safely(self, input_element, message: str):
        """システムメッセージ分離を防ぐ安全なメッセージ送信"""
        if self._contains_system_message(message):
            logger.warning("Message contains system prompt - using extra caution to prevent separation")

            # システムメッセージを含む場合は分割を極力避ける
            if len(message) > 8000:  # 非常に長い場合のみ警告
                logger.error(f"Message with system prompt is very long ({len(message)} chars) - high risk of separation")

            # 一括送信を強制試行
            try:
                input_element.send_keys(message)
                logger.info("Successfully sent system message as single unit")
            except Exception as e:
                logger.error(f"Failed to send system message as single unit: {e}")
                raise RuntimeError("システムメッセージの分離を防ぐため、メッセージ送信を中止しました。メッセージを短縮してください。")
        else:
            # 通常のメッセージは既存の処理
            self._send_message_with_chunking(input_element, message)

    def _split_sentences(self, sentences: List[str], max_size: int) -> List[str]:
        """文レベルでの分割"""
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk + sentence) <= max_size:
                if current_chunk:
                    current_chunk += '. ' + sentence
                else:
                    current_chunk = sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _wait_for_stop_button_disappear(self):
        """Stop buttonが消えるまで待機（チャンク間の安全な待機）"""
        try:
            driver = self.selenium_wrapper.driver

            # Stop buttonが存在し、かつ表示されている間は待機
            wait = WebDriverWait(driver, 30)  # 最大30秒待機

            # Stop buttonが見つからないか、非表示になるまで待機
            def stop_button_gone(driver):
                try:
                    stop_buttons = driver.find_elements(By.CSS_SELECTOR, '[data-testid="stop-button"]')
                    if not stop_buttons:
                        return True

                    for button in stop_buttons:
                        if button.is_displayed() and button.is_enabled():
                            return False
                    return True
                except:
                    return True

            wait.until(stop_button_gone)
            logger.info("Stop button disappeared - ready for next chunk")

        except Exception as e:
            logger.warning(f"Error waiting for stop button: {e}, proceeding anyway")

    def _collect_exception_details(self, exception: Exception) -> dict:
        """
        例外の詳細情報を収集する（空のメッセージ問題対策）

        Args:
            exception: 発生した例外

        Returns:
            dict: 例外の詳細情報
        """
        try:
            # 基本的な例外情報
            exception_type = type(exception).__name__
            exception_message = str(exception).strip()

            # Selenium特有の例外情報を収集（TimeoutException処理前に実行）
            selenium_details = {}

            # WebDriverException系の詳細情報
            if hasattr(exception, 'msg'):
                selenium_details['selenium_msg'] = str(getattr(exception, 'msg', '')).strip()
            if hasattr(exception, 'screen'):
                selenium_details['has_screenshot'] = getattr(exception, 'screen', None) is not None
            if hasattr(exception, 'stacktrace'):
                selenium_details['has_stacktrace'] = getattr(exception, 'stacktrace', None) is not None

            # InvalidSessionIdException用
            if hasattr(exception, 'session_id'):
                selenium_details['session_id'] = getattr(exception, 'session_id', 'unknown')

            # TimeoutException特有の処理（Expected Conditions対応版）
            if exception_type == 'TimeoutException':
                # TimeoutExceptionの場合、より詳細な情報を生成
                if not exception_message or exception_message in ['Message:', 'Message', '']:
                    exception_message = f"TimeoutException: WebDriverWait operation timed out"

                    # Selenium詳細属性から情報を抽出
                    if selenium_details.get('selenium_msg'):
                        exception_message += f" - Selenium msg: {selenium_details['selenium_msg']}"

                    # スタックトレースから詳細を抽出
                    import traceback
                    stack_info = traceback.format_exc()
                    if "until" in stack_info:
                        if "ResponseStarted" in stack_info:
                            exception_message += " during ResponseStarted condition check"
                        elif "lambda" in stack_info:
                            exception_message += " during lambda condition check"
                        else:
                            exception_message += " during condition check"
                    if "_check_response_started" in stack_info:
                        exception_message += " while waiting for ChatGPT response to start"
                else:
                    # 既存のメッセージがある場合は、それを使用
                    if exception_message not in ['Message:', 'Message']:
                        exception_message = f"TimeoutException: {exception_message}"
                    else:
                        # 'Message:'の場合は置換
                        exception_message = f"TimeoutException: WebDriverWait operation timed out (original message was incomplete: '{exception_message}')"

            # WebDriver状態情報
            webdriver_state = {}
            try:
                if self.selenium_wrapper and self.selenium_wrapper.driver:
                    driver = self.selenium_wrapper.driver
                    webdriver_state['current_url'] = driver.current_url
                    webdriver_state['session_id'] = getattr(driver, 'session_id', 'unknown')
                    webdriver_state['title'] = driver.title[:100]  # 最初の100文字のみ
            except Exception as state_error:
                webdriver_state['state_collection_error'] = str(state_error)

            # 空のメッセージまたは不完全なメッセージの場合の代替情報生成
            if not exception_message or exception_message in ['Message:', 'Message', '']:
                if exception_type:
                    exception_message = f"Empty or incomplete message from {exception_type}"
                else:
                    exception_message = "Unknown exception with empty or incomplete message"

                # Seleniumの詳細情報があれば追加
                if selenium_details.get('selenium_msg'):
                    exception_message += f" (Selenium: {selenium_details['selenium_msg']})"

            # 完全な情報の構築
            full_info = {
                'type': exception_type,
                'original_message': str(exception),
                'selenium_details': selenium_details,
                'webdriver_state': webdriver_state,
                'timestamp': time.time()
            }

            return {
                'message': exception_message,
                'full_info': full_info
            }

        except Exception as detail_error:
            # 例外詳細の収集自体でエラーが発生した場合
            return {
                'message': f"Exception detail collection failed: {str(detail_error)}",
                'full_info': {
                    'original_exception': str(exception),
                    'detail_collection_error': str(detail_error)
                }
            }

    def _is_response_complete(self, response_element, response_text: str) -> bool:
        """
        ChatGPTの応答が完了しているかを判定（stop-button監視強化版）

        Args:
            response_element: レスポンス要素
            response_text: 現在のレスポンステキスト

        Returns:
            bool: 応答が完了している場合True
        """
        try:
            driver = self.selenium_wrapper.driver

            # 1. 最優先: stop-button (data-testid="stop-button") の監視
            try:
                stop_buttons = driver.find_elements(By.CSS_SELECTOR, '[data-testid="stop-button"]')
                if stop_buttons:
                    # stop-buttonが存在する場合は処理中
                    for button in stop_buttons:
                        if button.is_displayed() and button.is_enabled():
                            logger.debug("Stop button is still visible, response in progress")
                            return False
            except Exception as e:
                logger.debug(f"Error checking stop button: {e}")

            # 2. 補助的なストリーミング完了の視覚的手がかりをチェック
            try:
                # ストリーミング終了を示すインジケーターを探す
                streaming_indicators = [
                    ".result-streaming",
                    "[class*='streaming']",
                    "[class*='generating']",
                    ".cursor-blink",
                    "[aria-busy='true']"
                ]

                is_still_streaming = False
                for indicator in streaming_indicators:
                    elements = driver.find_elements(By.CSS_SELECTOR, indicator)
                    if elements and any(el.is_displayed() for el in elements):
                        is_still_streaming = True
                        logger.debug(f"Found active streaming indicator: {indicator}")
                        break

                if is_still_streaming:
                    logger.debug("Still streaming based on visual indicators")
                    return False

            except Exception as e:
                logger.debug(f"Error checking streaming indicators: {e}")

            # 3. 短時間待機してテキストの変化を確認
            initial_text = response_text
            initial_length = len(initial_text)

            # 2秒間待機してテキストの変化を監視
            monitoring_duration = 2.0
            check_interval = 0.5
            stability_checks = int(monitoring_duration / check_interval)
            stable_count = 0

            for i in range(stability_checks):
                time.sleep(check_interval)
                try:
                    # 要素を再取得（stale element対策）
                    current_text = response_element.text.strip()
                    current_length = len(current_text)

                    # テキストが変化していない場合
                    if current_text == initial_text and current_length == initial_length:
                        stable_count += 1
                    else:
                        # テキストが変化した場合、初期値を更新
                        initial_text = current_text
                        initial_length = current_length
                        stable_count = 0
                        logger.debug(f"Text changed during stability check: {current_length} chars")

                except StaleElementReferenceException:
                    # 要素が無効になった場合は完了と判定
                    logger.debug("Element became stale, considering response complete")
                    return True
                except Exception as e:
                    logger.debug(f"Error checking response stability: {e}")
                    stable_count += 1

            # 4. 最小文字数チェック（極端に短い応答の場合は継続）
            # ただし、明確に完了した短い応答もあるため慎重に判定
            if len(initial_text) < 20:  # 20文字未満は部分応答の可能性が高い
                logger.debug("Response too short, continuing to wait")
                return False

            # 5. テキストの安定性による判定
            # 連続してテキストが安定している場合は完了と判定
            stability_threshold = stability_checks * 0.7  # 70%以上安定していれば完了
            if stable_count >= stability_threshold:
                logger.debug(f"Response stable for {stable_count}/{stability_checks} checks, considering complete")
                return True

            # 6. デフォルトは継続
            logger.debug(f"Response not definitively complete (stable: {stable_count}/{stability_checks})")
            return False

        except Exception as e:
            logger.debug(f"Error in response completion check: {e}")
            # エラーの場合は継続して待機（安全側）
            return False

    def _check_response_started(self) -> bool:
        """
        レスポンスが開始されたかを多角的にチェック（改良版）

        ChatGPTのUI変更に対応できるよう、複数の検出方法を組み合わせて使用

        Returns:
            bool: レスポンスが開始されている場合True
        """
        try:
            driver = self.selenium_wrapper.driver

            # 1. ページ全体の状態確認（ロード状態）
            if driver.execute_script("return document.readyState") != "complete":
                logger.debug("Page not fully loaded yet")
                return False

            # 2. 複数段階での応答検出
            detection_methods = []

            # 方法1: AssistantメッセージのDOMチェック（最も確実）
            try:
                # より包括的なassistantメッセージセレクタ
                assistant_selectors = [
                    "[data-message-author-role='assistant']",
                    "[data-role='assistant']",
                    ".message[data-author='assistant']",
                    "[data-testid*='assistant']",
                    "[role='assistant']"
                ]

                for selector in assistant_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        # 最新の要素をチェック
                        latest = elements[-1]
                        if latest.is_displayed():
                            # テキストがあるかチェック（空でも可、DOM存在が重要）
                            detection_methods.append(f"assistant_element_{selector}")
                            break
            except Exception as e:
                logger.debug(f"Assistant element detection failed: {e}")

            # 方法2: ストリーミング・生成中インジケータ
            try:
                streaming_selectors = [
                    "[class*='streaming']",
                    "[class*='generating']",
                    "[class*='typing']",
                    "[aria-live='polite']",
                    ".result-streaming",
                    ".cursor-blink",
                    "[data-testid*='streaming']",
                    "[aria-busy='true']"
                ]

                for selector in streaming_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and any(el.is_displayed() for el in elements):
                        detection_methods.append(f"streaming_indicator_{selector}")
                        break
            except Exception as e:
                logger.debug(f"Streaming indicator detection failed: {e}")

            # 方法3: テキストコンテンツの変化検出
            try:
                # メッセージコンテナの変化を検出
                content_selectors = [
                    "div[class*='prose']",
                    "div[class*='markdown']",
                    ".message-content",
                    "[data-testid='conversation-turn']",
                    ".conversation-item",
                    "[role='presentation'] div"
                ]

                for selector in content_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        # 最後の要素でテキストコンテンツをチェック
                        latest = elements[-1]
                        if latest.is_displayed() and latest.text.strip():
                            detection_methods.append(f"content_change_{selector}")
                            break
            except Exception as e:
                logger.debug(f"Content change detection failed: {e}")

            # 方法4: UI状態変化の検出
            try:
                # 送信ボタンの状態変化（無効化されている＝処理中）
                send_button_selectors = [
                    "button[data-testid='send-button']",
                    "button[aria-label*='Send']",
                    "button[title*='Send']"
                ]

                for selector in send_button_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        button = elements[0]
                        if button.is_displayed() and not button.is_enabled():
                            detection_methods.append(f"send_button_disabled_{selector}")
                            break
            except Exception as e:
                logger.debug(f"UI state detection failed: {e}")

            # 方法5: 停止ボタンの検出（応答中の強い指標）
            try:
                stop_selectors = [
                    "button[aria-label*='Stop']",
                    "button[title*='Stop']",
                    "button[aria-label*='停止']",
                    "button[title*='停止']",
                    "[data-testid*='stop']"
                ]

                for selector in stop_selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements and any(el.is_displayed() and el.is_enabled() for el in elements):
                        detection_methods.append(f"stop_button_{selector}")
                        break
            except Exception as e:
                logger.debug(f"Stop button detection failed: {e}")

            # 方法6: JavaScript経由でのページ状態確認
            try:
                # ページ内のJavaScript変数やイベント状態をチェック
                js_checks = [
                    "document.querySelector('[data-message-author-role=\"assistant\"]') !== null",
                    "document.querySelector('[class*=\"streaming\"]') !== null",
                    "document.querySelector('[aria-busy=\"true\"]') !== null"
                ]

                for i, js_check in enumerate(js_checks):
                    if driver.execute_script(f"return {js_check}"):
                        detection_methods.append(f"js_check_{i}")
                        break
            except Exception as e:
                logger.debug(f"JavaScript detection failed: {e}")

            # 検出結果の評価
            if detection_methods:
                logger.debug(f"Response started detected via: {', '.join(detection_methods)}")
                return True

            # 追加チェック: DOM変更の検出（最終手段）
            try:
                # ページ内の動的変更を検出
                mutation_check = """
                return new Promise((resolve) => {
                    const observer = new MutationObserver((mutations) => {
                        for (let mutation of mutations) {
                            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                                for (let node of mutation.addedNodes) {
                                    if (node.nodeType === 1 && (
                                        node.getAttribute('data-message-author-role') === 'assistant' ||
                                        node.className.includes('streaming') ||
                                        node.className.includes('generating')
                                    )) {
                                        observer.disconnect();
                                        resolve(true);
                                        return;
                                    }
                                }
                            }
                        }
                    });
                    observer.observe(document.body, { childList: true, subtree: true });
                    setTimeout(() => {
                        observer.disconnect();
                        resolve(false);
                    }, 1000);
                });
                """

                # 1秒間DOM変更を監視
                dom_change_detected = driver.execute_async_script(mutation_check)
                if dom_change_detected:
                    logger.debug("Response started detected via DOM mutation")
                    return True

            except Exception as e:
                logger.debug(f"DOM mutation detection failed: {e}")

            logger.debug("No response start indicators found")
            return False

        except Exception as e:
            logger.debug(f"Error in comprehensive response start check: {e}")
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

    def _analyze_ui_state(self):
        """
        ChatGPT UIの現在状態を分析してデバッグ情報を提供

        Returns:
            dict: UI状態の詳細情報
        """
        try:
            driver = self.driver
            state_info = {
                'page_loaded': False,
                'input_available': False,
                'send_button_state': 'not_found',
                'response_area_state': 'not_found',
                'login_state': 'unknown',
                'streaming_indicators': [],
                'error_messages': []
            }

            # ページの基本読み込み状態
            try:
                state_info['page_loaded'] = driver.execute_script("return document.readyState") == "complete"
                state_info['current_url'] = driver.current_url
            except Exception:
                state_info['page_loaded'] = False

            # 入力エリアの状態
            input_selectors = [
                "textarea[placeholder*='ChatGPT']",
                "textarea[data-id*='root']",
                "#prompt-textarea",
                "div[contenteditable='true']"
            ]

            for selector in input_selectors:
                try:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                    if element and element.is_displayed():
                        state_info['input_available'] = True
                        state_info['input_selector'] = selector
                        break
                except Exception:
                    continue

            # 送信ボタンの状態
            send_selectors = [
                "button[data-testid='send-button']",
                "button:has(svg[data-icon='paper-plane'])",
                "button[aria-label*='Send']"
            ]

            for selector in send_selectors:
                try:
                    button = driver.find_element(By.CSS_SELECTOR, selector)
                    if button:
                        if button.is_enabled():
                            state_info['send_button_state'] = 'enabled'
                        else:
                            state_info['send_button_state'] = 'disabled'
                        state_info['send_button_selector'] = selector
                        break
                except Exception:
                    continue

            # 応答エリアの状態
            response_indicators = [
                ".result-streaming",
                "[class*='streaming']",
                "[class*='generating']",
                "[data-message-author-role='assistant']"
            ]

            for selector in response_indicators:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        state_info['streaming_indicators'].append({
                            'selector': selector,
                            'count': len(elements),
                            'visible': any(el.is_displayed() for el in elements)
                        })
                except Exception:
                    continue

            # ログイン状態（基本チェック）
            try:
                state_info['login_state'] = 'logged_in' if self._check_login_status() else 'logged_out'
            except Exception:
                state_info['login_state'] = 'check_failed'

            # エラーメッセージの検出
            error_selectors = [
                "[class*='error']",
                "[class*='warning']",
                ".alert",
                "[role='alert']"
            ]

            for selector in error_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        if element.is_displayed() and element.text.strip():
                            state_info['error_messages'].append({
                                'selector': selector,
                                'text': element.text.strip()[:100]
                            })
                except Exception:
                    continue

            return state_info

        except Exception as e:
            return {'analysis_failed': str(e)}

    def safe_element_operation(self, operation, max_retries=3, retry_delay=1.0):
        """
        要素操作を安全に実行し、StaleElementReferenceExceptionに対応（カスタマイズ可能リトライ回数）
        ※連続送信防止: 送信操作では max_retries=1-2 を推奨

        Args:
            operation: 実行する操作（関数）
            max_retries (int): 最大リトライ回数（デフォルト3）
            retry_delay (float): リトライ間隔（秒、デフォルト1.0秒）

        Returns:
            操作関数の戻り値

        Raises:
            最後のリトライで失敗した場合の例外
        """
        last_exception = None

        for attempt in range(max_retries + 1):  # max_retries + 1回試行
            try:
                result = operation()
                if attempt > 0:
                    logger.debug(f"Operation succeeded on attempt {attempt + 1}")
                return result
            except StaleElementReferenceException as e:
                last_exception = e
                if attempt < max_retries:
                    logger.debug(f"StaleElementReferenceException on attempt {attempt + 1}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
                else:
                    logger.warning(f"StaleElementReferenceException after {max_retries + 1} attempts")
                    break
            except Exception as e:
                # StaleElementReferenceException以外の例外は即座に再発生
                logger.error(f"Non-recoverable exception in safe_element_operation: {e}")
                raise

        # 最大リトライ回数を超えた場合
        logger.error(f"Operation failed after {max_retries + 1} attempts")
        raise last_exception

    def _find_input_element(self):
        """ChatGPTの入力欄要素を検索する（DOM調査結果に基づく優先セレクター）"""
        if not self.selenium_wrapper or not self.selenium_wrapper.driver:
            print("❌ ERROR: SeleniumWrapperまたはDriverが初期化されていません")
            return None

        driver = self.selenium_wrapper.driver

        # DOM調査結果に基づく優先順位付きセレクター（2025-09-09 調査結果）
        input_selectors = [
            "#prompt-textarea",                              # 最優先 - DOM調査で確認済み
            "div[contenteditable='true']",                   # セカンダリ - DOM調査で確認済み
            "textarea[name='prompt-textarea']",              # フォールバック（隠されたフォーム要素）
            "[data-testid*='composer'] [contenteditable='true']",  # 将来のUI変更対応
            "[role='textbox'][contenteditable='true']",      # ARIA対応（contenteditable付き）
            "[role='textbox']",                              # ARIA対応（汎用）
            "textarea[placeholder*='質問']",                 # 日本語プレースホルダー対応
            "textarea[placeholder*='Message']"               # 英語プレースホルダー対応
        ]

        print(f"🔍 ChatGPT入力欄を検索中... ({len(input_selectors)}個のセレクターをテスト)")

        for i, selector in enumerate(input_selectors, 1):
            try:
                print(f"  セレクター {i}/{len(input_selectors)}: {selector}")
                elements = driver.find_elements(By.CSS_SELECTOR, selector)

                if elements:
                    element = elements[0]
                    # 要素の有効性確認
                    if element.is_displayed() and element.is_enabled():
                        print(f"  ✅ 有効な入力欄を発見: {element.tag_name}")
                        print(f"     要素数: {len(elements)}, 表示: {element.is_displayed()}, 有効: {element.is_enabled()}")

                        # デバッグ情報の追加
                        element_id = element.get_attribute('id')
                        element_class = element.get_attribute('class')
                        element_placeholder = element.get_attribute('placeholder')
                        if element_id:
                            print(f"     ID: {element_id}")
                        if element_class:
                            print(f"     Class: {element_class[:100]}...")
                        if element_placeholder:
                            print(f"     Placeholder: {element_placeholder}")

                        return element
                    else:
                        print(f"  ⚠️  要素は存在するが使用不可: 表示={element.is_displayed()}, 有効={element.is_enabled()}")
                else:
                    print(f"  ❌ 要素が見つかりません")
            except Exception as e:
                print(f"  ❌ セレクターエラー: {str(e)}")

        # 全セレクターで見つからなかった場合の詳細情報
        print("❌ ERROR: ChatGPTの入力欄が見つかりません。ページが正しく読み込まれているかを確認してください")

        # 現在のページ状態の診断情報
        try:
            current_url = driver.current_url
            page_title = driver.title
            print(f"📊 診断情報:")
            print(f"   現在のURL: {current_url}")
            print(f"   ページタイトル: {page_title}")

            # ログインページの場合の特別メッセージ
            if "auth.openai.com" in current_url or "login" in current_url.lower():
                print("💡 ヒント: 現在ログインページにいます。ChatGPTにログインしてからもう一度お試しください")
            elif "chatgpt.com" not in current_url:
                print("💡 ヒント: ChatGPTページ以外にいます。正しいページに移動してください")
            else:
                print("💡 ヒント: ページが完全に読み込まれるまでしばらく待ってから再試行してください")

        except Exception as e:
            print(f"   診断情報取得エラー: {str(e)}")

        return None

    def _is_chatgpt_ready_for_input(self) -> bool:
        """
        ChatGPTが新しい入力を受付可能な状態かを判定（DOM構造調査結果反映版）

        检証項目:
        1. Stop buttonが非アクティブ（応答完了）
        2. 入力欄が存在し有効化されている
        3. ローディング・生成インジケーターが非表示
        4. 送信ボタンが有効化されている

        Returns:
            bool: 入力可能な場合True
        """
        try:
            driver = self.selenium_wrapper.driver

            # 1. Stop buttonが非アクティブ（応答完了）であることを確認
            stop_buttons = driver.find_elements(By.CSS_SELECTOR, '[data-testid="stop-button"]')
            for button in stop_buttons:
                if button.is_displayed() and button.is_enabled():
                    logger.debug("Stop button is active - ChatGPT still processing")
                    return False

            # 2. 入力欄が存在し、有効化されていることを確認（DOM調査結果反映）
            input_selectors = [
                "#prompt-textarea",  # 最優先: DOM調査で確認済み
                "div[contenteditable='true']",  # セカンダリ
                "textarea[name='prompt-textarea']",  # フォールバック
            ]

            input_available = False
            for selector in input_selectors:
                try:
                    input_element = driver.find_element(By.CSS_SELECTOR, selector)
                    if input_element and input_element.is_displayed() and input_element.is_enabled():
                        input_available = True
                        logger.debug(f"Input element ready: {selector}")
                        break
                except NoSuchElementException:
                    continue

            if not input_available:
                logger.debug("Input element not available or disabled")
                return False

            # 3. ローディング・生成中インジケーターが非表示であることを確認
            loading_indicators = [
                "[class*='streaming']",
                "[class*='generating']",
                "[class*='typing']",
                "[aria-busy='true']",
                ".result-streaming",
                ".cursor-blink"
            ]

            for indicator in loading_indicators:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, indicator)
                    if elements and any(el.is_displayed() for el in elements):
                        logger.debug(f"Found active loading indicator: {indicator}")
                        return False
                except Exception:
                    continue

            # 4. 送信ボタンが有効化されていることを確認（生成完了の指標）
            send_button_selectors = [
                "button[data-testid='send-button']",
                "button[aria-label*='Send']",
                "button[title*='Send']"
            ]

            send_button_enabled = False
            for selector in send_button_selectors:
                try:
                    button = driver.find_element(By.CSS_SELECTOR, selector)
                    if button and button.is_displayed() and button.is_enabled():
                        send_button_enabled = True
                        logger.debug(f"Send button ready: {selector}")
                        break
                except Exception:
                    continue

            # 全ての条件を満たす場合のみ入力可能と判定
            is_ready = input_available and send_button_enabled
            if is_ready:
                logger.debug("ChatGPT is ready for input - all checks passed")
            else:
                logger.debug(f"ChatGPT not ready - input_available: {input_available}, send_button_enabled: {send_button_enabled}")

            return is_ready

        except Exception as e:
            logger.debug(f"Error checking ChatGPT ready state: {e}")
            return False

    def _find_send_button(self):
        """
        送信ボタンを取得（常に最新要素を取得）

        Returns:
            WebElement or None: 送信ボタン（見つからない場合はNone）
        """
        driver = self.selenium_wrapper.driver

        send_selectors = [
            "button[data-testid='send-button']",
            "button:has(svg[data-icon='paper-plane'])",
            "button:has(svg[class*='send'])",
            "button[aria-label*='Send']",
            "button[title*='Send']",
            "div[role='button']:has(svg)",
            ".btn-primary"
        ]

        for selector in send_selectors:
            try:
                send_button = driver.find_element(By.CSS_SELECTOR, selector)
                if send_button and send_button.is_enabled():
                    logger.debug(f"Found send button with selector: {selector}")
                    return send_button
            except NoSuchElementException:
                continue

        logger.debug("Send button not found, will use Enter key instead")
        return None
