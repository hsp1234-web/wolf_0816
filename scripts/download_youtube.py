# 檔案: scripts/download_youtube.py
# 說明: 一個獨立的、可透過命令列執行的 YouTube 影片下載工具。
import argparse
import sys
import os
from pathlib import Path
import yt_dlp

def download_video(url: str, output_dir: str) -> str:
    """
    使用 yt-dlp 下載指定的 YouTube URL，並將影片儲存到指定的目錄。

    :param url: YouTube 影片的 URL。
    :param output_dir: 影片儲存的目錄路徑。
    :return: 下載完成的影片檔案的絕對路徑。
    :raises Exception: 如果下載過程中發生任何錯誤。
    """
    try:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 設定 yt-dlp 選項
        # 我們希望下載單一影片檔案，格式為 mp4
        # 檔案名稱使用影片標題
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': str(output_path / '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'quiet': True, # 抑制不必要的日誌
            'encoding': 'utf-8',
            # 模擬瀏覽器行為，避免被 YouTube 阻擋 (HTTP 403)
            'add_header': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'Accept-Language': 'en-US,en;q=0.9',
            },
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 獲取影片資訊，但不下載
            info_dict = ydl.extract_info(url, download=False)
            # 根據資訊建構預期的檔案路徑
            # ydl.prepare_filename 在 download=False 時可用來預測檔名
            predicted_filename = ydl.prepare_filename(info_dict)

            # 執行下載
            ydl.download([url])

        # 檢查檔案是否存在
        if not os.path.exists(predicted_filename):
            # 有時候副檔名可能不如預期，做一次簡易的檢查
            base_name = os.path.splitext(predicted_filename)[0]
            if os.path.exists(base_name + ".mp4"):
                 predicted_filename = base_name + ".mp4"
            elif os.path.exists(base_name + ".mkv"):
                 predicted_filename = base_name + ".mkv"
            else:
                raise FileNotFoundError(f"下載後找不到預期的檔案: {predicted_filename}")

        # 返回絕對路徑
        return os.path.abspath(predicted_filename)

    except Exception as e:
        # 將 yt-dlp 的錯誤或其他例外重新拋出
        raise Exception(f"yt-dlp 執行失敗: {e}") from e

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="下載指定的 YouTube 影片。",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""\
輸出說明:
  - 成功時: 在標準輸出 (stdout) 打印出影片檔案的「絕對路徑」。
  - 失敗時: 在標準錯誤 (stderr) 打印出錯誤訊息，並以非零狀態碼 (1) 退出。
"""
    )
    parser.add_argument("--url", required=True, help="YouTube 影片的 URL。")
    parser.add_argument("--output-dir", required=True, help="影片儲存的目錄。")
    args = parser.parse_args()

    try:
        # 執行下載
        file_path = download_video(args.url, args.output_dir)
        # 成功時，在 stdout 打印結果路徑
        print(file_path)
        sys.exit(0)
    except Exception as e:
        # 失敗時，在 stderr 打印錯誤訊息，並以錯誤碼退出
        print(f"下載失敗: {e}", file=sys.stderr)
        sys.exit(1)
