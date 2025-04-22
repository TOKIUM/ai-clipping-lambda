import os
import json
from typing import Dict, Any, List
from google.cloud import aiplatform
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value
from vertexai.preview.generative_models import GenerativeModel, ChatSession
from vertexai.generative_models import Content
from src.utils.logger import setup_logger
from src.utils.helper import get_prompt_template

logger = setup_logger()

# 使用するモデルを設定
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "asia-northeast1")

# 認証情報ファイルのパスを設定（環境変数、またはデフォルトパス）
CREDENTIALS_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "./credential.json")

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
        aiplatform.init(
            location=LOCATION,
        )
        
        # システムプロンプトとユーザープロンプトを取得
        system_prompt = get_prompt_template('system')
        user_prompt_template = get_prompt_template('user')
        
        # ユーザープロンプトの構築
        prompt = user_prompt_template.format(text=text)
        
        # Geminiモデルの初期化
        model = GenerativeModel(MODEL)
        
        # チャットの初期化
        chat = model.start_chat(
            context=system_prompt,
        )
        
        # リクエストを送信
        response = chat.send_message(
            prompt,
            generation_config={
                "temperature": 0.3,
                "max_output_tokens": 2000,
                "top_p": 1.0,
            }
        )
        
        # レスポンスからテキストを取得
        result = response.text
        
        # JSON形式のレスポンスをパース
        try:
            extracted_info = json.loads(result)
            logger.info("Successfully extracted information using Gemini LLM via Vertex AI")
            return extracted_info
        except json.JSONDecodeError:
            # JSONとしてパースできない場合は、テキストとしてそのまま返す
            logger.warning("Gemini LLM response is not in valid JSON format. Returning raw text.")
            return {"raw_response": result}
            
    except Exception as e:
        logger.error(f"Error extracting information using Gemini LLM via Vertex AI: {str(e)}")
        raise