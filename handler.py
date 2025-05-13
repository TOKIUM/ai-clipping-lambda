import json
import os
from typing import Any, Dict, List, TypedDict
from src.download import download_file
from src.ocr import extract_text
from src.llm import extract_information
from src.processor import process_extracted_data
from src.formatter import format_sqs_message
from src.sqs_sender import send_to_queue
from src.utils.logger import setup_logger
from src.utils.helper import convert_bounding_box_format
from src.s3_uploader import upload_to_s3  # 追加

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
    logger.debug(f"Event: {event}")
    try:
        # 環境変数からバケット名を取得 (serverless.ymlで定義されている想定)
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        if not bucket_name:
            logger.error("S3_BUCKET_NAME environment variable is not set.")
            raise ValueError("S3_BUCKET_NAME environment variable is not set.")

        records = event.get('Records', [])
        if not records:
            logger.warning("No records found in the event")
            raise ValueError("No records found in the event")

        results: List[ProcessResult] = []

        for record in records:
            current_sqs_message_id = record.get('messageId', 'unknown_sqs_message_id')
            try:
                message_body_str = record.get('body', '{}')
                message_body = json.loads(message_body_str)
                logger.info(f"Processing SQS message body: {message_body} (Message ID: {current_sqs_message_id})")

                clipping_request_id_from_message = message_body.get("clipping_request_id")
                image_urls = message_body.get('images', [])

                if not image_urls:
                    logger.warning(f"No image_urls found in message body for SQS message ID: {current_sqs_message_id}. Body: {message_body_str}")
                    raise ValueError(f"No image_urls found in SQS message body for message ID: {current_sqs_message_id}")

                for image_info in image_urls:
                    object_key = image_info.get('s3_key')
                    image_index = image_info.get('index', 'N/A')
                    local_file_path = None  # Initialize local_file_path

                    if not object_key:
                        logger.warning(f"Missing s3_key in image_info (index: {image_index}) for request: {clipping_request_id_from_message}, SQS message ID: {current_sqs_message_id}. Image Info: {image_info}")
                        raise ValueError(f"Missing s3_key in image_info (index: {image_index}) for request: {clipping_request_id_from_message}")
                    # S3から画像/PDFをダウンロード
                    try:
                        logger.info(f"Processing s3_key: {object_key} (index: {image_index}) for request: {clipping_request_id_from_message}, SQS message ID: {current_sqs_message_id}")

                        local_file_path = download_file(bucket_name, object_key)
                        ocr_response = extract_text(local_file_path)

                        if not ocr_response:
                            logger.warning(f"No OCR data found for {object_key} (index: {image_index}). Skipping this item.")
                            results.append({
                                "file": object_key,
                                "status": "skipped",
                                "message_id": None,
                                "error": "No text detected by OCR"
                            })
                            continue
                    except Exception as e_s3_item:
                        logger.exception(f"Error processing s3_key {object_key} (index: {image_index}) for request {clipping_request_id_from_message}, SQS message ID: {current_sqs_message_id}: {str(e_s3_item)}")
                        # Re-raise the exception after logging, to be caught by the outer try-except
                        raise e_s3_item
                    # OCRレスポンスを変換
                    try:
                        converted_ocr_data = convert_bounding_box_format(ocr_response)

                        if not converted_ocr_data:
                            logger.warning(f"OCR data became invalid after conversion for {object_key} (index: {image_index}). Skipping this item.")
                            results.append({
                                "file": object_key,
                                "status": "skipped",
                                "message_id": None,
                                "error": "OCR data conversion failed or resulted in empty data"
                            })
                            continue
                        logger.info(f"Converted OCR data for {object_key} (index: {image_index}): {converted_ocr_data}")

                        # LLMで情報抽出
                        extracted_info = extract_information(converted_ocr_data)
                        logger.info(f"Extracted information for {object_key} (index: {image_index}): {extracted_info}")

                        # LLM処理結果とOCR結果を結合
                        combined_output = {
                            "llm_output": extracted_info,
                            "ocr_output": converted_ocr_data
                        }
                    except Exception as e_llm:
                        logger.error(f"Error during LLM processing for {object_key} (index: {image_index}): {str(e_llm)}")
                        raise e_llm
                    # LLM処理結果をS3にアップロード
                    try:
                        llm_output_bucket_name = os.environ.get('LLM_OUTPUT_S3_BUCKET_NAME')
                        if llm_output_bucket_name:
                            llm_output_s3_key = f"{clipping_request_id_from_message}/{object_key}_combined_output.json"
                            upload_to_s3(json.dumps(combined_output, ensure_ascii=False), llm_output_bucket_name, llm_output_s3_key)
                        else:
                            logger.warning("LLM_OUTPUT_S3_BUCKET_NAME environment variable is not set. Skipping LLM output upload to S3.")
                    except Exception as e_upload:
                        logger.error(f"Error uploading LLM output to S3 for {object_key} (index: {image_index}): {str(e_upload)}")
                        raise e_upload

                    try:
                        current_clipping_request_id_for_processor = clipping_request_id_from_message or \
                                                                    (context.aws_request_id if hasattr(context, 'aws_request_id') else "unknown_request_id")

                        processed_data = process_extracted_data(extracted_info, ocr_response, current_clipping_request_id_for_processor, object_key)
                        logger.info(f"Processed data for {object_key} (index: {image_index}): {processed_data}")

                        final_sqs_message = format_sqs_message(processed_data, clipping_request_id_from_message, object_key)
                        message_id_sent = send_to_queue(final_sqs_message)

                        results.append({
                            "file": object_key,
                            "status": final_sqs_message.get("status", "error"),
                            "message_id": message_id_sent,
                            "error": final_sqs_message.get("error_message")
                        })
                    except Exception as e_processor:
                        logger.exception(f"Error processing extracted data for {object_key} (index: {image_index}) for request {clipping_request_id_from_message}, SQS message ID: {current_sqs_message_id}: {str(e_processor)}")
                        raise e_processor
                    finally:
                        if local_file_path and os.path.exists(local_file_path):
                            try:
                                os.remove(local_file_path)
                                logger.info(f"Successfully deleted temporary file: {local_file_path}")
                            except OSError as e_remove:
                                logger.error(f"Error deleting temporary file {local_file_path}: {str(e_remove)}")
            except Exception as e_sqs_record:
                logger.exception(f"Error processing SQS record (Message ID: {current_sqs_message_id}): {str(e_sqs_record)}")
                raise e_sqs_record

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Processing completed successfully for all records",
                "results": results
            })
        }

    except Exception as e:
        logger.exception(f"Critical error in handler: {str(e)}")
        raise e
