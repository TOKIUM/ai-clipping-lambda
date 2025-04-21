import json
import logging
from typing import Any, Dict, List, TypedDict
from src.download import download_file
from src.ocr import extract_text
from src.llm import extract_information
from src.processor import process_extracted_data
from src.sqs_sender import send_to_queue
from src.utils.logger import setup_logger

logger = setup_logger()

# Python 3.12: TypedDictを使用して期待されるイベント構造を定義
class S3Object(TypedDict):
    key: str

class S3Bucket(TypedDict):
    name: str

class S3Info(TypedDict):
    bucket: S3Bucket
    object: S3Object

class SQSRecord(TypedDict):
    body: str

class ProcessResult(TypedDict):
    file: str
    status: str
    message_id: str | None = None
    error: str | None = None

def process_document(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    SQSから受け取ったS3イベント情報をもとに処理を行うメインハンドラー
    1. S3から画像/PDFをダウンロード
    2. Google Cloud VisionでOCR処理
    3. LLMで情報抽出
    4. 抽出情報の後処理
    5. SQSへ結果送信
    """
    logger.info("Processing started")
    
    try:
        # SQSからのメッセージを解析
        records = event.get('Records', [])
        if not records:
            logger.warning("No records found in the event")
            return {"statusCode": 400, "body": json.dumps({"message": "No records found"})}
        
        results: List[ProcessResult] = []
        
        # 各レコードを処理
        for record in records:
            try:
                # SQSメッセージを取得（S3イベント情報）
                message = json.loads(record.get('body', '{}'))
                logger.info(f"Processing message: {message}")
                
                # Python 3.12: パターンマッチングを使用してS3情報を抽出
                match message:
                    case {"bucket": {"name": bucket_name}, "object": {"key": object_key}} if bucket_name and object_key:
                        # 処理を続行
                        pass
                    case _:
                        logger.error("Missing bucket name or object key")
                        results.append({
                            "file": "unknown",
                            "status": "error",
                            "error": "Missing bucket name or object key"
                        })
                        continue
                
                # 1. S3からのダウンロード
                local_file_path = download_file(bucket_name, object_key)
                
                # 2. OCR処理
                extracted_text = extract_text(local_file_path)
                
                # 3. LLMで情報抽出
                extracted_info = extract_information(extracted_text)
                
                # 4. 抽出データの後処理
                processed_data = process_extracted_data(extracted_info)
                
                # 5. SQSへの送信データ整形
                # 6. SQSへ結果送信
                message_id = send_to_queue(processed_data)
                
                results.append({
                    "file": object_key,
                    "status": "success",
                    "message_id": message_id
                })
                
            except Exception as e:
                # Python 3.12: 例外グループ化と注釈付き例外を使用
                e.add_note(f"Error processing record for object {object_key if 'object_key' in locals() else 'unknown'}")
                logger.error(f"Error processing record: {str(e)}")
                
                results.append({
                    "file": object_key if 'object_key' in locals() else "unknown",
                    "status": "error",
                    "error": str(e)
                })
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Processing completed",
                "results": results
            })
        }
    
    except Exception as e:
        # Python 3.12: 例外グループ化と注釈付き例外を使用
        e.add_note("Critical error in handler function")
        logger.error(f"Critical error in handler: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error processing documents",
                "error": str(e)
            })
        }
