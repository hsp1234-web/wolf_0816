# tools/transcriber.py

# --- 可供 bake_envs.py 解析的依賴定義 ---
# 使用 ast.literal_eval 安全解析
DEPENDENCIES = {
    # '套件名': '在 pip install 中使用的名稱'
    'torch': 'torch',
    'faster-whisper': 'faster-whisper',
    'opencc': 'opencc-python-reimplemented'
}

import time
import logging
import argparse
import torch
from pathlib import Path
from opencc import OpenCC
import json
import sys
from faster_whisper.utils import get_assets_path

# --- 日誌設定 ---
# 設定一個基本的日誌記錄器，以便在工具執行時提供有用的輸出
# 這對於在背景執行時進行偵錯至關重要
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler() # 直接輸出到 stderr
    ]
)
log = logging.getLogger('transcriber_tool')

class Transcriber:
    """
    一個獨立的轉錄工具類別。
    它在初始化時載入指定的 faster-whisper 模型，並提供一個方法來執行轉錄。
    這個版本被簡化了，移除了單例模式和多模型快取，因為它被設計為在
    一個隔離的、一次性的「預烘烤」環境中運行。
    """
    def __init__(self, model_size: str):
        """
        在實例化時直接載入模型。
        """
        self.model_size = model_size
        self.model = self._load_model()

    def _load_model(self):
        """
        根據指定的模型大小和可用的硬體，載入 faster-whisper 模型。
        """
        log.info(f"🧠 開始載入 '{self.model_size}' 模型...")
        start_time = time.time()

        # --- JULES 於 2025-08-09 的修改：自動偵測並使用 GPU ---
        device = "cpu"
        compute_type = "int8"
        if torch.cuda.is_available():
            log.info("✅ 偵測到 NVIDIA GPU (CUDA)！將使用 GPU 進行加速。")
            device = "cuda"
            compute_type = "float16" # 在 GPU 上使用 float16 以獲得最佳性能
        else:
            log.info("ℹ️ 未偵測到 NVIDIA GPU (CUDA)。將使用 CPU 進行運算。")
        # --- 修改結束 ---

        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
            duration = time.time() - start_time
            log.info(f"✅ 成功載入 '{self.model_size}' 模型到 {device.upper()}！耗時: {duration:.2f} 秒。")
            return model
        except ImportError as e:
            log.critical(f"❌ 模型載入失敗：缺少 'faster_whisper' 或 'torch' 模組。請確認環境已正確安裝。")
            raise e
        except Exception as e:
            log.critical(f"❌ 載入 '{self.model_size}' 模型時發生未預期錯誤: {e}", exc_info=True)
            raise e

    def transcribe(self, audio_path: str, language: str, beam_size: int = 5) -> str:
        """
        執行音訊轉錄的核心方法。
        """
        log.info(f"🎤 開始處理轉錄任務: {audio_path} (Beam Size: {beam_size})")
        if not self.model:
            log.error("❌ 模型未被載入，無法進行轉錄。")
            raise RuntimeError("模型未被載入，無法進行轉錄。")

        try:
            start_time = time.time()
            log.info("模型載入完成，開始轉錄...")

            segments, info = self.model.transcribe(audio_path, beam_size=beam_size, language=language, word_timestamps=True)

            detected_lang_msg = f"'{info.language}' (機率: {info.language_probability:.2f})"
            if language:
                log.info(f"🌍 使用者指定語言: '{language}'，模型偵測到 {detected_lang_msg}")
            else:
                log.info(f"🌍 未指定語言，模型自動偵測到 {detected_lang_msg}")

            # --- 串流式輸出 ---
            # 我們不再一次性回傳整個文本，而是逐句印出
            cc = OpenCC('s2twp') if info.language.lower().startswith('zh') else None
            if cc:
                log.info("🔄 偵測到中文，將對每句進行繁體化處理。")

            total_transcript = []
            for segment in segments:
                segment_text = segment.text.strip()
                if cc:
                    segment_text = cc.convert(segment_text)

                # 建立一個 JSON 物件來標準化輸出
                output_data = {
                    "type": "segment",
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment_text
                }
                # 使用 flush=True 確保即時輸出
                print(json.dumps(output_data, ensure_ascii=False), flush=True)
                total_transcript.append(segment_text)

            processing_time = time.time() - start_time
            log.info(f"📝 轉錄完成。耗時: {processing_time:.2f} 秒。")

            # 在最後，輸出一個包含最終統計資訊的 JSON 物件
            final_info = {
                "type": "final",
                "audio_duration": info.duration,
                "processing_time": processing_time
            }
            print(json.dumps(final_info), flush=True)

            # 為了相容原有的檔案寫入邏輯，我們回傳完整的文本
            return "".join(total_transcript)

        except Exception as e:
            log.error(f"❌ 轉錄過程中發生錯誤: {e}", exc_info=True)
            raise e

