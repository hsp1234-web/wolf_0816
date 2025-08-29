import argparse
import json
import time
import sys
from pathlib import Path

def check_model(model_size):
    """Simulates checking if a model exists. Always returns true."""
    print("exists", flush=True)

def download_model(model_size):
    """Simulates downloading a model with progress updates."""
    print(json.dumps({"type": "progress", "percent": 10, "description": "開始下載模擬模型..."}), file=sys.stdout, flush=True)
    time.sleep(0.2)
    print(json.dumps({"type": "progress", "percent": 50, "description": "正在解壓縮..."}), file=sys.stdout, flush=True)
    time.sleep(0.2)
    print(json.dumps({"type": "progress", "percent": 100, "description": "安裝完成"}), file=sys.stdout, flush=True)
    time.sleep(0.1)
    # The main server looks for a final status message on stdout, not here.
    # This script just needs to exit successfully.

def transcribe_audio(audio_file, output_file, model_size, language, beam_size):
    """Simulates audio transcription with progress updates."""
    # 1. Simulate initial delay
    time.sleep(0.5)

    # 2. Simulate transcription segments
    segments = [
        {"start": 0.0, "end": 2.5, "text": "你好，歡迎使用這個模擬的轉錄系統。"},
        {"start": 2.5, "end": 5.0, "text": "這是一個測試，用於驗證端對端流程。"},
        {"start": 5.0, "end": 6.0, "text": "轉錄完成！"},
    ]

    full_transcript = ""
    for segment in segments:
        print(json.dumps({
            "type": "segment",
            "start": segment["start"],
            "end": segment["end"],
            "text": segment["text"]
        }), file=sys.stdout, flush=True)
        full_transcript += segment["text"] + " "
        time.sleep(0.3)

    # 3. Write the final transcript to the output file
    Path(output_file).write_text(full_transcript.strip(), encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description="Mock Transcriber Tool")
    parser.add_argument("--command", required=True, choices=["check", "download", "transcribe"])
    parser.add_argument("--model_size", default="tiny")
    parser.add_argument("--audio_file")
    parser.add_argument("--output_file")
    parser.add_argument("--language")
    parser.add_argument("--beam_size", type=int, default=5)

    args = parser.parse_args()

    if args.command == "check":
        check_model(args.model_size)
    elif args.command == "download":
        download_model(args.model_size)
    elif args.command == "transcribe":
        if not args.audio_file or not args.output_file:
            print("Error: --audio_file and --output_file are required for transcribe command.", file=sys.stderr)
            sys.exit(1)
        transcribe_audio(args.audio_file, args.output_file, args.model_size, args.language, args.beam_size)

    sys.exit(0)

if __name__ == "__main__":
    main()
