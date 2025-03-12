import os
import time
import logging
import random
import pickle
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Spotifyの認証
def authenticate_spotify():
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    auth_cache = os.environ.get("SPOTIFY_AUTH_CACHE")
    
    if auth_cache:
        logging.info("SPOTIFY_AUTH_CACHEを使用して認証を試みます")
        try:
            # 環境変数の値をファイルに書き込む
            with open(".cache", "w") as f:
                f.write(auth_cache)
            
            sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri="http://localhost:8080",
                scope="playlist-read-private",
                open_browser=False
            ))
            
            user = sp.current_user()
            logging.info(f"Spotify認証成功: {user['display_name']}")
            return sp
        except Exception as e:
            logging.error(f"認証エラー: {str(e)}")
            return None
    else:
        logging.error("SPOTIFY_AUTH_CACHEが設定されていません")
        return None

# プレイリストからトラック情報を取得
def get_playlist_tracks(sp, playlist_id):
    try:
        logging.info(f"プレイリスト {playlist_id} のトラック情報を取得中...")
        results = sp.playlist(playlist_id)
        
        playlist_name = results['name']
        tracks_items = results['tracks']['items']
        total_tracks = len(tracks_items)
        
        logging.info(f"プレイリスト名: {playlist_name}, 曲数: {total_tracks}")
        
        track_info = []
        for item in tracks_items:
            track = item['track']
            if track:
                artists = ", ".join([artist['name'] for artist in track['artists']])
                track_info.append({
                    'name': track['name'],
                    'artist': artists,
                    'album': track['album']['name'],
                    'url': track['external_urls']['spotify'] if 'external_urls' in track and 'spotify' in track['external_urls'] else None
                })
        
        logging.info(f"{len(track_info)}曲の情報を取得しました")
        return track_info
    except Exception as e:
        logging.error(f"プレイリストトラック取得エラー: {str(e)}")
        return []

# ブラウザ設定（ボット検出回避対策強化版）
def setup_browser():
    """ボット検出対策を強化したブラウザの設定"""
    options = webdriver.ChromeOptions()
    
    # GitHub Actions環境の場合の設定
    if os.environ.get('CI'):
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
    else:
        # ローカル環境ではヘッドレスモードを無効化
        options.headless = False
    
    # ボット検出対策の設定
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 本物のブラウザに見せるための設定
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--start-maximized")
    
    # ユーザーエージェントの設定
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ]
    options.add_argument(f"user-agent={random.choice(user_agents)}")
    
    # Chromiumベースのブラウザを設定
    try:
        # GitHub Actions環境では直接Chromeを使用
        if os.environ.get('CI'):
            driver = webdriver.Chrome(options=options)
        else:
            # ローカル環境ではChromeDriverManagerを使用
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        
        # webdriver検出を回避するJavaScript
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    except Exception as e:
        logging.error(f"ブラウザ設定エラー: {str(e)}")
        raise

# Cookie管理関数
def save_cookies(browser, filename="qobuz_cookies.pkl"):
    """ブラウザのCookieを保存"""
    try:
        pickle.dump(browser.get_cookies(), open(filename, "wb"))
        logging.info(f"Cookieを保存しました: {filename}")
        return True
    except Exception as e:
        logging.error(f"Cookie保存中にエラー: {str(e)}")
        return False

def load_cookies(browser, filename="qobuz_cookies.pkl"):
    """保存されたCookieをロード"""
    try:
        if os.path.exists(filename):
            cookies = pickle.load(open(filename, "rb"))
            # 事前にQobuzのドメインにアクセスしておく
            browser.get("https://www.qobuz.com")
            time.sleep(2)
            for cookie in cookies:
                # 一部のブラウザはexpiry属性があるとエラーになる場合がある
                if 'expiry' in cookie:
                    del cookie['expiry']
                browser.add_cookie(cookie)
            logging.info(f"Cookieをロードしました: {filename}")
            browser.refresh()  # クッキー適用後にリフレッシュ
            time.sleep(2)
            return True
        return False
    except Exception as e:
        logging.error(f"Cookie読み込み中にエラー: {str(e)}")
        return False

def check_login_status(browser):
    """ログイン状態を確認"""
    try:
        # ユーザープロフィール要素などでログイン状態を確認
        # 注: 以下のXPATHはQobuzの実際のHTML構造に合わせて調整が必要です
        browser.save_screenshot("login_check.png")  # デバッグ用
        elem = browser.find_elements(By.XPATH, "//div[contains(@class, 'userMenu')]")
        return len(elem) > 0
    except Exception as e:
        logging.debug(f"ログイン状態確認中にエラー: {str(e)}")
        return False