def check_model(model_size: str):
    """檢查模型是否已下載"""
    try:
        # 這是 faster-whisper 內部用來找模型路徑的方法
        model_path = get_assets_path(f"ctranslate2-4-avx2/whisper-{model_size}-ct2")
        if (Path(model_path) / "config.json").is_file():
            print("exists")
            log.info(f"✅ 模型 '{model_size}' 已存在於: {model_path}")
        else:
            print("not_exists")
            log.info(f"❓ 模型 '{model_size}' 不存在。")
    except Exception as e:
        print("not_exists")
        log.error(f"檢查模型 '{model_size}' 時出錯: {e}")

def download_model(model_size: str):
    """下載模型並回報進度"""
    log.info(f"📥 開始下載模型: {model_size}")
    # 利用 _load_model 的副作用來下載
    try:
        Transcriber(model_size=model_size)
        print(json.dumps({"progress": 100, "log": "模型下載完成"}), flush=True)
    except Exception as e:
        print(json.dumps({"progress": 100, "log": f"下載失敗: {e}"}), flush=True)
        log.critical(f"下載模型時發生錯誤: {e}", exc_info=True)
        exit(1)


def main():
    """
    主函數，根據 command 參數執行不同操作。
    """
    parser = argparse.ArgumentParser(description="一個多功能轉錄與模型管理工具。")
    parser.add_argument("--command", type=str, default="transcribe", choices=["transcribe", "check", "download"], help="要執行的操作。")
    # 轉錄參數
    parser.add_argument("--audio_file", type=str, help="[transcribe] 需要轉錄的音訊檔案路徑。")
    parser.add_argument("--output_file", type=str, help="[transcribe] 儲存轉錄結果的檔案路徑。")
    parser.add_argument("--language", type=str, default=None, help="[transcribe] 音訊的語言。")
    parser.add_argument("--beam_size", type=int, default=5, help="[transcribe] 解碼時使用的光束大小。")
    # 通用參數
    parser.add_argument("--model_size", type=str, default="tiny", help="要使用/檢查/下載的模型大小。")

    args = parser.parse_args()

    if args.command == "check":
        check_model(args.model_size)
        return

    if args.command == "download":
        download_model(args.model_size)
        return

    # --- 預設為轉錄 ---
    if not args.audio_file or not args.output_file:
        parser.error("--audio_file 和 --output_file 是 'transcribe' 命令的必要參數。")

    log.info(f"🚀 工具啟動 (轉錄模式)，參數: {args}")
    try:
        transcriber = Transcriber(model_size=args.model_size)
        result_text = transcriber.transcribe(args.audio_file, args.language, args.beam_size)
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result_text, encoding='utf-8')
        log.info(f"✅ 成功將結果寫入到: {args.output_file}")

    except Exception as e:
        log.critical(f"❌ 在執行過程中發生致命錯誤: {e}", exc_info=True)
        # 可以在此處建立一個錯誤標記檔案，以便外部執行器知道發生了問題
        error_file = Path(args.output_file).parent / f"{Path(args.output_file).stem}.error"
        error_file.write_text(str(e), encoding='utf-8')
        exit(1) # 以非零狀態碼退出，表示失敗

if __name__ == "__main__":
    main()
