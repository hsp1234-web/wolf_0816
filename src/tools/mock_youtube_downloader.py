import argparse
import json
import time
import sys
from pathlib import Path
import uuid

def download_url(url, output_dir, custom_filename, download_type, cookies_file):
    """Simulates downloading a URL and returns a path to a fake file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Simulate progress to stderr
    print(json.dumps({"type": "progress", "percent": 0, "description": "正在準備下載..."}), file=sys.stderr, flush=True)
    time.sleep(0.2)
    print(json.dumps({"type": "progress", "percent": 50, "description": "模擬下載中..."}), file=sys.stderr, flush=True)
    time.sleep(0.3)

    # Create a dummy output file
    extension = ".mp4" if download_type == "video" else ".mp3"
    if custom_filename:
        # Use custom filename but ensure it's safe
        safe_filename = "".join(c if c.isalnum() else "_" for c in custom_filename)
        final_filename = safe_filename + extension
    else:
        # Generate a unique name if no custom name is provided
        final_filename = f"mock_download_{uuid.uuid4().hex[:8]}{extension}"

    output_path = output_dir / final_filename

    # Create a small dummy file
    with open(output_path, "w") as f:
        f.write("This is a mock media file.")

    print(json.dumps({"type": "progress", "percent": 100, "description": "下載完成"}), file=sys.stderr, flush=True)

    # Output the result JSON to stdout
    result = {
        "output_path": str(output_path),
        "video_title": custom_filename or Path(final_filename).stem,
        "original_url": url,
        "download_type": download_type
    }
    print(json.dumps(result), flush=True)

def main():
    parser = argparse.ArgumentParser(description="Mock YouTube Downloader Tool")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--custom-filename", default=None)
    parser.add_argument("--download-type", default="audio", choices=["audio", "video"])
    parser.add_argument("--cookies-file", default=None) # We accept but ignore this in mock mode

    args = parser.parse_args()

    download_url(args.url, args.output_dir, args.custom_filename, args.download_type, args.cookies_file)

    sys.exit(0)

if __name__ == "__main__":
    main()
