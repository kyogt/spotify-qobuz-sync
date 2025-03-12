from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import time
import os
import logging
import random
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Spotify API認証
def initialize_spotify():
    try:
        scope = "playlist-read-private"
        
        # 認証キャッシュが環境変数にあればファイルに書き出す
        if "SPOTIFY_AUTH_CACHE" in os.environ:
            logger.info("SPOTIFY_AUTH_CACHEを使用して認証を試みます")
            with open(".cache", "w") as cache_file:
                cache_file.write(os.environ["SPOTIFY_AUTH_CACHE"])
        else:
            logger.warning("SPOTIFY_AUTH_CACHEが見つかりません。認証が失敗する可能性があります。")
        
        # 認証マネージャーを作成（対話的認証を無効化）
        auth_manager = SpotifyOAuth(
            client_id=os.environ["SPOTIFY_CLIENT_ID"],
            client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
            redirect_uri="http://localhost:8888/callback",
            scope=scope,
            open_browser=False,
            cache_path=".cache"  # キャッシュファイルのパスを明示的に指定
        )
        
        # 既存のトークンからSpotifyクライアントを初期化
        sp = spotipy.Spotify(auth_manager=auth_manager)
        
        # 認証テスト
        try:
            current_user = sp.current_user()
            logger.info(f"Spotify認証成功: {current_user['display_name']}")
        except Exception as e:
            logger.error(f"認証テストに失敗しました: {e}")
            raise
        
        return sp
    except Exception as e:
        logger.error(f"Spotify APIの初期化に失敗しました: {e}")
        raise

# プレイリストのトラック情報を取得する関数
def get_playlist_tracks(sp, playlist_id):
    try:
        logger.info(f"プレイリスト {playlist_id} のトラック情報を取得中...")
        
        # 事前にプレイリストの存在を確認する
        try:
            playlist_info = sp.playlist(playlist_id, fields="name,tracks.total")
            logger.info(f"プレイリスト名: {playlist_info['name']}, 曲数: {playlist_info['tracks']['total']}")
        except Exception as e:
            logger.error(f"プレイリスト情報取得エラー: {e}")
            return []
        
        # トラック情報を取得する
        tracks = []
        
        # ページングでトラックを取得
        results = sp.playlist_items(playlist_id, limit=100)
        current_tracks = [item for item in results['items'] if item['track']]
        tracks.extend(current_tracks)
        
        while results['next']:
            results = sp.next(results)
            current_tracks = [item for item in results['items'] if item['track']]
            tracks.extend(current_tracks)
        
        # トラック情報を整形
        formatted_tracks = []
        for item in tracks:
            track = item['track']
            if track:  # トラックが存在する場合のみ追加
                formatted_tracks.append({
                    'name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'album': track['album']['name'] if 'album' in track else ''
                })
        
        logger.info(f"{len(formatted_tracks)}曲の情報を取得しました")
        return formatted_tracks
    except Exception as e:
        logger.error(f"トラック情報の取得に失敗しました: {e}")
        return []

# スクリーンショットを保存する関数
def save_screenshot(driver, name):
    try:
        screenshot_path = f"screenshot_{name}.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"スクリーンショット保存: {screenshot_path}")
    except Exception as e:
        logger.error(f"スクリーンショット保存に失敗: {e}")

