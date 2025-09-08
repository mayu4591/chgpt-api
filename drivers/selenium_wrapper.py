"""
SeleniumWrapper - Chrome外部起動型WebDriverラッパー

This module provides a singleton wrapper for Selenium WebDriver with external Chrome process management.
外部Chrome起動とWebDriver接続を分離し、プロセス管理とウィンドウ制御を提供します。
"""

import os
import socket
import threading
import time
import tempfile
import random
import shutil
import subprocess
import psutil
import win32gui
import win32con
import win32process
from typing import Optional

from selenium import webdriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver import Remote

DEFAULT_CHROME_PATH = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


class SeleniumWrapper:
    """Chrome外部起動型WebDriverラッパークラス

    Singletonパターンで実装され、Chrome外部プロセス管理とWebDriver接続を提供します。
    プロセス再利用、ウィンドウ透明化、適切なクリーンアップが可能です。
    """
    _instance = None  # Singleton instance
    _lock = threading.Lock()  # 排他用ロック

    @classmethod
    def get_instance(cls, url="", chrome_path=DEFAULT_CHROME_PATH, chrome_driver_path="", profile_dir_path="", port=""):
        """Singletonインスタンスを取得"""
        print("SeleniumWrapper get_instance")
        with cls._lock:
            if cls._instance is None:
                print("Creating new instance of SeleniumWrapper")
                cls._instance = cls(url, chrome_path, chrome_driver_path, profile_dir_path, port)
            return cls._instance

    @classmethod
    def close_instance(cls):
        """Singletonインスタンスを終了"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.quit(cls._instance.close_with_chrome)
                cls._instance = None

    def __init__(self, url="", chrome_path="", chrome_driver_path="", profile_dir_path="", port="", close_with_chrome=True):
        """SeleniumWrapper初期化"""
        print("SeleniumWrapper initialized")
        self.url = url
        self.chrome_path = chrome_path or DEFAULT_CHROME_PATH
        self.chrome_driver_path = chrome_driver_path
        self.profile_dir_path = profile_dir_path
        self.port = port
        self.tmp_profile = False
        self.chrome_process = None
        self.driver: Optional[Remote] = None
        self.pid = None  # hwndを取得するためのPIDのキャッシュ
        process_info_dir = profile_dir_path if len(profile_dir_path) > 0 else tempfile.gettempdir()
        self.process_info_file = os.path.join(process_info_dir, "chrome_process_info.txt")
        self.close_with_chrome = close_with_chrome
        self.visible = True

        if self.profile_dir_path == "":
            self.profile_dir_path = tempfile.mkdtemp()
            self.tmp_profile = True
            print("Creating a temporary profile directory at: ", self.profile_dir_path)
        else:
            # 相対パスを絶対パスに変換
            self.profile_dir_path = os.path.abspath(self.profile_dir_path)
            # プロファイルディレクトリの存在確認と作成
            if not os.path.exists(self.profile_dir_path):
                os.makedirs(self.profile_dir_path, exist_ok=True)
                print(f"Created profile directory: {self.profile_dir_path}")

        self.setup(url)

    def __del__(self):
        """デストラクタ - リソースクリーンアップ"""
        self.quit(self.close_with_chrome)
        if self.tmp_profile:
            print("Removing temporary profile directory at: ", self.profile_dir_path)
            shutil.rmtree(self.profile_dir_path, ignore_errors=True)

    def setup(self, url: str):
        """Chrome起動とWebDriver接続のセットアップ"""
        if self.port == "":
            self.port = self.find_available_port()

        # Check if a previous Chrome process exists
        if os.path.exists(self.process_info_file):
            try:
                with open(self.process_info_file, "r") as file:
                    _, port = file.readline().strip().split(",")
                    self.port = port.strip()
                    # Read all lines and extract PIDs
                    pids = [int(line.split(",")[0].strip()) for line in file.readlines()]
                    print(f"Found saved Chrome process PIDs: {pids}")
                # Check if any of the processes exist
                existing_processes = [psutil.Process(pid) for pid in pids if psutil.pid_exists(pid)]
                if existing_processes:
                    print(f"Reusing existing Chrome process with PIDs: {[p.pid for p in existing_processes]}")
                    self.chrome_process = existing_processes[0]  # Use the first valid process
                else:
                    print("No saved Chrome processes are running. Starting a new process.")
                    self.launch_chrome_with_remote_debugging(self.port, url)
            except Exception as e:
                print(f"Failed to reuse existing Chrome process: {e}")
                self.launch_chrome_with_remote_debugging(self.port, url)
        else:
            self.launch_chrome_with_remote_debugging(self.port, url)

        time.sleep(3)  # Chrome起動完了まで待機時間を増加

        # リモートデバッグポートの準備待機
        if not self._wait_for_debug_port(self.port, timeout=15):
            print(f"Warning: Remote debugging port {self.port} not ready, proceeding anyway")

        self.driver = self.setup_webdriver(self.port)

    @staticmethod
    def find_available_port():
        """利用可能なポート番号を取得"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

    def _wait_for_debug_port(self, port: str, timeout: int = 10) -> bool:
        """リモートデバッグポートが利用可能になるまで待機"""
        import socket
        import time

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    result = s.connect_ex(('127.0.0.1', int(port)))
                    if result == 0:
                        print(f"Remote debugging port {port} is ready")
                        return True
            except (socket.error, ValueError):
                pass
            time.sleep(0.5)

        print(f"Remote debugging port {port} not ready after {timeout} seconds")
        return False

    def launch_chrome_with_remote_debugging(self, port: str, url: str):
        """リモートデバッグポート付きでChromeを外部起動"""
        def open_chrome():
            try:
                # 起動前の詳細情報ログ
                print(f"Chrome launch attempt - Port: {port}, URL: {url}")
                print(f"Chrome path: {self.chrome_path}")
                print(f"Profile directory: {self.profile_dir_path}")

                # Chrome実行ファイルの存在確認
                if not os.path.exists(self.chrome_path.strip('"')):
                    raise FileNotFoundError(f"Chrome executable not found: {self.chrome_path}")
                print(f"Chrome executable verified: {self.chrome_path}")

                # プロファイルディレクトリの最終確認と作成
                if not os.path.exists(self.profile_dir_path):
                    os.makedirs(self.profile_dir_path, exist_ok=True)
                    print(f"Created profile directory during Chrome launch: {self.profile_dir_path}")
                else:
                    print(f"Using existing profile directory: {self.profile_dir_path}")

                # コマンドライン引数をリスト形式で構築（スペース含有パス対応）
                chrome_cmd = [
                    self.chrome_path.strip('"'),  # 引用符を除去
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={self.profile_dir_path}",
                    "--no-first-run",  # 初回起動時の処理をスキップ
                    "--disable-default-apps",  # デフォルトアプリの無効化
                    "--disable-extensions",  # 拡張機能無効化
                    "--disable-background-timer-throttling",  # バックグラウンド制御無効化
                    "--disable-renderer-backgrounding",  # レンダラー背景処理無効化
                    "--disable-backgrounding-occluded-windows",  # ウィンドウ背景処理無効化
                    url
                ]
                print(f"Launching Chrome with command: {chrome_cmd}")

                # shell=Falseでリスト形式のコマンドを使用
                self.chrome_process = subprocess.Popen(
                    chrome_cmd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
                print(f"Chrome process started successfully with PID: {self.chrome_process.pid}")

                # プロセス情報ファイル用ディレクトリの存在確認と作成
                process_info_dir = os.path.dirname(self.process_info_file)
                if not os.path.exists(process_info_dir):
                    os.makedirs(process_info_dir, exist_ok=True)
                    print(f"Created process info directory: {process_info_dir}")

                # Save the parent and child process PIDs to a file
                with open(self.process_info_file, "w") as file:
                    file.write(f"{self.chrome_process.pid},{self.port}\n")
                    parent = psutil.Process(self.chrome_process.pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        file.write(f"{child.pid},{self.port}\n")
            except Exception as e:
                print(f"Error during Chrome launch: {e}")
                print(f"Error type: {type(e).__name__}")
                print(f"Chrome path used: {self.chrome_path}")
                print(f"Profile path used: {self.profile_dir_path}")
                print(f"Port used: {port}")

                # Chrome起動失敗を適切にハンドリング
                if hasattr(self, 'chrome_process') and self.chrome_process:
                    try:
                        self.chrome_process.terminate()
                        print("Chrome process terminated due to launch error")
                    except Exception as term_error:
                        print(f"Failed to terminate Chrome process: {term_error}")
                        pass

        chrome_thread = threading.Thread(target=open_chrome)
        chrome_thread.start()
        chrome_thread.join()  # Chrome起動スレッドの完了を待機

    @staticmethod
    def find_chrome_window_by_pid(target_pid, timeout=15):
        """PIDによりChromeウィンドウを検索（タイムアウト付き再試行）"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            def callback(hwnd, hwnds):
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                window_title = win32gui.GetWindowText(hwnd)
                if found_pid == target_pid and "chrome" in window_title.lower():
                    hwnds.append(hwnd)
                return True

            hwnds = []
            win32gui.EnumWindows(callback, hwnds)
            if hwnds:
                return hwnds[0]
            time.sleep(0.5)  # Retry every 0.5 seconds
        return None

    def transparent_window(self):
        """Chromeウィンドウを透明化"""
        if self.chrome_process is None:
            print("Chrome process is not running. Cannot make window transparent.")
            return
        pids = []
        if self.pid is not None:
            pids.append(self.pid)
        pids.append(self.chrome_process.pid)
        parent = psutil.Process(self.chrome_process.pid)
        children = parent.children(recursive=True)
        pids.extend([child.pid for child in children])
        for pid in pids:
            hwnd = SeleniumWrapper.find_chrome_window_by_pid(pid)

            if hwnd:
                print(f"Found Chrome window: hwnd={hwnd}")
                # Set the window to always on top
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

                # Make the window transparent and click-through
                extended_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, extended_style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
                win32gui.SetLayeredWindowAttributes(hwnd, 0, 1, win32con.LWA_ALPHA)  # Set transparency to 0 (fully transparent)
                self.pid = pid
                self.visible = False
                break
            else:
                print("Failed to find the Chrome window matching the PID after retrying.")

    def restore_window(self):
        """Chromeウィンドウを元に戻す"""
        if self.chrome_process is None:
            print("Chrome process is not running. Cannot restore window.")
            return
        pids = []
        if self.pid is not None:
            pids.append(self.pid)
        pids.append(self.chrome_process.pid)
        parent = psutil.Process(self.chrome_process.pid)
        children = parent.children(recursive=True)
        pids.extend([child.pid for child in children])
        for pid in pids:
            hwnd = SeleniumWrapper.find_chrome_window_by_pid(pid)

            if hwnd:
                print(f"Restoring Chrome window: hwnd={hwnd}")
                # Remove the always on top style
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED)
                # Restore the window to its original state (不透明に戻す)
                win32gui.SetLayeredWindowAttributes(hwnd, 0, 255, win32con.LWA_ALPHA)
                # Remove the transparency and click-through styles
                extended_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, extended_style & ~win32con.WS_EX_LAYERED & ~win32con.WS_EX_TRANSPARENT)
                # Restore the window to its original state
                win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                # Set the window to be visible
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNORMAL)
                self.pid = pid
                self.visible = True
                break
            else:
                print("Failed to find the Chrome window matching the PID after retrying.")

    def close_chrome(self):
        """Chromeプロセスを終了"""
        if self.chrome_process is not None:
            print("Closing Chrome process...")
            try:
                # Get the process tree and terminate all child processes
                parent = psutil.Process(self.chrome_process.pid)
                children = parent.children(recursive=True)
                for child in children:
                    print(f"Terminating child process: {child.pid}")
                    child.terminate()
                gone, still_alive = psutil.wait_procs(children, timeout=5)
                for child in still_alive:
                    print(f"Killing child process: {child.pid}")
                    child.kill()
                # Terminate the parent process
                print(f"Terminating parent process: {parent.pid}")
                parent.terminate()
                parent.wait(timeout=5)
            except psutil.NoSuchProcess:
                print("Process already terminated.")
            except psutil.TimeoutExpired:
                print("Process did not terminate in time, forcing kill...")
                parent.kill()
            finally:
                # Remove the process info file
                if os.path.exists(self.process_info_file):
                    os.remove(self.process_info_file)
            self.chrome_process = None
            self.pid = None
        else:
            print("Chrome process is not running.")

    def setup_webdriver(self, port: str):
        """WebDriverインスタンスを初期化（外部Chrome接続）"""
        print(f"Setting up WebDriver connection to port {port}")

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")

        # 接続リトライロジック
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"WebDriver connection attempt {attempt + 1}/{max_retries}")
                driver = webdriver.Chrome(options=chrome_options)
                print(f"WebDriver connected successfully on attempt {attempt + 1}")
                print(f"WebDriver session ID: {driver.session_id}")
                return driver
            except Exception as e:
                print(f"WebDriver connection attempt {attempt + 1} failed: {e}")
                print(f"Error type: {type(e).__name__}")
                print(f"Debug address: 127.0.0.1:{port}")

                # ポート状態の再確認
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(1)
                        result = s.connect_ex(('127.0.0.1', int(port)))
                        if result == 0:
                            print(f"Port {port} is still accessible")
                        else:
                            print(f"Port {port} is not accessible (connect_ex result: {result})")
                except Exception as port_check_error:
                    print(f"Port check failed: {port_check_error}")

                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指数バックオフ
                    print(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    print(f"Failed to initialize WebDriver after {max_retries} attempts")
                    print("Common causes:")
                    print("  - Chrome process not fully started")
                    print("  - Remote debugging port not accessible")
                    print("  - ChromeDriver version incompatibility")
                    print("  - Firewall blocking localhost connections")
                    return None

    def quit(self, close_with_chrome=True):
        """ブラウザとWebDriverセッションを終了"""
        if close_with_chrome:
            self.close_chrome()
        if self.driver is not None:
            self.driver.quit()
            self.driver = None

    ##############################################################
    ################# 汎用的なメソッド
    ##############################################################

    def focus_to_element(self, element, preventScroll=True):
        """要素にフォーカスを当てる"""
        if self.driver is None:
            print("WebDriver is not initialized. Cannot focus on element.")
            return
        JavaScriptFocusToElement = "arguments[0].focus({'preventScroll': arguments[1]})"
        self.driver.execute_script(JavaScriptFocusToElement, element, preventScroll)

    def click_element(self, element):
        """要素をクリック（JavaScript実行）"""
        if self.driver is None:
            print("WebDriver is not initialized. Cannot click on element.")
            return
        JavaScriptClickElement = "arguments[0].click();"
        self.driver.execute_script(JavaScriptClickElement, element)
        time.sleep(random.randint(5, 20)/10)

    def find_element_with_wait(self, by, value, timeout=60, enableRefresh=False, onBeforeFind=None,
                             max_interval=100, min_interval=100, max_refresh_after_wait_time=7000,
                             min_refresh_after_wait_time=5000, max_refresh_interval=180,
                             min_refresh_interval=60, reverse_condition=False) -> Optional[WebElement]:
        """要素が見つかるまで待機（オプション付きリフレッシュ機能）"""
        if self.driver is None:
            print("WebDriver is not initialized. Cannot find element.")
            return None
        start_time = time.time()
        refresh_time = time.time()
        random_time = random.randint(min_refresh_interval, max_refresh_interval)
        element: Optional[WebElement] = None

        while True:
            try:
                if onBeforeFind:
                    onBeforeFind(self)
                if enableRefresh and time.time() - refresh_time > random_time:
                    self.driver.refresh()
                    refresh_time = time.time()
                    random_time = random.randint(min_refresh_interval, max_refresh_interval)
                    time.sleep(random.randint(min_refresh_after_wait_time, max_refresh_after_wait_time)/1000)
                element = self.driver.find_element(by, value)
                if not reverse_condition:
                    break
            except:
                if reverse_condition:
                    break
                pass
            # timeout秒以上経過したら終了
            if time.time() - start_time > timeout:
                print(f"Timeout after {timeout} seconds while waiting for element: {by}, {value}")
                break
            time.sleep(random.randint(min_interval, max_interval)/1000)

        return element
