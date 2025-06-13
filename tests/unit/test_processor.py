import unittest
import json
from datetime import datetime
from unittest.mock import patch, MagicMock
from google.cloud import vision
from src.processor import (
    vertices_to_bbox,
    bbox_overlap,
    sort_words_naturally,
    normalize_value,
    find_matching_word_sequence,
    calculate_minimum_bbox,
    correct_bounding_boxes_recursive,
    get_all_words_from_ocr_response,
    correct_bounding_boxes,
    process_extracted_data,
    parse_date
)


class TestProcessor(unittest.TestCase):

    def setUp(self):
        """テストごとに実行される初期化処理"""
        # モックOCR単語を作成するヘルパー
        self.create_mock_word = self._create_mock_word
        
        # テスト用データ
        self.test_extraction_data = {
            "issuer_name": {
                "value": "テスト株式会社",
                "bbox": {"x": 10, "y": 20, "width": 100, "height": 30}
            },
            "amount_info": {
                "total_amount": {
                    "value": 10000,
                    "bbox": {"x": 150, "y": 50, "width": 80, "height": 25}
                }
            }
        }

    def _create_mock_word(self, text, x, y, width, height):
        """モックOCR単語オブジェクトを作成するヘルパーメソッド"""
        mock_word = MagicMock()
        mock_word.bounding_box = MagicMock()
        
        # 頂点を作成（左上、右上、右下、左下の順）
        vertices = [
            MagicMock(x=x, y=y),
            MagicMock(x=x + width, y=y),
            MagicMock(x=x + width, y=y + height),
            MagicMock(x=x, y=y + height)
        ]
        mock_word.bounding_box.vertices = vertices
        
        # シンボルを作成
        symbols = []
        for char in text:
            mock_symbol = MagicMock()
            mock_symbol.text = char
            symbols.append(mock_symbol)
        mock_word.symbols = symbols
        
        return mock_word

    def test_vertices_to_bbox_valid_vertices(self):
        """正常な頂点からbboxが正しく計算されることのテスト"""
        vertices = [
            {'x': 10, 'y': 20},
            {'x': 110, 'y': 20},
            {'x': 110, 'y': 50},
            {'x': 10, 'y': 50}
        ]
        
        result = vertices_to_bbox(vertices)
        
        expected = {
            'x': 10,
            'y': 20,
            'width': 100,
            'height': 30
        }
        
        self.assertEqual(result, expected)

    def test_vertices_to_bbox_empty_vertices(self):
        """空の頂点リストでNoneが返されることのテスト"""
        result = vertices_to_bbox([])
        self.assertIsNone(result)
        
        result = vertices_to_bbox(None)
        self.assertIsNone(result)

    def test_bbox_overlap_overlapping_boxes(self):
        """重なるbboxの判定テスト"""
        bbox1 = {'x': 10, 'y': 10, 'width': 50, 'height': 30}
        bbox2 = {'x': 30, 'y': 20, 'width': 40, 'height': 25}
        
        self.assertTrue(bbox_overlap(bbox1, bbox2))

    def test_bbox_overlap_non_overlapping_boxes(self):
        """重ならないbboxの判定テスト"""
        bbox1 = {'x': 10, 'y': 10, 'width': 30, 'height': 20}
        bbox2 = {'x': 50, 'y': 40, 'width': 30, 'height': 20}
        
        self.assertFalse(bbox_overlap(bbox1, bbox2))

    def test_bbox_overlap_invalid_boxes(self):
        """無効なbboxでFalseが返されることのテスト"""
        bbox1 = {'x': 10, 'y': 10, 'width': 30, 'height': 20}
        
        self.assertFalse(bbox_overlap(bbox1, None))
        self.assertFalse(bbox_overlap(None, bbox1))
        self.assertFalse(bbox_overlap(None, None))

    def test_sort_words_naturally_valid_words(self):
        """OCR単語の自然順ソートのテスト"""
        words = [
            self.create_mock_word("世界", 100, 10, 30, 20),  # 右上
            self.create_mock_word("こんにちは", 10, 10, 80, 20),  # 左上
            self.create_mock_word("さようなら", 10, 40, 80, 20),  # 左下
            self.create_mock_word("また明日", 100, 40, 60, 20)  # 右下
        ]
        
        sorted_words = sort_words_naturally(words)
        
        # Y座標の小さいもの（上）から、同じY座標ではX座標の小さいもの（左）から並ぶ
        expected_order = ["こんにちは", "世界", "さようなら", "また明日"]
        actual_order = ["".join([s.text for s in word.symbols]) for word in sorted_words]
        
        self.assertEqual(actual_order, expected_order)

    def test_sort_words_naturally_empty_list(self):
        """空のリストで空のリストが返されることのテスト"""
        result = sort_words_naturally([])
        self.assertEqual(result, [])
        
        result = sort_words_naturally(None)
        self.assertEqual(result, [])

    def test_normalize_value_text_type(self):
        """テキストタイプの正規化テスト"""
        # 全角スペースの変換
        self.assertEqual(normalize_value("テスト　会社", "text"), "テスト 会社")
        
        # 複数スペースの統合
        self.assertEqual(normalize_value("テスト   会社", "text"), "テスト 会社")
        
        # 先頭・末尾のスペース除去
        self.assertEqual(normalize_value("  テスト会社  ", "text"), "テスト会社")

    def test_normalize_value_number_type(self):
        """数値タイプの正規化テスト"""
        # 円記号とカンマの除去
        self.assertEqual(normalize_value("¥10,000", "number"), "10000")
        self.assertEqual(normalize_value("￥5,500", "number"), "5500")
        
        # 浮動小数点の整数化
        self.assertEqual(normalize_value("100.0", "number"), "100")
        
        # スペースの除去
        self.assertEqual(normalize_value("1 0 0 0", "number"), "1000")

    def test_normalize_value_date_type(self):
        """日付タイプの正規化テスト"""
        # 和暦形式の変換
        self.assertEqual(normalize_value("2023年12月25日", "date"), "2023-12-25")
        
        # スラッシュ区切り
        self.assertEqual(normalize_value("2023/12/25", "date"), "2023-12-25")
        
        # ドット区切り
        self.assertEqual(normalize_value("2023.12.25", "date"), "2023-12-25")
        
        # 逆順（日本式）
        self.assertEqual(normalize_value("25/12/2023", "date"), "2023-12-25")

    def test_normalize_value_none_input(self):
        """None入力での空文字列返却テスト"""
        self.assertEqual(normalize_value(None), "")
        self.assertEqual(normalize_value(None, "number"), "")
        self.assertEqual(normalize_value(None, "date"), "")

    def test_find_matching_word_sequence_exact_match(self):
        """完全一致する単語シーケンスの検索テスト"""
        words = [
            self.create_mock_word("テスト", 10, 10, 40, 20),
            self.create_mock_word("株式会社", 60, 10, 80, 20),
            self.create_mock_word("合計", 10, 40, 40, 20)
        ]
        
        result = find_matching_word_sequence("テスト株式会社", words, "text")
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        
        # 結果の単語が正しい順序であることを確認
        combined_text = "".join([symbol.text for word in result for symbol in word.symbols])
        self.assertEqual(combined_text, "テスト株式会社")

    def test_find_matching_word_sequence_number_match(self):
        """数値型での一致検索テスト"""
        words = [
            self.create_mock_word("¥", 10, 10, 15, 20),
            self.create_mock_word("10,000", 30, 10, 60, 20),
            self.create_mock_word("円", 95, 10, 20, 20)
        ]
        
        result = find_matching_word_sequence("10000", words, "number")
        
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        combined_text = "".join([symbol.text for word in result for symbol in word.symbols])
        self.assertEqual(combined_text, "10,000")

    def test_find_matching_word_sequence_no_match(self):
        """一致しない場合のテスト"""
        words = [
            self.create_mock_word("テスト", 10, 10, 40, 20),
            self.create_mock_word("会社", 60, 10, 40, 20)
        ]
        
        result = find_matching_word_sequence("存在しない文字列", words, "text")
        self.assertIsNone(result)

    def test_find_matching_word_sequence_empty_input(self):
        """空の入力での処理テスト"""
        words = [self.create_mock_word("テスト", 10, 10, 40, 20)]
        
        result = find_matching_word_sequence("", words, "text")
        self.assertIsNone(result)
        
        result = find_matching_word_sequence("テスト", [], "text")
        self.assertIsNone(result)

    def test_calculate_minimum_bbox_valid_words(self):
        """単語リストからの最小bbox計算テスト"""
        words = [
            self.create_mock_word("テスト", 10, 20, 40, 20),
            self.create_mock_word("会社", 60, 15, 40, 25)
        ]
        
        result = calculate_minimum_bbox(words)
        
        expected = {
            'x': 10,
            'y': 15,
            'width': 90,  # 100 - 10
            'height': 25  # 40 - 15
        }
        
        self.assertEqual(result, expected)

    def test_calculate_minimum_bbox_empty_words(self):
        """空の単語リストでNoneが返されることのテスト"""
        result = calculate_minimum_bbox([])
        self.assertIsNone(result)

    def test_calculate_minimum_bbox_words_without_bbox(self):
        """bboxのない単語でNoneが返されることのテスト"""
        mock_word = MagicMock()
        mock_word.bounding_box = None
        
        result = calculate_minimum_bbox([mock_word])
        self.assertIsNone(result)

    def test_correct_bounding_boxes_recursive_dict_with_value_bbox(self):
        """値とbboxを持つ辞書の補正テスト"""
        data = {
            "value": "テスト会社",
            "bbox": {"x": 10, "y": 10, "width": 80, "height": 20}
        }
        
        ocr_words = [
            self.create_mock_word("テスト", 12, 12, 35, 18),
            self.create_mock_word("会社", 50, 12, 35, 18)
        ]
        
        result = correct_bounding_boxes_recursive(data, ocr_words)
        
        # 補正されたbboxが返されることを確認
        self.assertIn("bbox", result)
        self.assertNotEqual(result["bbox"], data["bbox"])  # 元のbboxとは異なる
        
        # 値は保持されることを確認
        self.assertEqual(result["value"], "テスト会社")

    def test_correct_bounding_boxes_recursive_nested_dict(self):
        """ネストした辞書の再帰的補正テスト"""
        data = {
            "company": {
                "name": {
                    "value": "テスト株式会社",
                    "bbox": {"x": 10, "y": 10, "width": 100, "height": 20}
                }
            },
            "amount": {
                "value": 5000,
                "bbox": {"x": 150, "y": 50, "width": 60, "height": 20}
            }
        }
        
        ocr_words = [
            self.create_mock_word("テスト株式会社", 10, 10, 100, 20),
            self.create_mock_word("5000", 150, 50, 60, 20)
        ]
        
        result = correct_bounding_boxes_recursive(data, ocr_words)
        
        # ネストした構造が保持されることを確認
        self.assertIn("company", result)
        self.assertIn("name", result["company"])
        self.assertIn("value", result["company"]["name"])
        self.assertEqual(result["company"]["name"]["value"], "テスト株式会社")

    def test_correct_bounding_boxes_recursive_list_processing(self):
        """リストの再帰的処理テスト"""
        data = [
            {
                "value": "項目1",
                "bbox": {"x": 10, "y": 10, "width": 50, "height": 20}
            },
            {
                "value": "項目2",
                "bbox": {"x": 10, "y": 40, "width": 50, "height": 20}
            }
        ]
        
        ocr_words = [
            self.create_mock_word("項目1", 10, 10, 50, 20),
            self.create_mock_word("項目2", 10, 40, 50, 20)
        ]
        
        result = correct_bounding_boxes_recursive(data, ocr_words)
        
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["value"], "項目1")
        self.assertEqual(result[1]["value"], "項目2")

    def test_correct_bounding_boxes_recursive_primitive_values(self):
        """プリミティブ値の処理テスト"""
        self.assertEqual(correct_bounding_boxes_recursive("test", []), "test")
        self.assertEqual(correct_bounding_boxes_recursive(123, []), 123)
        self.assertEqual(correct_bounding_boxes_recursive(None, []), None)

    def test_get_all_words_from_ocr_response_single_response(self):
        """単一OCRレスポンスからの単語抽出テスト"""
        # モックOCRレスポンスを作成
        mock_response = MagicMock()
        mock_response.full_text_annotation = MagicMock()
        
        # モックページ、ブロック、パラグラフ、単語を作成
        mock_word1 = self.create_mock_word("テスト", 10, 10, 40, 20)
        mock_word2 = self.create_mock_word("会社", 60, 10, 40, 20)
        
        mock_paragraph = MagicMock()
        mock_paragraph.words = [mock_word1, mock_word2]
        
        mock_block = MagicMock()
        mock_block.paragraphs = [mock_paragraph]
        
        mock_page = MagicMock()
        mock_page.blocks = [mock_block]
        
        mock_response.full_text_annotation.pages = [mock_page]
        
        result = get_all_words_from_ocr_response(mock_response)
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], mock_word1)
        self.assertEqual(result[1], mock_word2)

    def test_get_all_words_from_ocr_response_list_of_responses(self):
        """複数OCRレスポンスからの単語抽出テスト"""
        # 2つのモックレスポンスを作成
        mock_response1 = MagicMock()
        mock_response1.full_text_annotation = MagicMock()
        
        mock_word1 = self.create_mock_word("ページ1", 10, 10, 60, 20)
        mock_paragraph1 = MagicMock()
        mock_paragraph1.words = [mock_word1]
        mock_block1 = MagicMock()
        mock_block1.paragraphs = [mock_paragraph1]
        mock_page1 = MagicMock()
        mock_page1.blocks = [mock_block1]
        mock_response1.full_text_annotation.pages = [mock_page1]
        
        mock_response2 = MagicMock()
        mock_response2.full_text_annotation = MagicMock()
        
        mock_word2 = self.create_mock_word("ページ2", 10, 10, 60, 20)
        mock_paragraph2 = MagicMock()
        mock_paragraph2.words = [mock_word2]
        mock_block2 = MagicMock()
        mock_block2.paragraphs = [mock_paragraph2]
        mock_page2 = MagicMock()
        mock_page2.blocks = [mock_block2]
        mock_response2.full_text_annotation.pages = [mock_page2]
        
        result = get_all_words_from_ocr_response([mock_response1, mock_response2])
        
        self.assertEqual(len(result), 2)

    def test_get_all_words_from_ocr_response_empty_response(self):
        """空のOCRレスポンスの処理テスト"""
        result = get_all_words_from_ocr_response(None)
        self.assertEqual(result, [])
        
        mock_response = MagicMock()
        mock_response.full_text_annotation = None
        result = get_all_words_from_ocr_response(mock_response)
        self.assertEqual(result, [])

    @patch('src.processor.logger')
    def test_correct_bounding_boxes_success(self, mock_logger):
        """bounding box補正の成功ケーステスト"""
        extraction_result = {
            "company_name": {
                "value": "テスト会社",
                "bbox": {"x": 10, "y": 10, "width": 80, "height": 20}
            }
        }
        
        mock_ocr_response = MagicMock()
        
        # get_all_words_from_ocr_responseをモック
        with patch('src.processor.get_all_words_from_ocr_response') as mock_get_words:
            mock_words = [self.create_mock_word("テスト会社", 10, 10, 80, 20)]
            mock_get_words.return_value = mock_words
            
            result = correct_bounding_boxes(extraction_result, mock_ocr_response)
            
            # 結果が返されることを確認
            self.assertIsInstance(result, dict)
            self.assertIn("company_name", result)
            
            # ログが正しく出力されることを確認
            mock_logger.info.assert_any_call("Starting bounding box correction using OCR data.")
            mock_logger.info.assert_any_call("Found 1 words in OCR data for correction.")
            mock_logger.info.assert_any_call("Bounding box correction process completed.")

    @patch('src.processor.logger')
    def test_correct_bounding_boxes_no_ocr_words(self, mock_logger):
        """OCR単語がない場合のテスト"""
        extraction_result = {"test": "data"}
        mock_ocr_response = MagicMock()
        
        with patch('src.processor.get_all_words_from_ocr_response') as mock_get_words:
            mock_get_words.return_value = []
            
            result = correct_bounding_boxes(extraction_result, mock_ocr_response)
            
            # 元のデータがそのまま返されることを確認
            self.assertEqual(result, extraction_result)
            
            # 警告ログが出力されることを確認
            mock_logger.warning.assert_called_once_with("No OCR words found in the response. Skipping bounding box correction.")

    @patch('src.processor.logger')
    def test_correct_bounding_boxes_error_handling(self, mock_logger):
        """bounding box補正でのエラーハンドリングテスト"""
        extraction_result = {"test": "data"}
        mock_ocr_response = MagicMock()
        
        with patch('src.processor.correct_bounding_boxes_recursive') as mock_correct_recursive:
            # get_all_words_from_ocr_responseは正常に動作させて、
            # correct_bounding_boxes_recursiveでエラーを発生させる
            with patch('src.processor.get_all_words_from_ocr_response') as mock_get_words:
                mock_get_words.return_value = [self.create_mock_word("test", 10, 10, 20, 20)]
                mock_correct_recursive.side_effect = Exception("Processing error")
                
                result = correct_bounding_boxes(extraction_result, mock_ocr_response)
                
                # 元のデータがそのまま返されることを確認
                self.assertEqual(result, extraction_result)
                
                # エラーログが出力されることを確認
                mock_logger.error.assert_called_once()

    @patch('src.processor.logger')
    def test_process_extracted_data_success(self, mock_logger):
        """抽出データ処理の成功ケーステスト"""
        extracted_data = self.test_extraction_data
        mock_ocr_response = MagicMock()
        
        with patch('src.processor.correct_bounding_boxes') as mock_correct_bbox:
            corrected_data = {"corrected": True, **extracted_data}
            mock_correct_bbox.return_value = corrected_data
            
            result = process_extracted_data(
                extracted_data, 
                mock_ocr_response, 
                "test_request_id", 
                "test_s3_key"
            )
            
            # 成功結果の検証
            self.assertTrue(result["processed"])
            self.assertEqual(result["original_data"], extracted_data)
            self.assertEqual(result["corrected_data"], corrected_data)
            self.assertIsNone(result["error"])
            self.assertIn("process_timestamp", result)
            
            # ログが正しく出力されることを確認
            mock_logger.info.assert_any_call("Processing extracted data for request test_request_id, file test_s3_key")
            mock_logger.info.assert_any_call("Attempting bounding box correction for test_s3_key")
            mock_logger.info.assert_any_call("Data processing completed successfully for test_s3_key")

    @patch('src.processor.logger')
    def test_process_extracted_data_no_structured_data(self, mock_logger):
        """構造化データがない場合のテスト"""
        # raw_responseのみのデータ
        extracted_data = {"raw_response": "非構造化テキスト"}
        
        result = process_extracted_data(
            extracted_data, 
            None, 
            "test_request_id", 
            "test_s3_key"
        )
        
        # 処理失敗結果の検証
        self.assertFalse(result["processed"])
        self.assertEqual(result["original_data"], extracted_data)
        self.assertIsNone(result["corrected_data"])
        self.assertEqual(result["error"], "No structured data from LLM")
        
        # 警告ログが出力されることを確認
        mock_logger.warning.assert_called_once_with("No structured data from LLM for test_s3_key. Skipping further processing.")

    @patch('src.processor.logger')
    def test_process_extracted_data_no_ocr_response(self, mock_logger):
        """OCRレスポンスがない場合のテスト"""
        extracted_data = self.test_extraction_data
        
        result = process_extracted_data(
            extracted_data, 
            None, 
            "test_request_id", 
            "test_s3_key"
        )
        
        # 成功結果の検証（OCR補正なし）
        self.assertTrue(result["processed"])
        self.assertEqual(result["corrected_data"], extracted_data)
        
        # ログが正しく出力されることを確認
        mock_logger.info.assert_any_call("No OCR data provided for test_s3_key, skipping bounding box correction.")

    @patch('src.processor.logger')
    def test_process_extracted_data_empty_or_invalid_input(self, mock_logger):
        """空または無効な入力データのテスト"""
        # 空の辞書
        result = process_extracted_data({}, None, "test_request_id", "test_s3_key")
        self.assertFalse(result["processed"])
        self.assertEqual(result["error"], "No structured data from LLM")
        
        # None
        result = process_extracted_data(None, None, "test_request_id", "test_s3_key")
        self.assertFalse(result["processed"])
        self.assertEqual(result["error"], "No structured data from LLM")
        
        # 辞書でない
        result = process_extracted_data("invalid", None, "test_request_id", "test_s3_key")
        self.assertFalse(result["processed"])
        self.assertEqual(result["error"], "No structured data from LLM")

    @patch('src.processor.logger')
    def test_process_extracted_data_processing_error(self, mock_logger):
        """処理中エラーのテスト"""
        extracted_data = self.test_extraction_data
        mock_ocr_response = MagicMock()
        
        with patch('src.processor.correct_bounding_boxes') as mock_correct_bbox:
            # エラーを発生させる
            mock_correct_bbox.side_effect = Exception("Processing error")
            
            result = process_extracted_data(
                extracted_data, 
                mock_ocr_response, 
                "test_request_id", 
                "test_s3_key"
            )
            
            # エラー結果の検証
            self.assertFalse(result["processed"])
            self.assertEqual(result["original_data"], extracted_data)
            self.assertEqual(result["error"], "Processing error")
            
            # エラーログが出力されることを確認
            mock_logger.error.assert_called_once()

    def test_parse_date_various_formats(self):
        """様々な日付形式の解析テスト"""
        # ISO形式
        result = parse_date("2023-12-25")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 25)
        
        # スラッシュ区切り
        result = parse_date("2023/12/25")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2023)
        
        # 和暦形式
        result = parse_date("2023年12月25日")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2023)
        
        # ドット区切り
        result = parse_date("2023.12.25")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2023)

    def test_parse_date_invalid_formats(self):
        """無効な日付形式のテスト"""
        # 無効な形式
        result = parse_date("invalid date")
        self.assertIsNone(result)
        
        # 空文字列
        result = parse_date("")
        self.assertIsNone(result)
        
        # None
        result = parse_date(None)
        self.assertIsNone(result)

    @patch('src.processor.logger')
    def test_parse_date_logging(self, mock_logger):
        """parse_dateでのログ出力テスト"""
        parse_date("無効な日付形式")
        
        # 警告ログが出力されることを確認
        mock_logger.warning.assert_called_once()

    def test_integration_full_processing_pipeline(self):
        """完全な処理パイプラインの統合テスト"""
        # 実際のOCRレスポンスに近いデータ構造を模擬
        extracted_data = {
            "issuer_name": {
                "value": "株式会社テスト",
                "bbox": {"x": 10, "y": 10, "width": 120, "height": 25}
            },
            "amount_info": {
                "total_amount": {
                    "value": "¥10,000",
                    "bbox": {"x": 200, "y": 50, "width": 80, "height": 20}
                },
                "tax_breakdown": [
                    {
                        "tax_rate": {"value": 0.1},
                        "amount_consumption_tax": {
                            "value": 1000,
                            "bbox": {"x": 200, "y": 80, "width": 60, "height": 20}
                        }
                    }
                ]
            }
        }
        
        # OCR単語のモック
        ocr_words = [
            self.create_mock_word("株式会社テスト", 10, 10, 120, 25),
            self.create_mock_word("¥10,000", 200, 50, 80, 20),
            self.create_mock_word("1000", 200, 80, 60, 20)
        ]
        
        # OCRレスポンスのモック
        mock_ocr_response = MagicMock()
        
        with patch('src.processor.get_all_words_from_ocr_response') as mock_get_words:
            mock_get_words.return_value = ocr_words
            
            # 処理実行
            result = process_extracted_data(
                extracted_data, 
                mock_ocr_response, 
                "integration_test_id", 
                "integration_test.pdf"
            )
            
            # 結果検証
            self.assertTrue(result["processed"])
            self.assertIsNone(result["error"])
            self.assertIsNotNone(result["corrected_data"])
            self.assertIn("issuer_name", result["corrected_data"])
            self.assertIn("amount_info", result["corrected_data"])


if __name__ == '__main__':
    unittest.main()
