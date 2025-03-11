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
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=os.environ["SPOTIFY_CLIENT_ID"],
            client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
            redirect_uri="http://localhost:8888/callback",
            scope=scope,
            open_browser=False))  # GitHubアクションで実行する場合はブラウザを開かない
        return sp
    except Exception as e:
        logger.error(f"Spotify APIの初期化に失敗しました: {e}")
        raise

# プレイリストIDを取得する関数
def get_playlist_id_by_name(sp, name):
    try:
        results = sp.current_user_playlists()
        for playlist in results['items']:
            if name in playlist['name']:
                return playlist['id']
        return None
    except Exception as e:
        logger.error(f"プレイリスト '{name}' のID取得に失敗しました: {e}")
        return None

# プレイリストのトラック情報を取得する関数
def get_playlist_tracks(sp, playlist_id):
    try:
        logger.info(f"プレイリスト {playlist_id} のトラック情報を取得中...")
        results = sp.playlist_items(playlist_id)
        tracks = []
        for item in results['items']:
            if item['track'] is None:
                continue
            track = item['track']
            tracks.append({
                'name': track['name'],
                'artist': track['artists'][0]['name'],
                'album': track['album']['name'] if 'album' in track else ''
            })
        logger.info(f"{len(tracks)}曲の情報を取得しました")
        return tracks
    except Exception as e:
        logger.error(f"トラック情報の取得に失敗しました: {e}")
        return []

# Qobuzプレイリストを更新する関数
def update_qobuz_playlist(playlist_name, tracks):
    # Chromeの設定
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # ヘッドレスモード
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Chromeドライバーセットアップ
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        logger.info(f"Qobuzにログイン中...")
        # Qobuzにログイン
        driver.get("https://www.qobuz.com/login")
        
        # ログインフォームの読み込みを待つ
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "email"))
        )
        
        # ログイン情報を入力
        driver.find_element(By.ID, "email").send_keys(os.environ["QOBUZ_EMAIL"])
        driver.find_element(By.ID, "password").send_keys(os.environ["QOBUZ_PASSWORD"])
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # ログイン成功を確認
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'user-menu')]"))
        )
        logger.info("ログイン成功")
        
        # マイプレイリスト画面に移動
        driver.get("https://www.qobuz.com/my-profile/playlists")
        time.sleep(3)  # ページの読み込みを待つ
        
        # プレイリストの存在確認
        logger.info(f"プレイリスト '{playlist_name}' を確認中...")
        try:
            playlist_found = driver.find_elements(By.XPATH, f"//div[contains(text(), '{playlist_name}')]")
            playlist_exists = len(playlist_found) > 0
        except:
            playlist_exists = False
        
        if not playlist_exists:
            # 新規プレイリスト作成
            logger.info(f"プレイリスト '{playlist_name}' を新規作成します")
            driver.find_element(By.XPATH, "//button[contains(text(), 'Create playlist') or contains(text(), 'Create a playlist')]").click()
            
            # プレイリスト名入力フォームが表示されるまで待つ
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Playlist name' or @placeholder='Name']"))
            )
            
            # プレイリスト名を入力して作成
            playlist_name_input = driver.find_element(By.XPATH, "//input[@placeholder='Playlist name' or @placeholder='Name']")
            playlist_name_input.clear()
            playlist_name_input.send_keys(playlist_name)
            
            # 作成ボタンをクリック
            create_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Create') and not(contains(text(), 'Create playlist'))]")
            create_button.click()
            time.sleep(3)
        else:
            # 既存プレイリストをクリック
            logger.info(f"既存のプレイリスト '{playlist_name}' を編集します")
            driver.find_element(By.XPATH, f"//div[contains(text(), '{playlist_name}')]").click()
            time.sleep(3)
            
            # プレイリストを空にする（任意）
            try:
                # プレイリストページに移動した確認
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'playlist-header')]"))
                )
                
                # トラックがあるか確認
                tracks_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'track-item')]")
                if len(tracks_elements) > 0:
                    logger.info("既存のトラックを削除中...")
                    
                    # 全選択ボタンをクリック
                    select_all_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'select-all')]")
                    select_all_btn.click()
                    time.sleep(1)
                    
                    # 削除ボタンをクリック
                    delete_btn = driver.find_element(By.XPATH, "//button[contains(@class, 'delete') or contains(text(), 'Delete')]")
                    delete_btn.click()
                    time.sleep(1)
                    
                    # 確認ダイアログのOKボタンをクリック
                    confirm_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'OK') or contains(text(), 'Confirm')]")
                    confirm_btn.click()
                    time.sleep(2)
            except Exception as e:
                logger.warning(f"プレイリストの曲を削除できませんでした: {e}")
                # 削除に失敗しても続行する
        
        # 各トラックを検索して追加
        logger.info(f"{len(tracks)}曲をQobuzプレイリストに追加します")
        success_count = 0
        
        for i, track in enumerate(tracks):
            search_query = f"{track['name']} {track['artist']}"
            logger.info(f"[{i+1}/{len(tracks)}] 検索中: {search_query}")
            
            # 検索ページに移動
            driver.get(f"https://www.qobuz.com/search?q={search_query}")
            time.sleep(3)  # 検索結果の読み込みを待つ
            
            try:
                # 検索結果の最初のトラックを見つける
                track_items = driver.find_elements(By.XPATH, "//div[contains(@class, 'track-item')]")
                
                if len(track_items) > 0:
                    # オプションメニューボタン（3点リーダーまたは類似アイコン）をクリック
                    options_btn = track_items[0].find_element(By.XPATH, ".//button[contains(@class, 'more-options') or contains(@class, 'options')]")
                    options_btn.click()
                    time.sleep(1)
                    
                    # メニューからプレイリストに追加を選択
                    add_to_playlist_option = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, "//li[contains(text(), 'Add to playlist') or contains(text(), 'Add to a playlist')]"))
                    )
                    add_to_playlist_option.click()
                    time.sleep(1)
                    
                    # プレイリスト選択ダイアログからプレイリストを選択
                    playlist_option = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, f"//div[contains(text(), '{playlist_name}')]"))
                    )
                    playlist_option.click()
                    time.sleep(1)
                    
                    success_count += 1
                    logger.info(f"トラック追加成功: {search_query}")
                else:
                    logger.warning(f"検索結果が見つかりませんでした: {search_query}")
            except Exception as e:
                logger.error(f"トラック追加に失敗しました: {search_query}, エラー: {e}")
                continue
            
            # サーバーに負荷をかけすぎないよう少し待機
            time.sleep(2)
        
        logger.info(f"処理完了: {success_count}/{len(tracks)}曲を追加しました")
    
    except Exception as e:
        logger.error(f"Qobuzプレイリスト更新中にエラーが発生しました: {e}")
    finally:
        driver.quit()

