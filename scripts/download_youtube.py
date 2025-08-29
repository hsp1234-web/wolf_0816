# 檔案: scripts/download_youtube.py
# 說明: 一個多模式的 YouTube 資源獲取工具 v2。
#      - 支援影片、音訊、字幕下載
#      - 透過 stderr 即時回報 JSON 格式的進度
#      - 捕捉常見錯誤並回報標準化的錯誤訊息
import argparse
import sys
import os
import json
from pathlib import Path
import yt_dlp
import logging
import re

# --- 日誌設定 ---
# 將日誌寫入與腳本相同的目錄，以便除錯
log_file = Path(__file__).resolve().parent / "downloader.log"
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(log_file)])

# --- 錯誤處理 ---
# 將 yt-dlp 的常見錯誤訊息映射為友善的繁體中文提示
ERROR_MAP = {
    "HTTP Error 403: Forbidden": "存取被拒 (403)，此影片可能受到版權保護或有地區限制。",
    "HTTP Error 429: Too Many Requests": "請求過於頻繁 (429)，請稍後再試。",
    "Private video": "此為私人影片，需要登入才能存取。",
    "Video unavailable": "影片不可用，可能已被刪除或設為私人。",
    "This video is unavailable": "影片不可用，可能已被刪除或設為私人。",
    "Login required": "此內容需要登入才能查看，請嘗試使用 cookies.txt 功能。"
}

def find_friendly_error(stderr_text):
    for key, value in ERROR_MAP.items():
        if key in stderr_text:
            return value
    return "發生未知的下載錯誤，請檢查日誌以獲取詳細資訊。"

# --- yt-dlp 進度掛鉤 ---
def progress_hook(d):
    """yt-dlp 的進度回呼函式，將進度以 JSON 格式打印到 stderr。"""
    if d['status'] == 'downloading':
        # 建立進度回報的 JSON 物件
        progress_info = {
            "type": "progress",
            "status": "downloading",
            "percent": float(d.get('_percent_str', '0%').strip('%')),
            "total_bytes": d.get('total_bytes'),
            "downloaded_bytes": d.get('downloaded_bytes'),
            "speed": d.get('speed'),
            "eta": d.get('eta'),
            "filename": d.get('filename')
        }
        # 打印到 stderr，讓主程序可以捕捉
        print(json.dumps(progress_info), file=sys.stderr, flush=True)
    elif d['status'] == 'finished':
        # 標記下載階段完成
        print(json.dumps({"type": "progress", "status": "processing"}), file=sys.stderr, flush=True)


def get_youtube_resource(url: str, mode: str, output_dir_str: str, custom_filename_base: str = None) -> dict:
    output_path = Path(output_dir_str)
    output_path.mkdir(parents=True, exist_ok=True)

    # 檔名模板
    # 如果有自訂檔名，就使用它，否則使用影片標題
    filename_template = f"{custom_filename_base}.%(ext)s" if custom_filename_base else "%(title)s.%(ext)s"
    outtmpl = str(output_path / filename_template)

    base_ydl_opts = {
        'outtmpl': outtmpl,
        'quiet': True,
        'encoding': 'utf-8',
        'add_header': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
        },
        'progress_hooks': [progress_hook],
        'noprogress': True, # 關閉 yt-dlp 自己的進度條，使用我們的 hook
    }

    ydl_opts = base_ydl_opts.copy()

    if mode == 'video':
        ydl_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        })
    elif mode == 'audio':
        ydl_opts.update({
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }],
        })
    elif mode == 'subtitle':
        ydl_opts.update({
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'zh-Hant', 'zh-Hans'],
            'skip_download': True,
            'outtmpl': str(output_path / (custom_filename_base if custom_filename_base else '%(title)s')),
        })
    else:
        raise ValueError(f"不支援的模式: {mode}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        final_filepath_str = ydl.prepare_filename(info_dict)

        # 處理字幕的特殊情況
        if mode == 'subtitle':
            subtitle_file_vtt = None
            for lang in ['en', 'zh-Hant', 'zh-Hans']:
                possible_file = Path(final_filepath_str + f".{lang}.vtt")
                if possible_file.exists():
                    subtitle_file_vtt = possible_file
                    break

            if not subtitle_file_vtt:
                raise FileNotFoundError("找不到任何可用語言的 VTT 字幕檔案。")

            text_content = subtitle_file_vtt.read_text(encoding='utf-8')
            text_lines = [line for line in text_content.splitlines() if '-->' not in line and line.strip() and not line.strip().isdigit()]
            text_only = "\n".join(text_lines)
            text_only = re.sub(r'<[^>]+>', '', text_only)

            # 輸出為 Markdown 檔案
            final_filepath = subtitle_file_vtt.with_suffix('.md')
            final_filepath.write_text(f"# {info_dict.get('title')}\n\n{text_only.strip()}", encoding='utf-8')
            subtitle_file_vtt.unlink() # 刪除原始 vtt
        else:
            # 對於音訊和影片，yt-dlp 會自動處理副檔名
            # 我們需要找到實際產生的檔案
            if not Path(final_filepath_str).exists():
                 # 如果後處理器改變了副檔名 (例如 audio)
                 base, _ = os.path.splitext(final_filepath_str)
                 if mode == 'audio':
                     final_filepath_str = base + ".m4a"
                 elif mode == 'video':
                     final_filepath_str = base + ".mp4"

            if not os.path.exists(final_filepath_str):
                 raise FileNotFoundError(f"下載後找不到預期的檔案: {final_filepath_str}")
            final_filepath = Path(final_filepath_str)

    return {
        "type": mode,
        "file_path": str(final_filepath.resolve()),
        "video_title": info_dict.get('title', '無標題'),
        "original_url": url,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="多模式媒體下載工具 v2。")
    parser.add_argument("--url", required=True, help="媒體的 URL。")
    parser.add_argument("--mode", required=True, choices=['video', 'audio', 'subtitle'], help="要下載的資源類型。")
    parser.add_argument("--output-dir", default="youtube_downloads", help="資源儲存的目錄路徑。")
    parser.add_argument("--custom-filename", default=None, help="自訂的檔案名稱 (不含副檔名)。")

    args = parser.parse_args()

    logging.info(f"開始執行下載腳本 v2，參數: URL={args.url}, Mode={args.mode}, Output={args.output_dir}")

    try:
        result = get_youtube_resource(args.url, args.mode, args.output_dir, args.custom_filename)
        logging.info(f"下載成功，結果: {result}")
        print(json.dumps(result))
        sys.exit(0)
    except Exception as e:
        stderr_text = str(e)
        friendly_error = find_friendly_error(stderr_text)

        logging.error(f"下載過程中發生錯誤: {stderr_text}", exc_info=True)

        # 將標準化的錯誤訊息輸出到 stderr
        error_response = {
            "type": "error",
            "message": friendly_error,
            "original_error": stderr_text
        }
        print(json.dumps(error_response), file=sys.stderr)
        sys.exit(1)
