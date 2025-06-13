import unittest
import json
import os
from unittest.mock import patch, MagicMock
from src.llm import extract_information


class TestLLM(unittest.TestCase):

    def setUp(self):
        """テストごとに実行される初期化処理"""
        self.test_text = "請求書\n株式会社テスト\n合計金額: 10,000円\n税込"
        self.sample_system_prompt = "あなたは請求書から情報を抽出する専門家です。"
        self.sample_user_prompt = "以下のJSONから重要な情報を抽出してください:\n{text}"

    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_success_valid_json(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """正常なJSON応答が返される場合のテスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # モデルレスポンスのモック
        expected_json_response = {
            "issuer_name": {
                "value": "株式会社テスト",
                "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}
            },
            "amount_info": {
                "total_amount": {
                    "value": 10000,
                    "bbox": {"x": 150.0, "y": 50.0, "width": 80.0, "height": 25.0}
                }
            }
        }
        
        mock_response = MagicMock()
        mock_response.text = json.dumps(expected_json_response)
        
        # トークン使用量のモック
        mock_usage_metadata = MagicMock()
        mock_usage_metadata.prompt_token_count = 100
        mock_usage_metadata.candidates_token_count = 150
        mock_usage_metadata.total_token_count = 250
        mock_response.usage_metadata = mock_usage_metadata
        
        # モデルのモック
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance
        
        # テスト実行
        result = extract_information(self.test_text)
        
        # 検証
        self.assertIsInstance(result, dict)
        self.assertEqual(result["issuer_name"]["value"], "株式会社テスト")
        self.assertEqual(result["amount_info"]["total_amount"]["value"], 10000)
        
        # トークン使用量が正しく追加されているかチェック
        self.assertIn("usage_metadata", result)
        self.assertEqual(result["usage_metadata"]["prompt_token_count"], 100)
        self.assertEqual(result["usage_metadata"]["candidates_token_count"], 150)
        self.assertEqual(result["usage_metadata"]["total_token_count"], 250)
        
        # Vertex AIの初期化が呼ばれたかチェック
        mock_vertexai.init.assert_called_once_with(location="us-central1")
        
        # プロンプトテンプレートの取得が正しく呼ばれたかチェック
        mock_get_prompt.assert_any_call('system')
        mock_get_prompt.assert_any_call('user')
        
        # モデルの設定が正しいかチェック
        mock_generative_model.assert_called_once()
        call_args = mock_generative_model.call_args[1]
        self.assertEqual(call_args["model_name"], "gemini-2.0-flash")
        self.assertEqual(call_args["generation_config"]["temperature"], 0)
        self.assertEqual(call_args["generation_config"]["max_output_tokens"], 8192)
        self.assertEqual(call_args["generation_config"]["response_mime_type"], "application/json")
        self.assertEqual(call_args["system_instruction"], self.sample_system_prompt)
        
        # コンテンツ生成が正しく呼ばれたかチェック
        mock_model_instance.generate_content.assert_called_once()
        
        # ログが正しく出力されたかチェック
        mock_logger.info.assert_any_call("Extracting information using Gemini LLM with Vertex AI (Model: gemini-2.0-flash)")
        mock_logger.info.assert_any_call("Gemini Token Usage: Prompt=100, Candidates=150, Total=250")
        mock_logger.info.assert_any_call("Successfully extracted information using Gemini LLM via Vertex AI")

    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_invalid_json_response(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """無効なJSON応答が返される場合のテスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # 無効なJSONレスポンスのモック
        invalid_json_text = "これは有効なJSONではありません。"
        
        mock_response = MagicMock()
        mock_response.text = invalid_json_text
        
        # トークン使用量のモック
        mock_usage_metadata = MagicMock()
        mock_usage_metadata.prompt_token_count = 80
        mock_usage_metadata.candidates_token_count = 20
        mock_usage_metadata.total_token_count = 100
        mock_response.usage_metadata = mock_usage_metadata
        
        # モデルのモック
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance
        
        # テスト実行
        result = extract_information(self.test_text)
        
        # 検証
        self.assertIsInstance(result, dict)
        self.assertIn("raw_response", result)
        self.assertEqual(result["raw_response"], invalid_json_text)
        
        # トークン使用量が正しく追加されているかチェック
        self.assertIn("usage_metadata", result)
        self.assertEqual(result["usage_metadata"]["total_token_count"], 100)
        
        # 警告ログが出力されたかチェック
        mock_logger.warning.assert_called_once_with("Gemini LLM response is not in valid JSON format. Returning raw text.")

    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_vertex_ai_error(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """Vertex AI APIでエラーが発生する場合のテスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # Vertex AIの初期化でエラーを発生させる
        mock_vertexai.init.side_effect = Exception("Vertex AI initialization failed")
        
        # テスト実行とエラーの検証
        with self.assertRaises(Exception) as context:
            extract_information(self.test_text)
        
        self.assertEqual(str(context.exception), "Vertex AI initialization failed")
        
        # エラーログが出力されたかチェック
        mock_logger.error.assert_called_once_with("Error extracting information using Gemini LLM via Vertex AI: Vertex AI initialization failed")

    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_model_generation_error(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """モデルのコンテンツ生成でエラーが発生する場合のテスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # モデルのコンテンツ生成でエラーを発生させる
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.side_effect = Exception("Content generation failed")
        mock_generative_model.return_value = mock_model_instance
        
        # テスト実行とエラーの検証
        with self.assertRaises(Exception) as context:
            extract_information(self.test_text)
        
        self.assertEqual(str(context.exception), "Content generation failed")
        
        # エラーログが出力されたかチェック
        mock_logger.error.assert_called_once_with("Error extracting information using Gemini LLM via Vertex AI: Content generation failed")

    @patch('src.llm.MODEL', 'gemini-1.5-pro')
    @patch('src.llm.LOCATION', 'asia-northeast1')
    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_custom_environment_variables(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """カスタム環境変数が正しく使用されることのテスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # モデルレスポンスのモック
        mock_response = MagicMock()
        mock_response.text = '{"test": "response"}'
        mock_usage_metadata = MagicMock()
        mock_usage_metadata.prompt_token_count = 50
        mock_usage_metadata.candidates_token_count = 50
        mock_usage_metadata.total_token_count = 100
        mock_response.usage_metadata = mock_usage_metadata
        
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance
        
        # テスト実行
        result = extract_information(self.test_text)
        
        # 検証
        # カスタムリージョンでVertex AIが初期化されたかチェック
        mock_vertexai.init.assert_called_once_with(location="asia-northeast1")
        
        # カスタムモデルが使用されたかチェック
        call_args = mock_generative_model.call_args[1]
        self.assertEqual(call_args["model_name"], "gemini-1.5-pro")
        
        # ログにカスタムモデル名が含まれているかチェック
        mock_logger.info.assert_any_call("Extracting information using Gemini LLM with Vertex AI (Model: gemini-1.5-pro)")

    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_prompt_formatting(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """プロンプトの正しいフォーマットが使用されることのテスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # モデルレスポンスのモック
        mock_response = MagicMock()
        mock_response.text = '{"test": "response"}'
        mock_usage_metadata = MagicMock()
        mock_usage_metadata.prompt_token_count = 50
        mock_usage_metadata.candidates_token_count = 50
        mock_usage_metadata.total_token_count = 100
        mock_response.usage_metadata = mock_usage_metadata
        
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance
        
        # テスト実行
        extract_information(self.test_text)
        
        # プロンプトが正しくフォーマットされて渡されたかチェック
        expected_formatted_prompt = self.sample_user_prompt.format(text=self.test_text)
        mock_model_instance.generate_content.assert_called_once_with(expected_formatted_prompt)

    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_empty_text_input(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """空のテキスト入力に対する処理のテスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # モデルレスポンスのモック
        mock_response = MagicMock()
        mock_response.text = '{"message": "No content to extract"}'
        mock_usage_metadata = MagicMock()
        mock_usage_metadata.prompt_token_count = 20
        mock_usage_metadata.candidates_token_count = 10
        mock_usage_metadata.total_token_count = 30
        mock_response.usage_metadata = mock_usage_metadata
        
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance
        
        # 空のテキストでテスト実行
        result = extract_information("")
        
        # 検証
        self.assertIsInstance(result, dict)
        self.assertEqual(result["message"], "No content to extract")
        
        # 空のテキストが正しく渡されたかチェック
        expected_formatted_prompt = self.sample_user_prompt.format(text="")
        mock_model_instance.generate_content.assert_called_once_with(expected_formatted_prompt)

    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_complex_json_response(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """複雑なJSON応答の処理テスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # 複雑なJSON応答のモック
        complex_json_response = {
            "issuer_name": {
                "value": "株式会社テスト",
                "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}
            },
            "amount_info": {
                "total_amount": {
                    "value": 10800,
                    "bbox": {"x": 150.0, "y": 50.0, "width": 80.0, "height": 25.0}
                },
                "tax_breakdown": [
                    {
                        "tax_rate": {"value": 0.1},
                        "amount_consumption_tax": {
                            "value": 800,
                            "bbox": {"x": 200.0, "y": 100.0, "width": 60.0, "height": 20.0}
                        },
                        "amount_exclude_tax": {
                            "value": 10000,
                            "bbox": {"x": 100.0, "y": 100.0, "width": 80.0, "height": 20.0}
                        }
                    }
                ]
            },
            "bank_details": {
                "bank_name": {
                    "value": "テスト銀行",
                    "bbox": {"x": 50.0, "y": 200.0, "width": 120.0, "height": 25.0}
                },
                "account_number": {
                    "value": "1234567",
                    "bbox": {"x": 200.0, "y": 200.0, "width": 100.0, "height": 25.0}
                }
            }
        }
        
        mock_response = MagicMock()
        mock_response.text = json.dumps(complex_json_response)
        mock_usage_metadata = MagicMock()
        mock_usage_metadata.prompt_token_count = 200
        mock_usage_metadata.candidates_token_count = 300
        mock_usage_metadata.total_token_count = 500
        mock_response.usage_metadata = mock_usage_metadata
        
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance
        
        # テスト実行
        result = extract_information(self.test_text)
        
        # 検証
        self.assertIsInstance(result, dict)
        
        # ネストした構造が正しく保持されているかチェック
        self.assertEqual(result["issuer_name"]["value"], "株式会社テスト")
        self.assertEqual(result["amount_info"]["total_amount"]["value"], 10800)
        self.assertEqual(len(result["amount_info"]["tax_breakdown"]), 1)
        self.assertEqual(result["amount_info"]["tax_breakdown"][0]["tax_rate"]["value"], 0.1)
        self.assertEqual(result["bank_details"]["bank_name"]["value"], "テスト銀行")
        
        # トークン使用量が正しく追加されているかチェック
        self.assertEqual(result["usage_metadata"]["total_token_count"], 500)

    @patch('src.llm.get_prompt_template')
    def test_get_prompt_template_integration(self, mock_get_prompt):
        """get_prompt_template関数との統合テスト"""
        # プロンプトテンプレートが正しく呼び出されることを確認
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        with patch('src.llm.vertexai'), \
             patch('src.llm.GenerativeModel') as mock_generative_model, \
             patch('src.llm.logger'):
            
            mock_response = MagicMock()
            mock_response.text = '{"test": "response"}'
            mock_usage_metadata = MagicMock()
            mock_usage_metadata.prompt_token_count = 50
            mock_usage_metadata.candidates_token_count = 50
            mock_usage_metadata.total_token_count = 100
            mock_response.usage_metadata = mock_usage_metadata
            
            mock_model_instance = MagicMock()
            mock_model_instance.generate_content.return_value = mock_response
            mock_generative_model.return_value = mock_model_instance
            
            # テスト実行
            extract_information(self.test_text)
            
            # get_prompt_templateが正しく呼ばれたかチェック
            self.assertEqual(mock_get_prompt.call_count, 2)
            mock_get_prompt.assert_any_call('system')
            mock_get_prompt.assert_any_call('user')

    @patch('src.llm.vertexai')
    @patch('src.llm.GenerativeModel')
    @patch('src.llm.get_prompt_template')
    @patch('src.llm.logger')
    def test_extract_information_missing_usage_metadata(self, mock_logger, mock_get_prompt, mock_generative_model, mock_vertexai):
        """トークン使用量情報が欠落している場合のテスト"""
        # プロンプトテンプレートのモック
        mock_get_prompt.side_effect = [self.sample_system_prompt, self.sample_user_prompt]
        
        # usage_metadataが欠落しているレスポンスのモック
        mock_response = MagicMock()
        mock_response.text = '{"test": "response"}'
        # usage_metadataが存在しない、またはAttributeErrorが発生する場合をシミュレート
        mock_response.usage_metadata = None
        
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        mock_generative_model.return_value = mock_model_instance
        
        # テスト実行時にAttributeErrorが発生することを期待
        with self.assertRaises(AttributeError):
            extract_information(self.test_text)


if __name__ == '__main__':
    unittest.main()
