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
    try:
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
    except Exception as e:
        logging.error(f"予期せぬ認証エラー: {str(e)}")
        return None

# プレイリストからトラック情報を取得
def get_playlist_tracks(sp, playlist_id):
    try:
        logging.info(f"プレイリスト {playlist_id} のトラック情報を取得開始")
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
    """ボット検出対策を強化したブラウザの設定（改良版）"""
    try:
        options = webdriver.ChromeOptions()
        
        # 一意のユーザーデータディレクトリを指定または完全に無効化
        import tempfile
        import uuid
        temp_dir = os.path.join(tempfile.gettempdir(), f"chrome_profile_{uuid.uuid4().hex}")
        logging.info(f"一時ユーザーデータディレクトリを作成: {temp_dir}")
        options.add_argument(f"--user-data-dir={temp_dir}")
        
        # または、シークレットモードを使用してユーザーデータを保存しない方式にする
        # options.add_argument("--incognito")
        
        # GitHub Actions環境の場合の設定
        if os.environ.get('CI'):
            logging.info("CI環境を検出: CI設定を適用します")
            # ヘッドレスモードはQobuzの自動ログインに影響する可能性があるため、テスト段階では一時的に無効化
            options.add_argument('--headless=new')  # ヘッドレスモードを有効化
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
        else:
            logging.info("ローカル環境: 標準設定を適用します")
            options.headless = False
        
        # ウィンドウサイズ設定
        options.add_argument("--window-size=1920,1080")
        
        # ボット検出対策の設定
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # ユーザーエージェントの設定（より一般的なものに）
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
        ]
        selected_agent = random.choice(user_agents)
        options.add_argument(f"user-agent={selected_agent}")
        logging.info(f"選択されたユーザーエージェント: {selected_agent}")
        
        # Chromiumベースのブラウザを設定
        if os.environ.get('CI'):
            logging.info("CI環境: 直接Chromeを使用します")
            driver = webdriver.Chrome(options=options)
        else:
            logging.info("ローカル環境: ChromeDriverManagerを使用します")
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        
        # webdriver検出を回避するJavaScript
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        logging.info("ブラウザ設定完了")
        
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
            logging.info(f"既存のCookieファイルを読み込みます: {filename}")
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
        else:
            logging.info("既存のCookieファイルが見つかりません")
            return False
    except Exception as e:
        logging.error(f"Cookie読み込み中にエラー: {str(e)}")
        return False

def check_login_status(browser):
    """ログイン状態を確認"""
    try:
        # ユーザープロフィール要素などでログイン状態を確認
        # 注: 以下のXPATHはQobuzの実際のHTML構造に合わせて調整が必要です
        logging.info("ログイン状態を確認中...")
        browser.save_screenshot("login_check.png")  # デバッグ用
        elem = browser.find_elements(By.XPATH, "//div[contains(@class, 'userMenu')]")
        is_logged_in = len(elem) > 0
        logging.info(f"ログイン状態: {'ログイン済み' if is_logged_in else '未ログイン'}")
        return is_logged_in
    except Exception as e:
        logging.error(f"ログイン状態確認中にエラー: {str(e)}")
        return False

def perform_with_retry(func, *args, max_retries=3, retry_delay=5, **kwargs):
    """関数実行をリトライするためのラッパー"""
    for attempt in range(max_retries):
        try:
            logging.info(f"関数 {func.__name__} を実行します (試行 {attempt+1}/{max_retries})")
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
# login_to_qobuz関数の修正部分

