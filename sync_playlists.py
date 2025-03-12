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
    # GitHub Actionsではヘッドレスモードを使用
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # デバッグオプション追加
    chrome_options.add_argument("--verbose")
    
    # Chromeドライバーセットアップ
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        logger.error(f"ChromeDriverのセットアップに失敗: {e}")
        return
    
    try:
        logger.info(f"Qobuzにログイン中...")
        # Qobuzにログイン
        driver.get("https://www.qobuz.com/login")
        save_screenshot(driver, "login_page")
        
        # ログインフォームの読み込みを待つ (最大60秒)
        try:
            email_field = WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            logger.info("ログインフォームが表示されました")
        except TimeoutException:
            logger.error("ログインフォームの表示がタイムアウトしました")
            save_screenshot(driver, "login_timeout")
            driver.quit()
            return
        
        # ログイン情報を入力
        email_field.send_keys(os.environ["QOBUZ_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["QOBUZ_PASSWORD"])
        save_screenshot(driver, "login_filled")
        
        # ログインボタンをクリック
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        logger.info("ログインボタンをクリックしました")
        
        # ログイン成功を確認
        try:
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'user-menu')]"))
            )
            logger.info("ログイン成功")
            save_screenshot(driver, "login_success")
        except TimeoutException:
            logger.error("ログイン成功の確認がタイムアウトしました")
            save_screenshot(driver, "login_failure")
            
            # CAPTCHAの確認
            if "captcha" in driver.page_source.lower() or "robot" in driver.page_source.lower():
                logger.error("CAPTCHAが検出されました。ヘッドレスモードでは解決できません。")
            
            driver.quit()
            return
        
        # マイプレイリスト画面に移動
        driver.get("https://www.qobuz.com/my-profile/playlists")
        logger.info("プレイリストページに移動しました")
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
        
        if not playlist_found:
            # 新規プレイリスト作成
            logger.info(f"プレイリスト '{playlist_name}' を新規作成します")
            
            # 「+」または「Create playlist」ボタンを探す
            try:
                # 複数の可能なセレクタを試す
                create_button_selectors = [
                    "//button[contains(text(), 'Create playlist') or contains(text(), 'Create a playlist')]",
                    "//button[contains(@class, 'create-playlist')]",
                    "//a[contains(text(), 'Create playlist') or contains(text(), 'Create a playlist')]",
                    "//div[contains(text(), 'Create playlist') or contains(text(), 'Create a playlist')]"
                ]
                
                create_button = None
                for selector in create_button_selectors:
                    elements = driver.find_elements(By.XPATH, selector)
                    if len(elements) > 0:
                        create_button = elements[0]
                        logger.info(f"プレイリスト作成ボタンが見つかりました (セレクタ: {selector})")
                        break
                
                if create_button:
                    create_button.click()
                    logger.info("プレイリスト作成ボタンをクリックしました")
                else:
                    logger.error("プレイリスト作成ボタンが見つかりませんでした")
                    save_screenshot(driver, "create_button_not_found")
                    driver.quit()
                    return
            except Exception as e:
                logger.error(f"プレイリスト作成ボタンクリックエラー: {e}")
                save_screenshot(driver, "create_button_error")
                driver.quit()
                return
            
            # プレイリスト名入力フォームが表示されるまで待つ
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Playlist name' or @placeholder='Name']"))
                )
                logger.info("プレイリスト名入力フォームが表示されました")
            except TimeoutException:
                logger.error("プレイリスト名入力フォームの表示がタイムアウトしました")
                save_screenshot(driver, "playlist_name_form_timeout")
                driver.quit()
                return
            
            # プレイリスト名を入力して作成
            try:
                playlist_name_input = driver.find_element(By.XPATH, "//input[@placeholder='Playlist name' or @placeholder='Name']")
                playlist_name_input.clear()
                playlist_name_input.send_keys(playlist_name)
                logger.info(f"プレイリスト名 '{playlist_name}' を入力しました")
                
                # 作成ボタンをクリック
                create_confirm_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Create') and not(contains(text(), 'Create playlist'))]")
                create_confirm_button.click()
                logger.info("プレイリスト作成確認ボタンをクリックしました")
                time.sleep(3)
            except Exception as e:
                logger.error(f"プレイリスト名入力・作成エラー: {e}")
                save_screenshot(driver, "playlist_create_error")
                driver.quit()
                return
        else:
            # 既存プレイリストをクリック
            logger.info(f"既存のプレイリスト '{playlist_name}' を編集します")
            
            try:
                for selector in selectors:
                    elements = driver.find_elements(By.XPATH, selector)
                    if len(elements) > 0:
                        elements[0].click()
                        logger.info(f"プレイリスト '{playlist_name}' をクリックしました")
                        break
                time.sleep(3)
            except Exception as e:
                logger.error(f"プレイリストクリックエラー: {e}")
                save_screenshot(driver, "playlist_click_error")
                driver.quit()
                return
            
            # プレイリストを空にする（任意）
            try:
                # プレイリストページに移動した確認
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'playlist-header')]"))
                )
                logger.info("プレイリストページが表示されました")
                save_screenshot(driver, "playlist_page")
                
                # トラックがあるか確認
                tracks_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'track-item')]")
                if len(tracks_elements) > 0:
                    logger.info(f"既存のトラック {len(tracks_elements)}曲 を削除します")
                    
                    try:
                        # 全選択ボタンをクリック
                        select_all_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'select-all')]")
                        select_all_btn.click()
                        logger.info("全選択ボタンをクリックしました")
                        time.sleep(1)
                        
                        # 削除ボタンをクリック
                        delete_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'delete') or contains(text(), 'Delete')]")
                        delete_btn.click()
                        logger.info("削除ボタンをクリックしました")
                        time.sleep(1)
                        
                        # 確認ダイアログのOKボタンをクリック
                        confirm_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'OK') or contains(text(), 'Confirm')]")
                        confirm_btn.click()
                        logger.info("削除確認ボタンをクリックしました")
                        time.sleep(2)
                    except Exception as e:
                        logger.warning(f"トラック削除エラー: {e}")
                        save_screenshot(driver, "track_delete_error")
                        # 削除に失敗しても続行する
            except Exception as e:
                logger.warning(f"プレイリスト編集準備エラー: {e}")
                save_screenshot(driver, "playlist_edit_error")
                # エラーがあっても続行する
        
        # 各トラックを検索して追加
        logger.info(f"{len(tracks)}曲をQobuzプレイリストに追加します")
        success_count = 0
        
        for i, track in enumerate(tracks):
            search_query = f"{track['name']} {track['artist']}"
            logger.info(f"[{i+1}/{len(tracks)}] 検索中: {search_query}")
            
            # 検索ページに移動
            driver.get(f"https://www.qobuz.com/search?q={search_query}")
            time.sleep(3)  # 検索結果の読み込みを待つ
            save_screenshot(driver, f"search_{i+1}")
            
            try:
                # 検索結果の最初のトラックを見つける
                track_items = driver.find_elements(By.XPATH, "//div[contains(@class, 'track-item')]")
                
                if len(track_items) > 0:
                    logger.info(f"検索結果: {len(track_items)}曲見つかりました")
                    
                    # オプションメニューボタン（3点リーダーまたは類似アイコン）をクリック
                    try:
                        options_btn = track_items[0].find_element(By.XPATH, ".//button[contains(@class, 'more-options') or contains(@class, 'options')]")
                        driver.execute_script("arguments[0].scrollIntoView();", options_btn)
                        time.sleep(1)
                        options_btn.click()
                        logger.info("オプションボタンをクリックしました")
                        save_screenshot(driver, f"options_{i+1}")
                        time.sleep(1)
                    except Exception as e:
                        logger.error(f"オプションボタンクリックエラー: {e}")
                        continue
                    
                    # メニューからプレイリストに追加を選択
                    try:
                        add_to_playlist_option = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.XPATH, "//li[contains(text(), 'Add to playlist') or contains(text(), 'Add to a playlist')]"))
                        )
                        add_to_playlist_option.click()
                        logger.info("「プレイリストに追加」オプションをクリックしました")
                        save_screenshot(driver, f"add_to_playlist_{i+1}")
                        time.sleep(1)
                    except Exception as e:
                        logger.error(f"プレイリスト追加オプションクリックエラー: {e}")
                        continue
                    
                    # プレイリスト選択ダイアログからプレイリストを選択
                    try:
                        selectors = [
                            f"//div[contains(text(), '{playlist_name}')]",
                            f"//span[contains(text(), '{playlist_name}')]",
                            f"//li[contains(text(), '{playlist_name}')]"
                        ]
                        
                        playlist_option = None
                        for selector in selectors:
                            elements = driver.find_elements(By.XPATH, selector)
                            if len(elements) > 0:
                                playlist_option = elements[0]
                                logger.info(f"プレイリスト '{playlist_name}' が見つかりました (セレクタ: {selector})")
                                break
                        
                        if playlist_option:
                            playlist_option.click()
                            logger.info(f"プレイリスト '{playlist_name}' を選択しました")
                            time.sleep(1)
                            success_count += 1
                        else:
                            logger.error(f"プレイリスト '{playlist_name}' が見つかりませんでした")
                            save_screenshot(driver, f"playlist_not_found_{i+1}")
                            continue
                    except Exception as e:
                        logger.error(f"プレイリスト選択エラー: {e}")
                        continue
                    
                    logger.info(f"トラック追加成功: {search_query}")
                else:
                    logger.warning(f"検索結果が見つかりませんでした: {search_query}")
                    save_screenshot(driver, f"no_results_{i+1}")
            except Exception as e:
                logger.error(f"トラック追加に失敗しました: {search_query}, エラー: {e}")
                continue
            
            # サーバーに負荷をかけすぎないよう少し待機
            time.sleep(2)
        
        logger.info(f"処理完了: {success_count}/{len(tracks)}曲を追加しました")
    
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
        combined_playlist_id = os.environ.get("DISCOVER_WEEKLY_ID")  # ここでは統合プレイリストIDにDiscover Weekly IDを使用
        
        logger.info(f"設定された統合プレイリストID: {combined_playlist_id}")
        
        if combined_playlist_id:
            # 統合プレイリストの同期
            logger.info("統合プレイリストの同期を開始します")
            combined_tracks = get_playlist_tracks(sp, combined_playlist_id)
            if combined_tracks:
                update_qobuz_playlist("Spotify Discover & Release (Combined)", combined_tracks)
            else:
                logger.error("統合プレイリストのトラックが取得できませんでした")
        else:
            logger.error("DISCOVER_WEEKLY_ID（統合プレイリストID）が設定されていません")
        
        logger.info("全ての処理が完了しました")
    
    except Exception as e:
        logger.error(f"メイン処理でエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
