# -*- coding: utf-8 -*-
# tools/gemini_processor.py
import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# --- 日誌設定 ---
# JULES'S FIX: Redirect all logging to stderr to keep stdout clean for the final JSON result.
# This is crucial to prevent JSONDecodeError in the parent process (api_server.py).
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    # 將日誌和進度訊息導向標準錯誤流
    stream=sys.stderr
)
log = logging.getLogger('gemini_processor_tool')

# --- 輔助函式 (來自 damo.py) ---
def sanitize_filename(title: str, max_len: int = 60) -> str:
    """清理檔案名稱，移除無效字元並取代空格。"""
    if not title:
        title = "untitled_document"
    # 移除非法字元
    title = re.sub(r'[\\/*?:"<>|]', "_", title)
    title = title.replace(" ", "_")
    # 將多個底線縮減為一個
    title = re.sub(r"_+", "_", title)
    # 去除開頭和結尾的底線
    title = title.strip('_')
    return title[:max_len]

def print_progress(status: str, detail: str, extra_data: dict = None):
    """
    JULES'S FIX: 以標準 JSON 格式輸出進度到 stderr。
    這確保了 stdout 保持乾淨，只用於傳遞最終結果。
    """
    progress_data = {
        "type": "progress",
        "status": status,
        "detail": detail
    }
    if extra_data:
        progress_data.update(extra_data)
    # 將進度訊息輸出到 stderr
    print(json.dumps(progress_data), file=sys.stderr, flush=True)

# --- 提示詞管理 ---
# 取得此檔案所在的目錄，並建立 prompts.json 的路徑
PROMPTS_FILE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "default_prompts.json"