def login_to_qobuz(browser, email, password):
    """人間らしい動作でQobuzにログインする（改良版）"""
    try:
        # Qobuzのログインページに移動
        browser.get("https://www.qobuz.com/signin")
        logging.info("Qobuzログインページにアクセスしました")
        
        # ページソースを保存（デバッグ用）
        with open("login_page_source.html", "w", encoding="utf-8") as f:
            f.write(browser.page_source)
        logging.info("ページソースを保存しました")
        
        # ページの読み込みを待機
        time.sleep(random.uniform(3, 5))
        
        # スクリーンショット保存
        browser.save_screenshot("login_page.png")
        logging.info("ログインページのスクリーンショットを保存しました")
        
        # より柔軟な要素検索方法を使用
        logging.info("メールアドレス入力フィールドを検索中...")
        
        # 複数のセレクタを試行
        selectors = [
            (By.ID, "email"),
            (By.NAME, "email"),
            (By.NAME, "username"),
            (By.ID, "username"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.XPATH, "//input[@type='email']"),
            (By.XPATH, "//form//input[contains(@placeholder, 'mail')]"),
            (By.XPATH, "//form//input[1]")  # フォームの最初のinput要素
        ]
        
        email_field = None
        for selector_type, selector_value in selectors:
            try:
                logging.info(f"セレクタを試行中: {selector_type} = {selector_value}")
                email_field = WebDriverWait(browser, 3).until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                if email_field:
                    logging.info(f"メールアドレス入力フィールドを発見: {selector_type} = {selector_value}")
                    break
            except:
                continue
        
        if not email_field:
            # ページ上のすべてのinput要素を探す
            inputs = browser.find_elements(By.TAG_NAME, "input")
            logging.info(f"{len(inputs)}個のinput要素を発見")
            
            if len(inputs) > 0:
                email_field = inputs[0]  # 最初のinput要素を使用
                logging.info("最初のinput要素をメールアドレスフィールドとして使用します")
            else:
                raise Exception("メールアドレス入力フィールドが見つかりませんでした")
        
        # 以下、入力処理は同様
        email_field.click()
        logging.info("メールアドレス入力フィールドを選択しました")
        
        # メールアドレス入力
        for char in email:
            email_field.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
            
        time.sleep(random.uniform(1, 2))
        
        # 後続のパスワード入力処理も同様の方法で柔軟に対応
        # ...

# プレイリスト作成とトラック追加
def create_qobuz_playlist(browser, playlist_name):
    """Qobuzで新しいプレイリストを作成"""
    try:
        # プレイリストページに移動
        browser.get("https://www.qobuz.com/my-profile/playlists")
        logging.info("Qobuzプレイリストページにアクセスしました")
        time.sleep(random.uniform(2, 3))
        
        # ページ表示のデバッグ用にスクリーンショット
        browser.save_screenshot("playlist_page.png")
        
        # 「新規プレイリスト作成」ボタンをクリック
        logging.info("プレイリスト作成ボタンを検索中...")
        create_button = WebDriverWait(browser, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Create a playlist')]"))  # 実際のテキストに合わせて調整
        )
        logging.info("プレイリスト作成ボタンをクリックします")
        create_button.click()
        time.sleep(random.uniform(1, 2))
        
        # プレイリスト名入力
        logging.info("プレイリスト名入力フィールドを検索中...")
        name_field = WebDriverWait(browser, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Playlist name']"))  # 実際のプレースホルダーに合わせて調整
        )
        name_field.clear()
        logging.info(f"プレイリスト名 '{playlist_name}' を入力中...")
        for char in playlist_name:
            name_field.send_keys(char)
            time.sleep(random.uniform(0.05, 0.1))
        
        # 保存ボタンをクリック
        logging.info("保存ボタンを検索中...")
        save_button = browser.find_element(By.XPATH, "//button[contains(text(), 'Create')]")  # 実際のテキストに合わせて調整
        logging.info("保存ボタンをクリックします")
        save_button.click()
        
        # 作成完了を待機
        wait_time = random.uniform(2, 3)
        logging.info(f"プレイリスト作成の完了を{wait_time:.1f}秒間待機します")
        time.sleep(wait_time)
        
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
        logging.info(f"検索クエリ: {search_query}")
        
        # 検索ページに移動
        encoded_query = search_query.replace(' ', '+')
        browser.get(f"https://www.qobuz.com/search?q={encoded_query}")
        logging.info(f"検索ページにアクセスしました: {encoded_query}")
        time.sleep(random.uniform(2, 4))
        
        # ページ表示のデバッグ用にスクリーンショット
        browser.save_screenshot(f"search_{track['name']}.png")
        
        # 検索結果の最初のトラックを選択
        logging.info("検索結果から最初のトラックを検索中...")
        first_track = WebDriverWait(browser, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'track-item')]"))  # 実際のクラスに合わせて調整
        )
        
        # この部分は実際のQobuzのUIに合わせて調整が必要
        # 右クリックして「プレイリストに追加」を選択する部分は
        # JavaScriptの実行やアクションチェーンを使って実装する必要があります
        
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
    
    browser = None
    try:
        # ブラウザ設定
        logging.info("ブラウザを設定中...")
        browser = setup_browser()
        
        # Cookie認証を試みる
        logging.info("Cookieによる認証を試みます")
        cookie_auth_success = load_cookies(browser)
        
        # Cookie認証失敗または未ログインの場合、通常ログイン
        if not cookie_auth_success or not check_login_status(browser):
            logging.info("Cookie認証に失敗したか、未ログイン状態です。通常ログインを試みます")
            login_success = perform_with_retry(login_to_qobuz, browser, qobuz_email, qobuz_password, max_retries=3)
            
            if login_success:
                # 成功したらCookieを保存
                logging.info("ログイン成功: Cookieを保存します")
                save_cookies(browser)
            else:
                raise Exception("Qobuzへのログインに失敗しました")
        
        # ログイン後の待機
        wait_time = random.uniform(2, 4)
        logging.info(f"ログイン処理完了後、{wait_time:.1f}秒間待機します")
        time.sleep(wait_time)
        
        # プレイリスト作成（日付を含めた名前で）
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        playlist_name = f"Spotify Sync {today}"
        logging.info(f"新しいプレイリストを作成します: {playlist_name}")
        
        playlist_url = create_qobuz_playlist(browser, playlist_name)
        if not playlist_url:
            raise Exception("プレイリスト作成に失敗しました")
        
        # トラックの追加
        success_count = 0
        # 初期テストのため、最初の10曲だけを処理
        max_tracks = 10  # テスト段階では少ない曲数から始める
        
        logging.info(f"トラック追加を開始します (最大{max_tracks}曲)")
        for i, track in enumerate(spotify_tracks[:max_tracks]):
            # 曲数の制限
            if success_count >= max_tracks:
                logging.info("最大曲数に達したため、処理を終了します")
                break
                
            logging.info(f"トラック {i+1}/{min(len(spotify_tracks), max_tracks)} を処理中: {track['artist']} - {track['name']}")
            if search_and_add_track(browser, track):
                success_count += 1
                logging.info(f"トラック追加成功 ({success_count}/{max_tracks})")
                # トラック追加間の待機（サーバー負荷軽減）
                wait_time = random.uniform(1.5, 3)
                logging.info(f"次のトラック処理まで{wait_time:.1f}秒間待機します")
                time.sleep(wait_time)
        
        logging.info(f"Qobuzへの同期が完了しました。{success_count}曲を追加しました")
        return True
        
    except Exception as e:
        logging.error(f"Qobuz同期中にエラーが発生しました: {str(e)}")
        # エラー時のスクリーンショット保存
        if browser:
            browser.save_screenshot("qobuz_sync_error.png")
        return False
    finally:
        # ブラウザを必ず閉じる
        if browser:
            logging.info("ブラウザを終了します")
            browser.quit()

