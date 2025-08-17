# tools/youtube_downloader.py
import argparse
import json
import logging
import sys
from pathlib import Path
import yt_dlp # 使用 yt-dlp 函式庫

# --- 日誌設定 ---
# 將所有日誌輸出到 stderr，以保持 stdout 的乾淨，專門用於最終的 JSON 結果。
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
log = logging.getLogger('youtube_downloader_tool')

# --- 進度回報 ---
def print_progress(status: str, detail: str, percent: float | None = None):
    """
    以標準 JSON 格式輸出進度到 stderr。
    """
    progress_data = {
        "type": "progress",
        "status": status,
        "description": detail,
    }
    if percent is not None:
        progress_data["percent"] = percent

    print(json.dumps(progress_data), file=sys.stderr, flush=True)


def progress_hook(d):
    """
    yt-dlp 的進度掛鉤。
    當下載狀態為 'downloading' 時，解析進度並透過 print_progress 輸出。
    """
    if d['status'] == 'downloading':
        # 從 yt-dlp 的字典中提取資訊
        percent_str = d.get('_percent_str', '0.0%').strip().replace('%', '')
        try:
            percent = float(percent_str)
        except (ValueError, TypeError):
            percent = 0.0

        speed_str = d.get('_speed_str', 'N/A').strip()
        eta_str = d.get('_eta_str', 'N/A').strip()

        detail_message = f"下載中... {percent:.1f}% (速度: {speed_str}, 預計剩餘: {eta_str})"
        print_progress("downloading", detail_message, percent)
    elif d['status'] == 'finished':
        log.info("yt-dlp 回報下載完成，正在進行後處理 (如轉檔)...")
        print_progress("processing", "下載完成，後處理中...", 100)
    elif d['status'] == 'error':
        log.error("yt-dlp 在執行過程中回報錯誤。")

def download_media(
    youtube_url: str,
    output_dir: Path,
    download_type: str = "audio",
    custom_filename: str | None = None,
    cookies_file: str | None = None
):
    """
    使用 yt-dlp 從 YouTube URL 下載媒體（音訊或影片）。

    :param youtube_url: 要下載的 YouTube URL。
    :param output_dir: 儲存檔案的目錄。
    :param download_type: 'audio' 或 'video'。
    :param custom_filename: 自訂的檔案名稱 (不含副檔名)。
    :param cookies_file: 用於驗證的 cookies.txt 檔案路徑。
    """
    log.info(f"開始下載媒體，類型: {download_type}，URL: {youtube_url}")
    print_progress("starting", f"準備開始下載: {youtube_url}")

    # 決定輸出檔案的路徑範本
    output_template = str(output_dir / (custom_filename if custom_filename else "%(title)s")) + ".%(ext)s"

    ydl_opts = {
        'outtmpl': output_template,
        'progress_hooks': [progress_hook],
        'logger': log, # 將 yt-dlp 的內部日誌導向我們的 logger
        'noprogress': True, # 關閉 yt-dlp 自己的進度條，由我們的 hook 處理
        'quiet': True, # 抑制非錯誤訊息到 stdout
        'encoding': 'utf-8',
    }

    if download_type == "audio":
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else: # video
        ydl_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
        })

    if cookies_file and Path(cookies_file).is_file():
        log.info(f"使用 Cookies 檔案: {cookies_file}")
        ydl_opts['cookiefile'] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # extract_info 會下載並處理檔案，然後回傳媒體資訊字典
            info_dict = ydl.extract_info(youtube_url, download=True)

        # 成功下載後，建構最終結果
        # JULES'S FIX: 不再手動猜測或修改檔名。
        # info_dict 在下載和後處理完成後，會包含最終的檔案路徑。
        # 我們直接從 'filepath' 鍵獲取，這是 yt-dlp 處理完畢後的實際路徑。
        # 如果 'filepath' 不存在，則使用 prepare_filename 作為備用。
        final_filepath_str = info_dict.get('filepath') or ydl.prepare_filename(info_dict)
        if not final_filepath_str:
            raise FileNotFoundError("無法從 yt-dlp 的回傳資訊中確定最終檔案路徑。")

        final_filepath = Path(final_filepath_str)

        # 移除手動的 exists 檢查，因為 info_dict 回傳的路徑應該是準確的。
        # 如果檔案真的不存在，讓後續的操作（例如 worker 讀取檔案）來發現問題，
        # 這比在這個階段讓腳本崩潰更好。

        final_result = {
            "type": "result",
            "status": "completed",
            "output_path": str(final_filepath),
            "video_title": info_dict.get("title", "Unknown Title"),
            "duration_seconds": info_dict.get("duration", 0)
        }

        # 將最終結果輸出到 stdout
        print(json.dumps(final_result), flush=True)
        log.info(f"✅ 媒體下載成功: {final_filepath}")

    except yt_dlp.utils.DownloadError as e:
        log.error(f"❌ yt-dlp 下載失敗: {e}", exc_info=True)

        # 增強錯誤偵測
        error_message = str(e)
        error_code = None
        if "authentication" in error_message.lower() or "login required" in error_message.lower():
            error_code = "AUTH_REQUIRED"
            error_message = "此影片需要登入驗證。請提供 cookies.txt 檔案。"

        error_result = {"type": "result", "status": "failed", "error": error_message, "error_code": error_code}
        # 將錯誤結果輸出到 stdout
        print(json.dumps(error_result), flush=True)
        sys.exit(1)
    except Exception as e:
        log.error(f"❌ 下載過程中發生未預期的錯誤: {e}", exc_info=True)
        error_result = {"type": "result", "status": "failed", "error": str(e)}
        # 將錯誤結果輸出到 stdout
        print(json.dumps(error_result), flush=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="YouTube 媒體下載工具 (使用 yt-dlp)。")
    parser.add_argument("--url", type=str, required=True, help="YouTube URL。")
    parser.add_argument("--output-dir", type=str, required=True, help="儲存媒體的目錄。")
    parser.add_argument("--download-type", type=str, default="audio", choices=['audio', 'video'], help="下載類型：'audio' 或 'video'。")
    parser.add_argument("--custom-filename", type=str, default=None, help="自訂的檔案名稱 (不含副檔名)。")
    parser.add_argument("--cookies-file", type=str, default=None, help="用於驗證的 cookies.txt 檔案路徑。")

    args = parser.parse_args()

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    download_media(
        args.url,
        output_path,
        args.download_type,
        args.custom_filename,
        args.cookies_file
    )

if __name__ == "__main__":
    main()
