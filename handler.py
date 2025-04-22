import json
from typing import Any, Dict, List, TypedDict
from src.download import download_file
from src.ocr import extract_text
from src.llm import extract_information
from src.processor import process_extracted_data
from src.formatter import format_sqs_message
from src.sqs_sender import send_to_queue
from src.utils.logger import setup_logger
from src.utils.helper import convert_bounding_box_format

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
    2. Google Cloud VisionでOCR処理 (レスポンスオブジェクト取得)
    3. LLMで情報抽出
    4. 抽出情報の後処理 (OCRレスポンスも使用)
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
            object_key = "unknown"
            try:
                # SQSメッセージを取得（S3イベント情報）
                message = json.loads(record.get('body', '{}'))
                logger.info(f"Processing message: {message}")

                # S3情報を抽出
                s3_info = message.get('s3')
                if not s3_info:
                    # S3イベントではないメッセージ形式も考慮 (例: 直接投入されたテストメッセージ)
                    # 代替のキー構造を探す (例: Records[0].s3)
                    s3_info_from_records = message.get('Records', [{}])[0].get('s3')
                    if s3_info_from_records:
                        s3_info = s3_info_from_records
                    else:
                        logger.error("Could not find S3 information in the message")
                        results.append({
                            "file": "unknown",
                            "status": "error",
                            "error": "Missing S3 information"
                        })
                        continue

                bucket_name = s3_info.get('bucket', {}).get('name')
                object_key = s3_info.get('object', {}).get('key')

                if not bucket_name or not object_key:
                    logger.error("Missing bucket name or object key")
                    results.append({
                        "file": object_key or "unknown",
                        "status": "error",
                        "error": "Missing bucket name or object key"
                    })
                    continue

                # 1. S3からのダウンロード
                local_file_path = download_file(bucket_name, object_key)

                # 2. OCR処理 (戻り値がレスポンスオブジェクト or リストになる)
                ocr_response = extract_text(local_file_path)

                # OCR結果がない場合はスキップ
                if not ocr_response:
                    logger.warning(f"No OCR data found for {object_key}. Skipping.")
                    results.append({
                        "file": object_key,
                        "status": "skipped",
                        "message_id": None,
                        "error": "No text detected by OCR"
                    })
                    continue

                # *** Convert Bounding Box format before passing to LLM ***
                converted_ocr_data = convert_bounding_box_format(ocr_response)

                # Check again if conversion resulted in unusable data
                if not converted_ocr_data:
                     logger.warning(f"OCR data became invalid after conversion for {object_key}. Skipping.")
                     results.append({
                         "file": object_key,
                         "status": "skipped",
                         "message_id": None,
                         "error": "OCR data conversion failed or resulted in empty data"
                     })
                     continue

                # LLMに渡すテキストと後処理用のOCRデータを準備
                ocr_data_for_processor = converted_ocr_data
                if isinstance(converted_ocr_data, list): # PDFの場合
                    ocr_data_for_processor = converted_ocr_data # リスト全体を渡す
                elif hasattr(converted_ocr_data, 'full_text_annotation') and converted_ocr_data.full_text_annotation: # 画像の場合
                    ocr_data_for_processor = converted_ocr_data # 単一レスポンスを渡す
                else:
                    logger.warning(f"Unexpected OCR response format or no text annotation for {object_key}. Skipping.")
                    results.append({
                        "file": object_key,
                        "status": "skipped",
                        "message_id": None,
                        "error": "Unexpected OCR response format or no text annotation"
                    })
                    continue

                # 3. LLMで情報抽出 (変換後のデータを渡す)
                extracted_info = extract_information(ocr_data_for_processor)

                # 4. 抽出データの後処理 (LLM結果とOCRレスポンス全体を渡す)
                processed_data = process_extracted_data(extracted_info, ocr_response)

                # 5. SQSメッセージのフォーマット
                final_sqs_message = format_sqs_message(processed_data, object_key)

                # 6. SQSへ結果送信 (フォーマットされたメッセージを送信)
                message_id = send_to_queue(final_sqs_message)

                # 結果リストに追加 (statusはフォーマット結果から取得)
                results.append({
                    "file": object_key,
                    "status": final_sqs_message.get("status", "error"), # Use status from formatted message
                    "message_id": message_id,
                    "error": final_sqs_message.get("error_message") # エラーメッセージもフォーマット結果から取得
                })

            except Exception as e:
                logger.exception(f"Error processing record for object {object_key}: {str(e)}")

                results.append({
                    "file": object_key,
                    "status": "error",
                    "message_id": None,
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
        logger.exception(f"Critical error in handler: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error processing documents",
                "error": str(e)
            })
        }