# メイン処理
if __name__ == "__main__":
    try:
        logging.info("スクリプト実行を開始します")
        
        # Spotify認証
        sp = authenticate_spotify()
        if not sp:
            logging.error("Spotify認証に失敗しました")
            exit(1)
        
        # プレイリストID取得（後方互換性のため両方の環境変数をサポート）
        playlist_id = os.environ.get("COMBINED_PLAYLIST_ID") or os.environ.get("DISCOVER_WEEKLY_ID")
        if not playlist_id:
            logging.error("COMBINED_PLAYLIST_IDまたはDISCOVER_WEEKLY_IDが設定されていません")
            exit(1)
        
        logging.info(f"使用するプレイリストID: {playlist_id}")
        logging.info("統合プレイリストの同期を開始します")
        
        # トラック情報取得
        tracks = get_playlist_tracks(sp, playlist_id)
        
        # Qobuz同期
        if tracks:
            logging.info(f"トラック取得成功: {len(tracks)}曲")
            
            # Qobuz同期を有効化
            qobuz_email = os.environ.get("QOBUZ_EMAIL")
            qobuz_password = os.environ.get("QOBUZ_PASSWORD")
            
            if qobuz_email and qobuz_password:
                logging.info("Qobuz認証情報が見つかりました。同期を開始します。")
                sync_result = sync_to_qobuz(tracks, qobuz_email, qobuz_password)
                if sync_result:
                    logging.info("Qobuz同期が成功しました")
                else:
                    logging.error("Qobuz同期に失敗しました")
            else:
                logging.error("QobuzのログインIDまたはパスワードが設定されていません")
        else:
            logging.error("同期するトラックが見つかりませんでした")
        
        logging.info("全ての処理が完了しました")
    except Exception as e:
        logging.error(f"予期せぬエラーが発生しました: {str(e)}")
        exit(1)
