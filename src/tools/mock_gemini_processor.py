import argparse
import json
import time
import sys
import os
from pathlib import Path

def validate_key():
    """Simulates validating a Google API key. Succeeds if the key is not empty."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key and "valid" in api_key.lower():
         # Allow a way to test failure for E2E tests
        if "invalid" in api_key.lower():
            print("API key not valid. Please pass a valid API key.", file=sys.stderr)
            sys.exit(1)
        # Success
        sys.exit(0)
    else:
        # Fail if key is empty or doesn't contain 'valid'
        print("API key not valid. Please pass a valid API key.", file=sys.stderr)
        sys.exit(1)

def list_models():
    """Returns a fixed list of mock models."""
    models = {
        "models": [
            {"id": "gemini-pro-mock", "name": "Gemini Pro (模擬)"},
            {"id": "gemini-1.5-flash-mock", "name": "Gemini 1.5 Flash (模擬)"},
            {"id": "gemini-ultra-mock", "name": "Gemini Ultra (模擬)"}
        ]
    }
    print(json.dumps(models))

def process_file(audio_file, model, output_dir, video_title, tasks, output_format):
    """Simulates processing a file to generate a report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sanitized_title = "".join(c if c.isalnum() else "_" for c in video_title)
    base_filename = f"{sanitized_title}_AI_Report"

    # Simulate progress
    print(json.dumps({"type": "progress", "status": "generating_transcript", "detail": "正在生成逐字稿..."}), file=sys.stderr, flush=True)
    time.sleep(0.5)
    print(json.dumps({"type": "progress", "status": "generating_summary", "detail": "正在生成摘要..."}), file=sys.stderr, flush=True)
    time.sleep(0.5)

    result = {
        "video_title": video_title,
        "model_used": model,
        "processing_duration_seconds": 1.23,
        "total_tokens_used": 456,
        "output_path": None,
        "html_report_path": None,
        "pdf_report_path": None # Not implemented in mock
    }

    if output_format == "html":
        report_content = f"""
        <html>
            <head><title>AI報告: {video_title}</title></head>
            <body>
                <h1>AI分析報告: {video_title}</h1>
                <p><strong>使用模型:</strong> {model}</p>
                {'<h2>重點摘要</h2><p>這是一段由模擬系統產生的影片摘要。</p>' if 'summary' in tasks else ''}
                {'<h2>逐字稿</h2><p>這是模擬的逐字稿內容，用於測試目的。</p>' if 'transcript' in tasks else ''}
                {'<h2>繁中翻譯</h2><p>這是模擬的繁體中文翻譯。</p>' if 'translate_zh' in tasks else ''}
            </body>
        </html>
        """
        report_path = output_dir / f"{base_filename}.html"
        report_path.write_text(report_content, encoding='utf-8')
        result["output_path"] = str(report_path)
        result["html_report_path"] = str(report_path)
    else: # txt
        report_content = f"AI分析報告: {video_title}\n\n"
        if 'summary' in tasks:
            report_content += "--- 重點摘要 ---\n這是一段由模擬系統產生的影片摘要。\n\n"
        if 'transcript' in tasks:
            report_content += "--- 逐字稿 ---\n這是模擬的逐字稿內容，用於測試目的。\n\n"
        report_path = output_dir / f"{base_filename}.txt"
        report_path.write_text(report_content, encoding='utf-8')
        result["output_path"] = str(report_path)

    print(json.dumps(result))

def main():
    parser = argparse.ArgumentParser(description="Mock Gemini Processor Tool")
    parser.add_argument("--command", required=True, choices=["validate_key", "list_models", "process"])
    parser.add_argument("--audio-file")
    parser.add_argument("--model")
    parser.add_argument("--output-dir")
    parser.add_argument("--video-title")
    parser.add_argument("--tasks", default="summary,transcript")
    parser.add_argument("--output-format", default="html")

    args = parser.parse_args()

    if args.command == "validate_key":
        validate_key()
    elif args.command == "list_models":
        list_models()
    elif args.command == "process":
        process_file(args.audio_file, args.model, args.output_dir, args.video_title, args.tasks, args.output_format)

    sys.exit(0)

if __name__ == "__main__":
    main()