# メイン処理
def main():
    try:
        # Spotify API初期化
        sp = initialize_spotify()
        
        # プレイリストIDの取得
        # 環境変数で指定されていればそれを使う、指定がなければ名前で検索
        discover_weekly_id = os.environ.get("DISCOVER_WEEKLY_ID")
        release_radar_id = os.environ.get("RELEASE_RADAR_ID")
        
        if not discover_weekly_id:
            discover_weekly_id = get_playlist_id_by_name(sp, "Discover Weekly")
        if not release_radar_id:
            release_radar_id = get_playlist_id_by_name(sp, "Release Radar")
        
        if not discover_weekly_id:
            logger.error("Discover Weeklyプレイリストが見つかりませんでした")
        else:
            # Discover Weeklyの同期
            logger.info("Discover Weeklyの同期を開始します")
            discover_tracks = get_playlist_tracks(sp, discover_weekly_id)
            update_qobuz_playlist("Discover Weekly (Spotify)", discover_tracks)
        
        if not release_radar_id:
            logger.error("Release Radarプレイリストが見つかりませんでした")
        else:
            # Release Radarの同期
            logger.info("Release Radarの同期を開始します")
            release_tracks = get_playlist_tracks(sp, release_radar_id)
            update_qobuz_playlist("Release Radar (Spotify)", release_tracks)
        
        logger.info("全ての処理が完了しました")
    
    except Exception as e:
        logger.error(f"メイン処理でエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
