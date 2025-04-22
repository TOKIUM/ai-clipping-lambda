import json
import unittest
import os
from unittest.mock import patch, MagicMock, ANY

# Vision APIレスポンスのモックを作成するヘルパー関数
def create_mock_ocr_response(text):
    mock_response = MagicMock()
    mock_response.full_text_annotation.text = text
    return mock_response

class TestHandler(unittest.TestCase):

    @patch.dict(os.environ, {'S3_BUCKET_NAME': 'test-bucket', 'OUTPUT_QUEUE_URL': 'test-queue-url'})
    @patch('src.download.download_file')
    @patch('src.ocr.extract_text')
    @patch('src.llm.extract_information')
    @patch('src.processor.process_extracted_data')
    @patch('src.formatter.format_sqs_message')
    @patch('src.sqs_sender.send_to_queue')
    def test_process_document_success(self, mock_send_to_queue, mock_format_sqs, mock_process_data,
                                       mock_extract_info, mock_extract_text, mock_download):
        # モックの戻り値を設定
        mock_download.return_value = "/tmp/test_image.png"
        mock_ocr_response = create_mock_ocr_response("請求書 テスト株式会社 合計 10000円")
        mock_extract_text.return_value = mock_ocr_response
        mock_llm_result = {"company_name": {"value": "テスト株式会社", "bbox": {"x": 10, "y": 10, "width": 50, "height": 10}},
                           "total_amount": {"value": 10000, "bbox": {"x": 60, "y": 10, "width": 30, "height": 10}}}
        mock_extract_info.return_value = mock_llm_result
        mock_processed_result = {"processed": True,
                                 "original_data": mock_llm_result,
                                 "corrected_data": mock_llm_result,
                                 "error": None,
                                 "process_timestamp": "2025-04-22T10:00:00Z"}
        mock_process_data.return_value = mock_processed_result
        mock_final_message = {"clipping_request_id": "req-123",
                              "s3_key": "images/test_image.png",
                              "status": "success",
                              "clips": [{"field_name": "company_name", "value": "テスト株式会社", "position": {}},
                                        {"field_name": "total_amount", "value": "10000", "position": {}}],
                              "error_message": None,
                              "processed_timestamp": "2025-04-22T10:00:00Z"}
        mock_format_sqs.return_value = mock_final_message
        mock_send_to_queue.return_value = "test-message-id-abc"

        from handler import process_document

        test_s3_key = "images/test_image.png"
        test_request_id = "req-123"
        event = {
            "Records": [
                {
                    "body": json.dumps({
                        "clipping_request_id": test_request_id,
                        "image_urls": [
                            {
                                "index": "1",
                                "s3_key": test_s3_key
                            }
                        ]
                    })
                }
            ]
        }

        response = process_document(event, {})

        self.assertEqual(response["statusCode"], 200)
        response_body = json.loads(response["body"])
        self.assertEqual(response_body["message"], "Processing completed for batch.")
        self.assertEqual(len(response_body["results"]), 1)
        result = response_body["results"][0]
        self.assertEqual(result["clipping_request_id"], test_request_id)
        self.assertEqual(result["s3_key"], test_s3_key)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message_id"], "test-message-id-abc")
        self.assertIsNone(result["error"])

        mock_download.assert_called_once_with("test-bucket", test_s3_key)
        mock_extract_text.assert_called_once_with("/tmp/test_image.png")
        mock_extract_info.assert_called_once_with("請求書 テスト株式会社 合計 10000円")
        mock_process_data.assert_called_once_with(mock_llm_result, mock_ocr_response, test_request_id, test_s3_key)
        mock_format_sqs.assert_called_once_with(mock_processed_result, test_request_id, test_s3_key)
        mock_send_to_queue.assert_called_once_with(mock_final_message)

    # TODO: エラーケースや複数画像、OCR失敗などのテストケースを追加

if __name__ == '__main__':
    unittest.main()