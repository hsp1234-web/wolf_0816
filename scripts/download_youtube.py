# 檔案: scripts/download_youtube.py
# 說明: 一個多模式的 YouTube 資源獲取工具。
#      可以根據模式下載字幕或純音訊。
import argparse
import sys
import os
import json
from pathlib import Path
import yt_dlp
import logging

# Setup logging
log_file = Path(__file__).resolve().parent / "downloader.log"
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stderr)])

def get_youtube_resource(url: str, mode: str, output_dir: str = "youtube_downloads") -> dict:
    """
    根據指定模式從 YouTube 下載資源 (字幕或音訊)。

    :param url: YouTube 影片的 URL。
    :param mode: 'subtitle' 或 'audio'。
    :param output_dir: 資源儲存的目錄路徑。
    :return: 一個包含資源類型和檔案路徑的字典。
    :raises Exception: 如果下載過程中發生任何錯誤或找不到資源。
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 基本 yt-dlp 選項
    base_ydl_opts = {
        'outtmpl': str(output_path / '%(id)s.%(ext)s'),
        'quiet': True,
        'encoding': 'utf-8',
        'add_header': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
        },
    }

    if mode == 'subtitle':
        # 字幕模式選項
        ydl_opts = base_ydl_opts.copy()
        ydl_opts.update({
            'writesubtitles': True,
            'subtitleslangs': ['en', 'zh-Hant', 'zh-Hans'], # 下載的語言順序
            'writeautomaticsub': True, # 如果沒有手動字幕，也下載自動字幕
            'skip_download': True, # 只下載字幕，不下載影片
            'outtmpl': str(output_path / '%(id)s'), # 檔名使用影片ID，副檔名由yt-dlp決定
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_id = info_dict.get('id')

            # 尋找下載的字幕檔案 (.vtt -> .txt)
            subtitle_file_vtt = None
            for lang in ['en', 'zh-Hant', 'zh-Hans']:
                 possible_file = output_path / f"{video_id}.{lang}.vtt"
                 if possible_file.exists():
                     subtitle_file_vtt = possible_file
                     break

            if not subtitle_file_vtt:
                raise FileNotFoundError("找不到任何可用語言的 VTT 字幕檔案。")

            # 將 VTT 轉換為純文字 TXT
            import re
            text_content = subtitle_file_vtt.read_text(encoding='utf-8')
            # 移除 VTT 標籤和時間戳
            text_lines = [line for line in text_content.splitlines() if '-->' not in line and line.strip() and not line.strip().isdigit()]
            text_only = "\n".join(text_lines)
            text_only = re.sub(r'<[^>]+>', '', text_only) # 移除 VTT 標籤，例如 <v>

            subtitle_file_txt = output_path / f"{video_id}.txt"
            subtitle_file_txt.write_text(text_only.strip(), encoding='utf-8')

            # 刪除原始 vtt 檔案
            subtitle_file_vtt.unlink()

            return {
                "type": "subtitle",
                "file_path": str(subtitle_file_txt.resolve())
            }

    elif mode == 'audio':
        # 音訊模式選項
        ydl_opts = base_ydl_opts.copy()
        ydl_opts.update({
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }],
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            predicted_filename = ydl.prepare_filename(info_dict)

            base, _ = os.path.splitext(predicted_filename)
            actual_filename = base + ".m4a"

            if not os.path.exists(actual_filename):
                raise FileNotFoundError(f"下載後找不到預期的音訊檔案: {actual_filename}")

            return {
                "type": "audio",
                "file_path": os.path.abspath(actual_filename)
            }
    else:
        raise ValueError(f"不支援的模式: {mode}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="根據指定模式從 YouTube 下載資源 (字幕或音訊)。",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""\
輸出說明:
  - 成功時: 在標準輸出 (stdout) 打印出一個 JSON 字串，包含 'type' 和 'file_path'。
  - 失敗時: 在標準錯誤 (stderr) 打印出錯誤訊息，並以非零狀態碼 (1) 退出。
"""
    )
    parser.add_argument("--url", required=True, help="YouTube 影片的 URL。")
    parser.add_argument("--mode", required=True, choices=['subtitle', 'audio', 'video'], help="要下載的資源類型。")
    parser.add_argument("--output-dir", default="youtube_downloads", help="資源儲存的目錄路徑。")

    args = parser.parse_args()

    logging.info(f"開始執行下載腳本，參數: URL={args.url}, Mode={args.mode}, Output={args.output_dir}")

    try:
        result = get_youtube_resource(args.url, args.mode, args.output_dir)
        logging.info(f"下載成功，結果: {result}")
        print(json.dumps(result))
        sys.exit(0)
    except Exception as e:
        logging.error(f"下載過程中發生未預期的錯誤: {e}", exc_info=True)
        # We still print to stderr for the parent process, but the detailed log is in the file.
        print(f"錯誤: {e}", file=sys.stderr)
        sys.exit(1)
