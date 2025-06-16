import os
import json
import vertexai
from datetime import datetime
from pathlib import Path
from vertexai.preview.generative_models import GenerativeModel
from src.utils.logger import setup_logger
from src.utils.helper import get_prompt_template

logger = setup_logger()

# 使用するモデルを設定
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")

# 認証情報ファイルのパスを設定（環境変数、またはデフォルトパス）
CREDENTIALS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "./credential.json")

def fix_common_json_errors(json_text: str) -> str:
    """
    LLMの応答でよく発生するJSONエラーを自動修正する
    
    Args:
        json_text (str): 修正対象のJSON文字列
        
    Returns:
        str: 修正されたJSON文字列
    """
    try:
        # 一般的なJSONエラーパターンを修正
        fixed_text = json_text
        
        # パターン1: オブジェクトの後にカンマが不足している場合
        # "}\n      }\n    ]," のパターンを "}\n      }\n    ]," に修正
        import re
        
        # 配列内のオブジェクトの最後でカンマが不足しているパターンを修正
        # "}\n      }\n    ]," の前にカンマを追加
        pattern1 = r'(\n\s*})\n(\s*})\n(\s*],)'
        replacement1 = r'\1,\n\2\n\3'
        fixed_text = re.sub(pattern1, replacement1, fixed_text)
        
        # パターン2: 最後のオブジェクトの後に余分なカンマがある場合を削除
        pattern2 = r',(\s*}])'
        replacement2 = r'\1'
        fixed_text = re.sub(pattern2, replacement2, fixed_text)
        
        return fixed_text.strip()
        
    except Exception as e:
        logger.warning(f"Failed to fix JSON errors: {str(e)}")
        return json_text

def extract_information(text):
    """
    OCRで抽出したテキストをLLMに送信し、必要な情報を抽出する
    
    Args:
        text (str): OCRで抽出されたテキスト
        
    Returns:
        dict: 抽出された情報
    """
    logger.info(f"Extracting information using Gemini LLM with Vertex AI (Model: {MODEL})")
    
    try:
        # Vertex AIの初期化
        vertexai.init(location=LOCATION)
        
        # システムプロンプトとユーザープロンプトを取得
        system_prompt = get_prompt_template('system')
        user_prompt_template = get_prompt_template('user')
        
        # ユーザープロンプトの構築
        prompt = user_prompt_template.format(text=text)

        # モデル設定
        generation_config = {
            "temperature": 0,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        
        # Geminiモデルの初期化
        model = GenerativeModel(
            model_name=MODEL,
            generation_config=generation_config,
            system_instruction=system_prompt,
        )
        
        response = model.generate_content(prompt)
        
        # レスポンスからテキストを取得
        result = response.text
        # トークン使用量を取得
        usage_metadata = response.usage_metadata
        prompt_tokens = usage_metadata.prompt_token_count
        candidates_tokens = usage_metadata.candidates_token_count
        total_tokens = usage_metadata.total_token_count

        logger.info(f"Gemini Token Usage: Prompt={prompt_tokens}, Candidates={candidates_tokens}, Total={total_tokens}")

        # JSON形式のレスポンスをパース
        try:
            extracted_info = json.loads(result)
            # 抽出結果にトークン情報を追加
            extracted_info['usage_metadata'] = {
                'prompt_token_count': prompt_tokens,
                'candidates_token_count': candidates_tokens,
                'total_token_count': total_tokens
            }
            logger.info("Successfully extracted information using Gemini LLM via Vertex AI")
            return extracted_info
        except json.JSONDecodeError as json_error:
            # JSONとしてパースできない場合は、自動修正を試行
            logger.warning(f"Initial JSON parse failed: {str(json_error)}")
            logger.warning(f"Attempting to fix common JSON formatting issues...")
            
            fixed_result = fix_common_json_errors(result)
            
            try:
                # 修正後のJSONでパースを再試行
                extracted_info = json.loads(fixed_result)
                logger.info("Successfully parsed JSON after auto-correction")
                
                # 抽出結果にトークン情報を追加
                extracted_info['usage_metadata'] = {
                    'prompt_token_count': prompt_tokens,
                    'candidates_token_count': candidates_tokens,
                    'total_token_count': total_tokens
                }
                return extracted_info
                
            except json.JSONDecodeError as second_json_error:
                # 修正後もJSONとしてパースできない場合は、デバッグ情報を保存
                logger.warning(f"JSON parse still failed after auto-correction: {str(second_json_error)}")
                logger.warning(f"Raw response (first 500 chars): {result[:500]}...")
                
                # この場合でもトークン情報は含める
                return {
                    "raw_response": result,
                    'usage_metadata': {
                        'prompt_token_count': prompt_tokens,
                        'candidates_token_count': candidates_tokens,
                        'total_token_count': total_tokens
                    }
                }
            
    except Exception as e:
        logger.error(f"Error extracting information using Gemini LLM via Vertex AI: {str(e)}")
        raise