def load_prompts() -> dict:
    """從 prompts/default_prompts.json 載入所有提示詞。"""
    try:
        with open(PROMPTS_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.critical(f"🔴 無法載入或解析提示詞檔案: {PROMPTS_FILE_PATH}。錯誤: {e}", exc_info=True)
        # 在無法載入提示詞時，系統無法運作，應直接退出
        sys.exit(1)

# 在模組載入時就讀取所有提示詞
ALL_PROMPTS = load_prompts()


import google.generativeai as genai

# 問題四：定義錯誤轉譯對照表
GEMINI_ERROR_MAP = {
    "SAFETY": "處理失敗：內容可能涉及安全或敏感議題。",
    "RECITATION": "處理失敗：內容可能引用了受版權保護的資料。",
    "OTHER": "處理失敗：因未知的模型內部原因終止。"
}

def get_error_message_from_response(response):
    """從 Gemini API 回應中解析出使用者易於理解的錯誤訊息。"""
    try:
        # 優先檢查是否有明確的阻擋原因
        if response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason.name
            return GEMINI_ERROR_MAP.get(reason, f"請求被未知原因阻擋: {reason}")

        # 接著檢查候選內容的完成原因是否正常
        candidate = response.candidates[0]
        if candidate.finish_reason.name not in ("STOP", "MAX_TOKENS"):
            reason = candidate.finish_reason.name
            return GEMINI_ERROR_MAP.get(reason, f"處理異常終止: {reason}")
    except (AttributeError, IndexError):
        # 如果回應的結構不符合預期，則不進行處理
        return None
    return None

# --- 核心 Gemini 處理函式 ---

def list_models():
    """列出可用的 Gemini 模型並以 JSON 格式輸出。"""
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set.")
        genai.configure(api_key=api_key)

        models_list = []
        for m in genai.list_models():
            # 我們只關心支援 'generateContent' 且可用於 'models/' 的模型
            if 'generateContent' in m.supported_generation_methods:
                # 簡化輸出，只包含名稱和顯示名稱
                 models_list.append({
                     "id": m.name,
                     "name": m.display_name
                 })
        print(json.dumps(models_list), flush=True)
    except Exception as e:
        log.critical(f"🔴 Failed to list models: {e}", exc_info=True)
        # 將錯誤訊息輸出到 stderr，以便父程序擷取
        print(f"Error listing models: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

def validate_key():
    """
    僅驗證 API 金鑰的有效性。
    透過一個輕量級的操作（如列出模型）來實現。
    如果成功，以 exit code 0 退出。
    如果失敗，以 non-zero exit code 退出，並在 stderr 中提供錯誤訊息。
    """
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set.")
        genai.configure(api_key=api_key)

        # list_models 是一個相對輕量級的驗證操作
        genai.list_models()
        log.info("✅ API key validation successful.")
        sys.exit(0)
    except Exception as e:
        # 將具體的錯誤訊息輸出到 stderr
        # Google API 錯誤通常有自己的詳細描述
        print(f"API key not valid. Reason: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


def upload_to_gemini(genai_module, audio_path: Path, display_filename: str):
    """上傳檔案至 Gemini Files API。"""
    log.info(f"☁️ Uploading '{display_filename}' to Gemini Files API...")
    print_progress("uploading", f"正在上傳音訊檔案 {display_filename}...")
    try:
        # 偵測 MIME 類型
        ext = audio_path.suffix.lower()
        mime_map = {'.mp3': 'audio/mp3', '.m4a': 'audio/m4a', '.aac': 'audio/aac',
                    '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.flac': 'audio/flac',
                    '.webm': 'audio/webm', '.mp4': 'audio/mp4'}
        mime_type = mime_map.get(ext, 'application/octet-stream')
        if mime_type in ['audio/m4a', 'audio/mp4']:
            mime_type = 'audio/aac' # Gemini 偏好 aac

        audio_file_resource = genai_module.upload_file(
            path=str(audio_path),
            display_name=display_filename,
            mime_type=mime_type
        )
        log.info(f"✅ Upload successful. Gemini File URI: {audio_file_resource.uri}")
        print_progress("upload_complete", "音訊上傳成功。")
        return audio_file_resource
    except Exception as e:
        log.critical(f"🔴 Failed to upload file to Gemini: {e}", exc_info=True)
        raise

def get_summary_and_transcript(genai_module, gemini_file_resource, model_api_name: str, video_title: str, original_filename: str):
    """
    使用 Gemini 模型生成摘要與逐字稿。
    JULES'S UPDATE: Now returns the full response object for token counting.
    """
    log.info(f"🤖 Requesting summary and transcript from model '{model_api_name}'...")
    print_progress("generating_transcript", "AI 正在生成摘要與逐字稿...")
    prompt = ALL_PROMPTS['get_summary_and_transcript'].format(original_filename=original_filename, video_title=video_title)
    try:
        model = genai_module.GenerativeModel(model_api_name)
        response = model.generate_content([prompt, gemini_file_resource], request_options={'timeout': 3600})
        full_response_text = response.text

        summary_match = re.search(r"\[重點摘要開始\](.*?)\[重點摘要結束\]", full_response_text, re.DOTALL)
        summary_text = summary_match.group(1).strip() if summary_match else "未擷取到重點摘要。"

        transcript_match = re.search(r"\[詳細逐字稿開始\](.*?)\[詳細逐字稿結束\]", full_response_text, re.DOTALL)
        transcript_text = transcript_match.group(1).strip() if transcript_match else "未擷取到詳細逐字稿。"

        if "未擷取到" in summary_text and "未擷取到" in transcript_text and "---[逐字稿分隔線]---" not in full_response_text:
            transcript_text = full_response_text
            summary_text = "（自動摘要失敗，請參考下方逐字稿自行整理）"

        log.info("✅ Successfully generated summary and transcript.")
        print_progress("transcript_generated", "摘要與逐字稿生成完畢。")
        return summary_text, transcript_text, response
    except Exception as e:
        log.critical(f"🔴 Failed to get summary/transcript from Gemini: {e}", exc_info=True)
        raise

def generate_html_report(genai_module, summary_text: str, transcript_text: str, model_api_name: str, video_title: str):
    """
    使用 Gemini 模型生成 HTML 報告。
    JULES'S UPDATE: Now returns the full response object for token counting.
    """
    log.info(f"🎨 Requesting HTML report from model '{model_api_name}'...")
    print_progress("generating_html", "AI 正在美化格式並生成 HTML 報告...")
    prompt = ALL_PROMPTS['format_as_html'].format(
        video_title_for_html=video_title,
        summary_text_for_html=summary_text,
        transcript_text_for_html=transcript_text
    )
    try:
        model = genai_module.GenerativeModel(model_api_name)
        response = model.generate_content(prompt, request_options={'timeout': 1800})
        generated_html = response.text

        if generated_html.strip().startswith("```html"):
            generated_html = generated_html.strip()[7:]
        if generated_html.strip().endswith("```"):
            generated_html = generated_html.strip()[:-3]

        doctype_pos = generated_html.lower().find("<!doctype html>")
        if doctype_pos != -1:
            generated_html = generated_html[doctype_pos:]

        log.info("✅ Successfully generated HTML report.")
        print_progress("html_generated", "HTML 報告生成完畢。")
        return generated_html.strip(), response
    except Exception as e:
        log.critical(f"🔴 Failed to generate HTML report from Gemini: {e}", exc_info=True)
        raise

def process_audio_file(audio_path: Path, model: str, video_title: str, output_dir: Path, tasks: str, output_format: str):
    """
    全新的彈性處理流程，根據傳入的 tasks 和 output_format 執行操作。
    JULES'S UPDATE: Added timing, token counting, and robust error handling.
    """
    start_time = time.time()
    total_tokens_used = 0

    try:
        import google.generativeai as genai
    except ImportError:
        log.critical("🔴 Necessary library (google-generativeai) not installed.")
        raise

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set.")
    genai.configure(api_key=api_key)

    task_list = [t.strip() for t in tasks.lower().split(',') if t.strip()]
    results = {}

    gemini_file_resource = None
    try:
        gemini_file_resource = upload_to_gemini(genai, audio_path, audio_path.name)
        model_instance = genai.GenerativeModel(model)

        def get_token_count(response):
            try:
                return response.usage_metadata.total_token_count
            except (AttributeError, ValueError):
                return 0

        # --- 執行 AI 任務 ---
        if "summary" in task_list and "transcript" in task_list:
            log.info("執行任務: 摘要與逐字稿 (合併執行)")
            summary, transcript, response = get_summary_and_transcript(genai, gemini_file_resource, model, video_title, audio_path.name)
            error_msg = get_error_message_from_response(response)
            if error_msg: raise ValueError(error_msg)
            total_tokens_used += get_token_count(response)
            results['summary'] = summary
            results['transcript'] = transcript
        else:
            if "summary" in task_list:
                log.info("執行任務: 僅摘要")
                prompt = ALL_PROMPTS['get_summary_only'].format(original_filename=audio_path.name, video_title=video_title)
                response = model_instance.generate_content([prompt, gemini_file_resource], request_options={'timeout': 1800})
                error_msg = get_error_message_from_response(response)
                if error_msg: raise ValueError(error_msg)
                total_tokens_used += get_token_count(response)
                results['summary'] = response.text.strip()
                log.info("✅ 摘要完成")

            if "transcript" in task_list:
                log.info("執行任務: 僅逐字稿")
                prompt = ALL_PROMPTS['get_transcript_only'].format(original_filename=audio_path.name, video_title=video_title)
                response = model_instance.generate_content([prompt, gemini_file_resource], request_options={'timeout': 3600})
                error_msg = get_error_message_from_response(response)
                if error_msg: raise ValueError(error_msg)
                total_tokens_used += get_token_count(response)
                results['transcript'] = response.text.strip()
                log.info("✅ 逐字稿完成")

        if "translate" in task_list:
            log.info("執行任務: 翻譯")
            text_to_translate = results.get('transcript', results.get('summary', ''))
            if text_to_translate:
                prompt = ALL_PROMPTS['translate_text'].format(text_to_translate=text_to_translate)
                response = model_instance.generate_content(prompt, request_options={'timeout': 1800})
                error_msg = get_error_message_from_response(response)
                if error_msg: raise ValueError(error_msg)
                total_tokens_used += get_token_count(response)
                results['translation'] = response.text.strip()
                log.info("✅ 翻譯完成")
            else:
                log.warning("⚠️ 無法執行翻譯，因為沒有可供翻譯的內容。")

        if "translate_zh" in task_list:
            log.info("執行任務: 翻譯成繁體中文")
            text_to_translate = results.get('transcript', results.get('summary', ''))
            if text_to_translate:
                prompt = ALL_PROMPTS['translate_text_zh'].format(text_to_translate=text_to_translate)
                response = model_instance.generate_content(prompt, request_options={'timeout': 1800})
                error_msg = get_error_message_from_response(response)
                if error_msg: raise ValueError(error_msg)
                total_tokens_used += get_token_count(response)
                results['translation_zh'] = response.text.strip()
                log.info("✅ 翻譯成繁體中文完成")
            else:
                log.warning("⚠️ 無法執行繁體中文翻譯，因為沒有可供翻譯的內容。")

        # --- 格式化與儲存 ---
        sanitized_title = sanitize_filename(video_title)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        final_filename_base = f"{sanitized_title}_{timestamp}_AI_Report"
        output_path = None

        if output_format == 'html':
            log.info("生成 HTML 格式報告...")
            summary_content = results.get('summary', '無摘要')
            transcript_content = results.get('transcript', '無逐字稿')
            html_content, response = generate_html_report(genai, summary_content, transcript_content, model, video_title)
            error_msg = get_error_message_from_response(response)
            if error_msg: raise ValueError(error_msg)
            total_tokens_used += get_token_count(response)
            output_path = output_dir / f"{final_filename_base}.html"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            log.info(f"✅ HTML 報告已儲存: {output_path}")

        elif output_format == 'txt':
            log.info("生成 TXT 格式報告...")
            output_content = f"報告標題: {video_title}\n\n"
            if 'summary' in results:
                output_content += f"--- 重點摘要 ---\n{results['summary']}\n\n"
            if 'transcript' in results:
                output_content += f"--- 詳細逐字稿 ---\n{results['transcript']}\n\n"
            if 'translation' in results:
                output_content += f"--- 使用原文 ---\n{results['translation']}\n\n"
            if 'translation_zh' in results:
                output_content += f"--- 繁體中文翻譯 ---\n{results['translation_zh']}\n\n"
            output_path = output_dir / f"{final_filename_base}.txt"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output_content)
            log.info(f"✅ TXT 報告已儲存: {output_path}")
        else:
             raise ValueError(f"不支援的輸出格式: {output_format}")

        processing_duration = time.time() - start_time

        final_result = {
            "type": "result",
            "status": "completed",
            "output_path": str(output_path),
            "video_title": video_title,
            "total_tokens_used": total_tokens_used,
            "processing_duration_seconds": round(processing_duration, 2)
        }
        print(json.dumps(final_result), flush=True)

    except ValueError as e:
        # 捕捉我們自訂的、易於理解的錯誤
        log.error(f"❌ Gemini 處理失敗: {e}")
        raise # 重新拋出，由主 exce-pt 區塊處理 JSON 輸出
    except Exception as e:
        log.critical(f"🔴 處理流程中發生未預期的嚴重錯誤: {e}", exc_info=True)
        raise

    finally:
        if gemini_file_resource:
            log.info(f"🗑️ Cleaning up Gemini file: {gemini_file_resource.name}")
            try:
                for attempt in range(3):
                    try:
                        genai.delete_file(gemini_file_resource.name)
                        log.info("✅ Cleanup successful.")
                        break
                    except Exception as e_del:
                        log.warning(f"Attempt {attempt+1} to delete file failed: {e_del}")
                        if attempt < 2:
                            time.sleep(2)
                        else:
                            raise
            except Exception as e:
                log.error(f"🔴 Failed to clean up Gemini file '{gemini_file_resource.name}' after retries: {e}")


def main():
    parser = argparse.ArgumentParser(description="Gemini AI 處理工具。")
    parser.add_argument(
        "--command",
        type=str,
        default="process",
        choices=["process", "list_models", "validate_key"],
        help="要執行的操作。"
    )
    # 根據指令，動態決定其他參數是否為必需
    # 我們先解析一次，看看指令是什麼
    args, remaining_argv = parser.parse_known_args()

    if args.command == "list_models":
        list_models()
        return

    if args.command == "validate_key":
        validate_key()
        return

    # 如果是 'process' 指令，則需要其他參數
    if args.command == "process":
        process_parser = argparse.ArgumentParser()
        process_parser.add_argument("--command", type=str, help=argparse.SUPPRESS) # 忽略已解析的 command
        # [JULES'S ARCHITECTURE FIX] 改為接收 task-id
        process_parser.add_argument("--task-id", type=str, required=True, help="要處理的 gemini_process 任務 ID。")
        process_parser.add_argument("--model", type=str, required=True, help="要使用的 Gemini 模型 API 名稱。")
        process_parser.add_argument("--output-dir", type=str, required=True, help="儲存生成報告的目錄。")
        process_parser.add_argument("--tasks", type=str, default="summary,transcript", help="要執行的任務列表，以逗號分隔。")
        process_parser.add_argument("--output-format", type=str, default="html", choices=["html", "txt"], help="最終輸出的檔案格式。")

        process_args = process_parser.parse_args(remaining_argv)

        # [JULES'S ARCHITECTURE FIX] 從資料庫獲取檔案路徑和標題
        try:
            from db.client import get_client
            db = get_client()
            log.info(f"正在從資料庫查詢任務 {process_args.task_id} 的詳細資訊...")

            task_info = db.get_task_status(process_args.task_id)
            if not task_info:
                raise ValueError(f"在資料庫中找不到任務 {process_args.task_id}")

            parent_task_id = task_info.get('depends_on')
            if not parent_task_id:
                raise ValueError(f"任務 {process_args.task_id} 沒有依賴的父任務")

            parent_task_info = db.get_task_status(parent_task_id)
            if not parent_task_info:
                raise ValueError(f"在資料庫中找不到父任務 {parent_task_id}")

            parent_result = json.loads(parent_task_info.get('result', '{}'))
            audio_file_str = parent_result.get('output_path')
            video_title = parent_result.get('video_title', '無標題')

            if not audio_file_str:
                raise ValueError(f"父任務 {parent_task_id} 的結果中不包含 'output_path'")

            log.info(f"成功獲取到音訊檔案路徑: {audio_file_str}")
            audio_path = Path(audio_file_str)

        except Exception as e:
            log.critical(f"🔴 從資料庫獲取任務資訊時發生嚴重錯誤: {e}", exc_info=True)
            print(json.dumps({"type": "result", "status": "failed", "error": f"資料庫查詢失敗: {e}"}), flush=True)
            sys.exit(1)


        output_path = Path(process_args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        if not audio_path.exists():
            log.critical(f"Input audio file not found: {audio_path}")
            print(json.dumps({"type": "result", "status": "failed", "error": f"Input file not found: {audio_path}"}), flush=True)
            sys.exit(1)

        try:
            # 將新的參數傳遞給 process_audio_file
            process_audio_file(
                audio_path=audio_path,
                model=process_args.model,
                video_title=video_title, # 從資料庫取得
                output_dir=output_path,
                tasks=process_args.tasks,
                output_format=process_args.output_format
            )
        except Exception as e:
            log.critical(f"An error occurred in the main processing flow: {e}", exc_info=True)
            print(json.dumps({"type": "result", "status": "failed", "error": str(e)}), flush=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
