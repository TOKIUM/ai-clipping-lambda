import json
import unittest
from unittest.mock import patch, MagicMock

class TestHandler(unittest.TestCase):
    
    @patch('src.download.download_file')
    @patch('src.ocr.extract_text')
    @patch('src.llm.extract_information')
    @patch('src.processor.process_extracted_data')
    @patch('src.queue.send_to_queue')
    def test_process_document(self, mock_send_to_queue, mock_process_data, 
                             mock_extract_info, mock_extract_text, mock_download):
        # モックの戻り値を設定
        mock_download.return_value = "/tmp/test_file.jpg"
        mock_extract_text.return_value = "テスト文書のテキスト"
        mock_extract_info.return_value = {"company_name": "テスト株式会社", "date": "2025-04-01"}
        mock_process_data.return_value = {"processed": True, "normalized": {"company_name": "テスト株式会社"}}
        mock_send_to_queue.return_value = "test-message-id-123"
        
        # ハンドラをインポート（パッチ後にインポートする）
        from handler import process_document
        
        # テスト用のSQSイベントを作成
        event = {
            "Records": [
                {
                    "body": json.dumps({
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "test-file.jpg"}
                    })
                }
            ]
        }
        
        # ハンドラを実行
        response = process_document(event, {})
        
        # アサーション
        self.assertEqual(response["statusCode"], 200)
        
        # 各モックが正しく呼ばれたことを確認
        mock_download.assert_called_once_with("test-bucket", "test-file.jpg")
        mock_extract_text.assert_called_once_with("/tmp/test_file.jpg")
        mock_extract_info.assert_called_once_with("テスト文書のテキスト")
        mock_process_data.assert_called_once_with({"company_name": "テスト株式会社", "date": "2025-04-01"})
        mock_send_to_queue.assert_called_once()