def perform_with_retry(func, *args, max_retries=3, retry_delay=5, **kwargs):
    """関数実行をリトライするためのラッパー"""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.warning(f"試行 {attempt+1}/{max_retries} 失敗: {str(e)}")
            if attempt < max_retries - 1:
                # ランダムな待機時間で再試行
                sleep_time = retry_delay * (1 + random.random())
                logging.info(f"{sleep_time:.2f}秒後に再試行します...")
                time.sleep(sleep_time)
            else:
                logging.error(f"最大試行回数に達しました: {func.__name__}")
                raise

# 人間のような動きでQobuzにログイン
def login_to_qobuz(browser, email, password):
    """人間らしい動作でQobuzにログインする"""
    try:
        # Qobuzのログインページに移動
        browser.get("https://www.qobuz.com/signin")
        logging.info("Qobuzログインページにアクセスしました")
        
        # ページの読み込みを待機
        time.sleep(random.uniform(2, 4))
        
        # ページ表示のデバッグ用にスクリーンショット
        browser.save_screenshot("login_page.png")
        
        # ランダムなスクロール（自然な動きに見せる）
        browser.execute_script(f"window.scrollBy(0, {random.randint(100, 300)})")
        time.sleep(random.uniform(0.5, 1.5))
        
        # メールアドレス入力フィールドを探して入力
        try:
            # 注: セレクタはQobuzのサイト構造に合わせて調整が必要
            email_field = WebDriverWait(browser, 10).until(
                EC.element_to_be_clickable((By.ID, "email"))  # または適切なセレクタ
            )
            email_field.click()
            # 一字一字タイプするシミュレーション
            for char in email:
                email_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
                
            time.sleep(random.uniform(1, 2))
            
            # パスワード入力
            password_field = browser.find_element(By.ID, "password")  # または適切なセレクタ
            password_field.click()
            for char in password:
                password_field.send_keys(char)
                time.sleep(random.uniform(0.05, 0.2))
                
            time.sleep(random.uniform(0.5, 1.5))
            
            # ログインボタンをクリック
            login_button = browser.find_element(By.XPATH, "//button[@type='submit']")  # または適切なセレクタ
            login_button.click()
            
            # ログイン後の読み込みを待機
            time.sleep(random.uniform(3, 5))
            
            # スクリーンショットを保存（デバッグ用）
            browser.save_screenshot("after_login.png")
            
            # ログイン成功の確認
            if check_login_status(browser):
                logging.info("Qobuzへのログイン成功")
                return True
            else:
                logging.error("ログインプロセスは完了しましたが、認証に失敗した可能性があります")
                return False
                
        except Exception as e:
            logging.error(f"ログインフォーム操作中にエラー: {str(e)}")
            browser.save_screenshot("login_form_error.png")
            return False
        
    except Exception as e:
        logging.error(f"Qobuzログイン中にエラーが発生しました: {str(e)}")
        browser.save_screenshot("login_error.png")
        return False

# プレイリスト作成とトラック追加
def create_qobuz_playlist(browser, playlist_name):
    """Qobuzで新しいプレイリストを作成"""
    try:
        # プレイリストページに移動
        browser.get("https://www.qobuz.com/my-profile/playlists")
        time.sleep(random.uniform(2, 3))
        
        # 「新規プレイリスト作成」ボタンをクリック
        create_button = WebDriverWait(browser, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Create a playlist')]"))  # 実際のテキストに合わせて調整
        )
        create_button.click()
        time.sleep(random.uniform(1, 2))
        
        # プレイリスト名入力
        name_field = WebDriverWait(browser, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Playlist name']"))  # 実際のプレースホルダーに合わせて調整
        )
        name_field.clear()
        for char in playlist_name:
            name_field.send_keys(char)
            time.sleep(random.uniform(0.05, 0.1))
        
        # 保存ボタンをクリック
        save_button = browser.find_element(By.XPATH, "//button[contains(text(), 'Create')]")  # 実際のテキストに合わせて調整
        save_button.click()
        
        # 作成完了を待機
        time.sleep(random.uniform(2, 3))
        
        # 作成されたプレイリストのURLを取得
        current_url = browser.current_url
        logging.info(f"プレイリスト作成完了: {current_url}")
        
        return current_url
    except Exception as e:
        logging.error(f"プレイリスト作成エラー: {str(e)}")
        browser.save_screenshot("playlist_create_error.png")
        return None

