# -*- coding: utf-8 -*-
# tools/mock_gemini_processor.py
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
import re

# --- 日誌設定 (與原版一致) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
log = logging.getLogger('mock_gemini_processor')

def sanitize_filename(title: str, max_len: int = 60) -> str:
    """清理檔案名稱，移除無效字元並取代空格。"""
    if not title:
        title = "untitled_document"
    title = re.sub(r'[\\/*?:"<>|]', "_", title)
    title = title.replace(" ", "_")
    title = re.sub(r"_+", "_", title)
    title = title.strip('_')
    return title[:max_len]

def print_progress(status: str, detail: str, extra_data: dict = None):
    """以標準 JSON 格式輸出進度到 stderr。"""
    progress_data = {
        "type": "progress",
        "status": status,
        "detail": detail
    }
    if extra_data:
        progress_data.update(extra_data)
    print(json.dumps(progress_data), file=sys.stderr, flush=True)

def validate_key():
    """模擬 API 金鑰驗證。"""
    log.info("MOCK: Validating API key...")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        log.error("MOCK: GOOGLE_API_KEY environment variable not set.")
        print("API key not valid. Reason: GOOGLE_API_KEY environment variable not set.", file=sys.stderr, flush=True)
        sys.exit(1)

    if "invalid" in api_key:
        log.warning("MOCK: API key contains 'invalid', simulating failure.")
        print("API key not valid. Reason: Mock key is invalid.", file=sys.stderr, flush=True)
        sys.exit(1)

    log.info("MOCK: API key validation successful.")
    sys.exit(0)

def list_models():
    """模擬列出可用的 Gemini 模型。"""
    log.info("MOCK: Listing available models...")
    mock_models = [
        {"id": "models/gemini-pro-mock", "name": "Gemini Pro (模擬)"},
        {"id": "models/gemini-1.5-flash-mock", "name": "Gemini 1.5 Flash (模擬)"}
    ]
    print(json.dumps(mock_models), flush=True)

def process_audio_file(audio_path: Path, model: str, video_title: str, output_dir: Path, tasks: str, output_format: str):
    """模擬完整的音訊處理流程。"""
    log.info(f"MOCK: Starting processing for '{video_title}' with model '{model}'")
    start_time = time.time()

    # 首先檢查 API 金鑰，這是流程的第一步，模擬真實腳本的行為
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        log.error("MOCK: GOOGLE_API_KEY not set, aborting process.")
        # 模擬真實腳本的錯誤輸出
        raise ValueError("GOOGLE_API_KEY environment variable not set.")

    # 模擬上傳
    print_progress("uploading", f"正在上傳音訊檔案 {audio_path.name}...")
    time.sleep(1)
    print_progress("upload_complete", "音訊上傳成功。")

    # 模擬生成逐字稿和摘要
    print_progress("generating_transcript", "AI 正在生成摘要與逐字稿...")
    time.sleep(2)
    print_progress("transcript_generated", "摘要與逐字稿生成完畢。")

    sanitized_title = sanitize_filename(video_title)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    final_filename_base = f"{sanitized_title}_{timestamp}_AI_Report"
    output_path = None

    if output_format == 'html':
        print_progress("generating_html", "AI 正在美化格式並生成 HTML 報告...")
        time.sleep(1)
        output_path = output_dir / f"{final_filename_base}.html"
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-TW">
        <head>
            <meta charset="UTF-8">
            <title>模擬報告：{video_title}</title>
            <style>
                body {{ font-family: sans-serif; margin: 2em; }}
                h1, h2 {{ color: #333; }}
            </style>
        </head>
        <body>
            <h1>模擬 AI 分析報告</h1>
            <h2>標題：{video_title}</h2>
            <h3>摘要</h3>
            <p>這是一個由 mock_gemini_processor.py 生成的模擬摘要。</p>
            <h3>逐字稿</h3>
            <p>這是一份模擬的逐字稿內容，用於測試目的。</p>
        </body>
        </html>
        """
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        log.info(f"MOCK: HTML report saved to {output_path}")
        print_progress("html_generated", "HTML 報告生成完畢。")

    elif output_format == 'txt':
        output_path = output_dir / f"{final_filename_base}.txt"
        txt_content = f"""
        報告標題: {video_title}

        --- 重點摘要 ---
        這是一個由 mock_gemini_processor.py 生成的模擬摘要。

        --- 詳細逐字稿 ---
        這是一份模擬的逐字稿內容，用於測試目的。
        """
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(txt_content)
        log.info(f"MOCK: TXT report saved to {output_path}")

    else:
        raise ValueError(f"不支援的輸出格式: {output_format}")

    processing_duration = time.time() - start_time
    final_result = {
        "type": "result",
        "status": "completed",
        "output_path": str(output_path),
        "html_report_path": str(output_path) if output_format == 'html' else None,
        "video_title": video_title,
        "total_tokens_used": 1234, # 假資料
        "processing_duration_seconds": round(processing_duration, 2)
    }
    # 將最終結果輸出到 stdout
    print(json.dumps(final_result), flush=True)

def main():
    parser = argparse.ArgumentParser(description="[模擬] Gemini AI 處理工具。")
    parser.add_argument(
        "--command",
        type=str,
        default="process",
        choices=["process", "list_models", "validate_key"],
        help="要執行的操作。"
    )
    args, remaining_argv = parser.parse_known_args()

    if args.command == "list_models":
        list_models()
        return

    if args.command == "validate_key":
        validate_key()
        return

    if args.command == "process":
        process_parser = argparse.ArgumentParser()
        process_parser.add_argument("--command", help=argparse.SUPPRESS)
        process_parser.add_argument("--audio-file", type=str, required=True)
        process_parser.add_argument("--model", type=str, required=True)
        process_parser.add_argument("--video-title", type=str, required=True)
        process_parser.add_argument("--output-dir", type=str, required=True)
        process_parser.add_argument("--tasks", type=str, default="summary,transcript")
        process_parser.add_argument("--output-format", type=str, default="html", choices=["html", "txt"])

        process_args = process_parser.parse_args(remaining_argv)

        audio_path = Path(process_args.audio_file)
        output_dir = Path(process_args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            process_audio_file(
                audio_path=audio_path,
                model=process_args.model,
                video_title=process_args.video_title,
                output_dir=output_dir,
                tasks=process_args.tasks,
                output_format=process_args.output_format
            )
        except Exception as e:
            log.critical(f"MOCK: An error occurred: {e}", exc_info=True)
            print(json.dumps({"type": "result", "status": "failed", "error": str(e)}), flush=True)
            sys.exit(1)

if __name__ == "__main__":
    main()