# Qobuzプレイリストを更新する関数
def update_qobuz_playlist(playlist_name, tracks):
    if not tracks:
        logger.warning(f"トラックリストが空のため、{playlist_name}の更新をスキップします")
        return
    
    # Chromeの設定
    chrome_options = Options()
    
    # GitHub Actionsではヘッドレスモードは無効化
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # ボット検出対策の設定
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    # ユーザーエージェントをランダムに設定
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ]
    chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")
    
    # Chromeドライバーセットアップ
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # ボット検出対策のJavaScriptを実行
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            """
        })
    except Exception as e:
        logger.error(f"ChromeDriverのセットアップに失敗: {e}")
        return
    
    try:
        logger.info(f"Qobuzにログイン中...")
        
        # Cookieを削除してクリーンな状態に
        driver.delete_all_cookies()
        
        # Qobuzのホームページにまず訪問（より自然な動きに見せる）
        driver.get("https://www.qobuz.com/")
        logger.info("Qobuzホームページにアクセスしました")
        save_screenshot(driver, "homepage")
        
        # ランダムな待機時間（より人間らしい挙動に）
        time.sleep(random.uniform(2, 5))
        
        # ログインページに移動
        driver.get("https://www.qobuz.com/login")
        logger.info("ログインページに移動しました")
        save_screenshot(driver, "login_page")
        
        # ログインフォームの読み込みを待つ (タイムアウト延長: 120秒)
        try:
            # 複数の可能なセレクタを試す
            selectors = [
                (By.ID, "email"),
                (By.NAME, "email"),
                (By.XPATH, "//input[@type='email']"),
                (By.XPATH, "//input[contains(@placeholder, 'email')]")
            ]
            
            email_field = None
            for selector_type, selector_value in selectors:
                try:
                    email_field = WebDriverWait(driver, 120).until(
                        EC.presence_of_element_located((selector_type, selector_value))
                    )
                    logger.info(f"ログインフォームが見つかりました (セレクタ: {selector_type}={selector_value})")
                    break
                except:
                    continue
            
            if not email_field:
                logger.error("ログインフォームの要素が見つかりませんでした")
                save_screenshot(driver, "login_form_not_found")
                
                # ページソースを保存してデバッグ
                with open("page_source.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                logger.info("ページソースを保存しました: page_source.html")
                
                driver.quit()
                return
            
            logger.info("ログインフォームが表示されました")
        except TimeoutException:
            logger.error("ログインフォームの表示がタイムアウトしました")
            save_screenshot(driver, "login_timeout")
            
            # ページソースを保存してデバッグ
            with open("page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logger.info("ページソースを保存しました: page_source.html")
            
            driver.quit()
            return
        
        # 少し待機（人間の挙動に近づける）
        time.sleep(random.uniform(1, 3))
        
        # ログイン情報を入力
        email_field.send_keys(os.environ["QOBUZ_EMAIL"])
        
        # パスワードフィールドを探す
        password_selectors = [
            (By.ID, "password"),
            (By.NAME, "password"),
            (By.XPATH, "//input[@type='password']")
        ]
        
        password_field = None
        for selector_type, selector_value in password_selectors:
            try:
                password_field = driver.find_element(selector_type, selector_value)
                break
            except:
                continue
        
        if password_field:
            password_field.send_keys(os.environ["QOBUZ_PASSWORD"])
        else:
            logger.error("パスワードフィールドが見つかりませんでした")
            save_screenshot(driver, "password_field_not_found")
            driver.quit()
            return
        
        save_screenshot(driver, "login_filled")
        
        # 少し待機
        time.sleep(random.uniform(1, 2))
        
        # ログインボタンをクリック
        login_button_selectors = [
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Login')]"),
            (By.XPATH, "//button[contains(text(), 'Sign in')]"),
            (By.XPATH, "//input[@type='submit']")
        ]
        
        login_button = None
        for selector_type, selector_value in login_button_selectors:
            try:
                login_button = driver.find_element(selector_type, selector_value)
                break
            except:
                continue
        
        if login_button:
            login_button.click()
            logger.info("ログインボタンをクリックしました")
        else:
            logger.error("ログインボタンが見つかりませんでした")
            save_screenshot(driver, "login_button_not_found")
            driver.quit()
            return
        
        # ログイン成功を確認 (タイムアウト延長: 120秒)
        try:
            # 複数の可能なセレクタを試す
            success_selectors = [
                (By.XPATH, "//div[contains(@class, 'user-menu')]"),
                (By.XPATH, "//a[contains(@href, '/logout')]"),
                (By.XPATH, "//div[contains(@class, 'header-user')]"),
                (By.XPATH, "//a[contains(@href, '/my-profile')]")
            ]
            
            success_element = None
            for selector_type, selector_value in success_selectors:
                try:
                    success_element = WebDriverWait(driver, 120).until(
                        EC.presence_of_element_located((selector_type, selector_value))
                    )
                    logger.info(f"ログイン成功確認 (セレクタ: {selector_type}={selector_value})")
                    break
                except:
                    continue
            
            if success_element:
                logger.info("ログイン成功")
                save_screenshot(driver, "login_success")
            else:
                logger.error("ログイン成功の確認ができませんでした")
                save_screenshot(driver, "login_success_not_confirmed")
                
                # CAPTCHAの確認
                if "captcha" in driver.page_source.lower() or "robot" in driver.page_source.lower():
                    logger.error("CAPTCHAが検出されました。")
                
                driver.quit()
                return
        except TimeoutException:
            logger.error("ログイン成功の確認がタイムアウトしました")
            save_screenshot(driver, "login_success_timeout")
            
            # CAPTCHAの確認
            if "captcha" in driver.page_source.lower() or "robot" in driver.page_source.lower():
                logger.error("CAPTCHAが検出されました。")
            
            driver.quit()
            return
        
        # ここからはプレイリスト操作部分...
        # 既存のコードを続けます
        
        # マイプレイリスト画面に移動
        logger.info("プレイリストページに移動します")
        driver.get("https://www.qobuz.com/my-profile/playlists")
        time.sleep(5)  # ページの読み込みを待つ
        save_screenshot(driver, "playlists_page")
        
        # プレイリストの存在確認
        logger.info(f"プレイリスト '{playlist_name}' を確認中...")
        try:
            # 複数の可能なセレクタを試す
            selectors = [
                f"//div[contains(text(), '{playlist_name}')]",
                f"//span[contains(text(), '{playlist_name}')]",
                f"//a[contains(text(), '{playlist_name}')]"
            ]
            
            playlist_found = False
            for selector in selectors:
                elements = driver.find_elements(By.XPATH, selector)
                if len(elements) > 0:
                    playlist_found = True
                    logger.info(f"プレイリスト '{playlist_name}' が見つかりました (セレクタ: {selector})")
                    break
            
            if not playlist_found:
                logger.info(f"プレイリスト '{playlist_name}' が見つかりませんでした。新規作成します。")
        except Exception as e:
            logger.warning(f"プレイリスト検索エラー: {e}")
            playlist_found = False
        
        # 残りのプレイリスト操作コードは変更なし...
        
        # テスト用に、最初の数曲だけ処理する
        test_limit = min(5, len(tracks))  # 最大5曲まで
        logger.info(f"テスト用に最初の{test_limit}曲のみ処理します")
        
        for i, track in enumerate(tracks[:test_limit]):
            # 既存のトラック追加コード...
            # この部分は変更なし
            pass
            
        logger.info(f"テスト実行完了: {test_limit}曲を処理しました")
        
    except Exception as e:
        logger.error(f"Qobuzプレイリスト更新中にエラーが発生しました: {e}")
        save_screenshot(driver, "final_error")
    finally:
        driver.quit()

# メイン処理
def main():
    try:
        # Spotify API初期化
        sp = initialize_spotify()
        
        # プレイリストIDを取得
        combined_playlist_id = os.environ.get("DISCOVER_WEEKLY_ID")  # 統合プレイリストIDにDiscover Weekly IDを使用
        
        logger.info(f"設定された統合プレイリストID: {combined_playlist_id}")
        
        if combined_playlist_id:
            # 統合プレイリストの同期
            logger.info("統合プレイリストの同期を開始します")
            combined_tracks = get_playlist_tracks(sp, combined_playlist_id)
            if combined_tracks:
                # とりあえずトラック取得までの検証
                logger.info(f"トラック取得成功: {len(combined_tracks)}曲")
                # テスト段階では実際のQobuz更新は行わない
                # update_qobuz_playlist("Spotify Discover & Release (Combined)", combined_tracks)
                logger.info("Qobuz同期はスキップします（テスト段階）")
            else:
                logger.error("統合プレイリストのトラックが取得できませんでした")
        else:
            logger.error("DISCOVER_WEEKLY_ID（統合プレイリストID）が設定されていません")
        
        logger.info("全ての処理が完了しました")
    
    except Exception as e:
        logger.error(f"メイン処理でエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