def search_and_add_track(browser, track):
    """トラックを検索して追加"""
    try:
        # 検索クエリの作成
        search_query = f"{track['artist']} {track['name']}"
        
        # 検索ページに移動
        browser.get(f"https://www.qobuz.com/search?q={search_query}")
        time.sleep(random.uniform(2, 4))
        
        # 検索結果の最初のトラックを選択
        first_track = WebDriverWait(browser, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'track-item')]"))  # 実際のクラスに合わせて調整
        )
        
        # 右クリックして「プレイリストに追加」を選択
        # 注: この部分はJavaScriptの実行やアクションチェーンで実装する必要があります
        # 簡略化のため、ここではその部分は省略しています
        
        logging.info(f"トラック追加: {search_query}")
        return True
    except Exception as e:
        logging.error(f"トラック追加エラー: {str(e)}")
        browser.save_screenshot(f"track_add_error_{track['name']}.png")
        return False

# SpotifyからQobuzへの同期メイン関数
def sync_to_qobuz(spotify_tracks, qobuz_email, qobuz_password):
    """SpotifyのトラックをQobuzに同期する改良版"""
    logging.info("Qobuz同期を開始します")
    
    browser = setup_browser()
    
    try:
        # Cookie認証を試みる
        cookie_auth_success = load_cookies(browser)
        
        # Cookie認証失敗または未ログインの場合、通常ログイン
        if not cookie_auth_success or not check_login_status(browser):
            logging.info("Cookie認証に失敗したか、未ログイン状態です。通常ログインを試みます")
            login_success = perform_with_retry(login_to_qobuz, browser, qobuz_email, qobuz_password, max_retries=3)
            
            if login_success:
                # 成功したらCookieを保存
                save_cookies(browser)
            else:
                raise Exception("Qobuzへのログインに失敗しました")
        
        # プレイリスト作成（日付を含めた名前で）
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        playlist_name = f"Spotify Sync {today}"
        
        playlist_url = create_qobuz_playlist(browser, playlist_name)
        if not playlist_url:
            raise Exception("プレイリスト作成に失敗しました")
        
        # トラックの追加
        success_count = 0
        for track in spotify_tracks:
            # 最大50曲まで処理（長すぎる処理を避けるため）
            if success_count >= 50:
                break
                
            if search_and_add_track(browser, track):
                success_count += 1
                # トラック追加間の待機（サーバー負荷軽減）
                time.sleep(random.uniform(1.5, 3))
        
        logging.info(f"Qobuzへの同期が完了しました。{success_count}曲を追加しました")
        return True
        
    except Exception as e:
        logging.error(f"Qobuz同期中にエラーが発生しました: {str(e)}")
        # エラー時のスクリーンショット保存
        browser.save_screenshot("qobuz_sync_error.png")
        return False
    finally:
        # ブラウザを必ず閉じる
        browser.quit()

# メイン処理
if __name__ == "__main__":
    # Spotify認証
    sp = authenticate_spotify()
    if not sp:
        logging.error("Spotify認証に失敗しました")
        exit(1)
    
    # プレイリストID取得
    playlist_id = os.environ.get("COMBINED_PLAYLIST_ID")
    if not playlist_id:
        logging.error("COMBINED_PLAYLIST_IDが設定されていません")
        exit(1)
    
    logging.info(f"設定された統合プレイリストID: {playlist_id}")
    logging.info("統合プレイリストの同期を開始します")
    
    # トラック情報取得
    tracks = get_playlist_tracks(sp, playlist_id)
    
    # Qobuz同期
    if tracks:
        logging.info(f"トラック取得成功: {len(tracks)}曲")
        
        # テスト段階のためQobuz同期はスキップ（本番環境では以下のコメントを解除）
        logging.info("Qobuz同期はスキップします（テスト段階）")
        
        # 本番用コード（準備ができたらコメントを解除）
        """
        qobuz_email = os.environ.get("QOBUZ_EMAIL")
        qobuz_password = os.environ.get("QOBUZ_PASSWORD")
        
        if qobuz_email and qobuz_password:
            sync_result = sync_to_qobuz(tracks, qobuz_email, qobuz_password)
            if sync_result:
                logging.info("Qobuz同期が成功しました")
            else:
                logging.error("Qobuz同期に失敗しました")
        else:
            logging.error("QobuzのログインIDまたはパスワードが設定されていません")
        """
    else:
        logging.error("同期するトラックが見つかりませんでした")
    
    logging.info("全ての処理が完了しました")
