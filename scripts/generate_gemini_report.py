# 檔案: scripts/generate_gemini_report.py
# 說明: 一個獨立的、可透過命令列執行的 Gemini 報告生成與模型查詢工具。
# 版本: 2.0
import argparse
import sys
import os
import re
from pathlib import Path
import google.generativeai as genai

# 預設的提示，如果使用者沒有透過 --prompt 提供
DEFAULT_PROMPT = """\
你是一位專業的報告分析師。請根據以下提供的文字內容，生成一份簡潔、有條理的重點摘要報告。

報告應包含：
1.  **標題**：為這份報告取一個貼切的標題。
2.  **核心摘要**：用 2-3 句話總結內容的核心思想。
3.  **重點條列**：將內容的主要論點或發現，以條列方式清晰地呈現出來。

請直接輸出 Markdown 格式的報告內容。

---
輸入文字如下：
{text_content}
---
"""

def get_model_sort_key(model_name: str) -> tuple:
    """
    生成用於模型排序的鍵。
    排序邏輯：家族 > 版本號(降序) > 穩定性 > 名稱(升序)
    """
    name_lower = model_name.lower()

    # 1. 家族優先級 (數字越小越優先)
    if "flash" in name_lower:
        family_priority = 0
    elif "lite" in name_lower: # 根據使用者要求新增
        family_priority = 1
    elif "pro" in name_lower:
        family_priority = 2
    else:
        family_priority = 99

    # 2. 版本號 (數字越大越優先，所以用負數)
    version_match = re.search(r'(\d\.\d+|\d+)', name_lower)
    version_num = 0.0
    if version_match:
        try:
            version_num = float(version_match.group(1))
        except ValueError:
            pass # 忽略無法轉換的數字

    # 3. 穩定性/階段優先級 (latest > preview > normal)
    if "latest" in name_lower:
        stage_priority = 0
    elif "preview" in name_lower:
        stage_priority = 1
    else:
        stage_priority = 2

    return (family_priority, -version_num, stage_priority, name_lower)

def list_models() -> list[str]:
    """
    獲取並排序可用的 Gemini 模型列表。
    :return: 排序後的模型名稱列表。
    """
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("環境變數 GOOGLE_API_KEY 尚未設定。")
        genai.configure(api_key=api_key)

        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)

        available_models.sort(key=get_model_sort_key)
        return available_models

    except Exception as e:
        print(f"查詢模型列表失敗: {e}", file=sys.stderr)
        return []

def get_token_count(response) -> int:
    """安全地從 API 回應中提取 token 總數。"""
    try:
        return response.usage_metadata.total_token_count
    except (AttributeError, ValueError):
        return 0

def generate_report(input_file: str, output_file: str, prompt: str | None, model: str | None) -> str:
    """
    讀取輸入檔案內容，使用 Gemini API 生成報告，並儲存到輸出檔案。
    """
    try:
        # 1. 選擇模型
        if not model:
            print("未指定模型，正在自動選擇最佳模型...", file=sys.stderr)
            available_models = list_models()
            if not available_models:
                raise ValueError("無法獲取任何可用模型。")
            model = available_models[0]
            print(f"已自動選擇模型: {model}", file=sys.stderr)

        # 2. 讀取輸入檔案
        input_path = Path(input_file)
        if not input_path.is_file():
            raise FileNotFoundError(f"輸入檔案不存在: {input_file}")
        text_content = input_path.read_text(encoding='utf-8')

        # 3. 設定 Gemini API (重複設定是安全的)
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("環境變數 GOOGLE_API_KEY 尚未設定。")
        genai.configure(api_key=api_key)

        # 4. 準備 Prompt
        final_prompt = (prompt or DEFAULT_PROMPT).format(text_content=text_content)

        # 5. 呼叫 Gemini API
        print(f"正在使用模型 '{model}' 生成報告...", file=sys.stderr)
        gen_model = genai.GenerativeModel(model)
        response = gen_model.generate_content(final_prompt)

        # 提取 Token 使用量
        token_usage = get_token_count(response)
        print(f"Token-Usage: {token_usage}", file=sys.stderr)

        if not response.parts:
             raise ValueError(f"Gemini API 未返回有效內容，可能原因: {response.prompt_feedback}")
        generated_text = response.text

        # 6. 寫入輸出檔案
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(generated_text, encoding='utf-8')

        return str(output_path.resolve())

    except Exception as e:
        raise Exception(f"Gemini 報告生成失敗: {e}") from e

if __name__ == "__main__":
    # 使用一個父解析器來處理通用說明，讓 --help 更清晰
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--api-key", help="可選，直接提供 Google API Key。如果未提供，則會讀取 GOOGLE_API_KEY 環境變數。")

    parser = argparse.ArgumentParser(
        description="根據輸入的文字檔內容，生成一份 Gemini 報告，或查詢可用模型。",
        formatter_class=argparse.RawTextHelpFormatter,
        parents=[parent_parser]
    )

    # 互斥的指令組，使用者只能選擇其中一個操作
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--generate", action='store_true', help="執行報告生成任務 (需搭配 --input-file 和 --output-file)。")
    action_group.add_argument("--list-models", action='store_true', help="列出所有可用且經過排序的 Gemini 模型。")

    # 生成報告時需要的參數
    gen_group = parser.add_argument_group('報告生成參數 (搭配 --generate 使用)')
    gen_group.add_argument("--input-file", help="輸入的文字檔路徑（例如轉錄稿）。")
    gen_group.add_argument("--output-file", help="生成的報告要儲存的路徑（例如 .md）。")
    gen_group.add_argument("--model", help="可選，指定要使用的模型名稱。若不指定，將自動選擇最高優先級的模型。")
    gen_group.add_argument("--prompt", help="可選的自訂 prompt 範本。範本中必須包含 '{text_content}'。")

    args = parser.parse_args()

    # 如果提供了 API Key 參數，設定為環境變數
    if args.api_key:
        os.environ['GOOGLE_API_KEY'] = args.api_key

    try:
        if args.list_models:
            sorted_models = list_models()
            if sorted_models:
                for model_name in sorted_models:
                    print(model_name)
            sys.exit(0)

        if args.generate:
            if not args.input_file or not args.output_file:
                parser.error("--generate 標誌必須與 --input-file 和 --output-file 一同使用。")

            file_path = generate_report(args.input_file, args.output_file, args.prompt, args.model)
            print(file_path) # 將成功路徑輸出到 stdout
            sys.exit(0)

    except Exception as e:
        print(f"執行失敗: {e}", file=sys.stderr)
        sys.exit(1)
