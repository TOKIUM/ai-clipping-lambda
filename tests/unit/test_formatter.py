import unittest
from unittest.mock import patch, MagicMock
import json
from src.formatter import create_clip_item, convert_to_clips_format_recursive, format_sqs_message


class TestFormatter(unittest.TestCase):

    def test_create_clip_item_valid_bbox(self):
        """正常なbboxでクリップアイテムが作成されることをテスト"""
        bbox = {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
        result = create_clip_item("test_field", "test_value", bbox, confidence=0.95, page=1)
        
        expected = {
            "field_name": "test_field",
            "value": "test_value",
            "position": {
                "bounding_box": [
                    {"x": 10.0, "y": 20.0},
                    {"x": 110.0, "y": 20.0},
                    {"x": 110.0, "y": 70.0},
                    {"x": 10.0, "y": 70.0},
                ]
            },
            "page": 1,
            "confidence": 0.95
        }
        
        self.assertEqual(result, expected)

    def test_create_clip_item_missing_bbox(self):
        """bboxがNoneの場合にNoneが返されることをテスト"""
        result = create_clip_item("test_field", "test_value", None)
        self.assertIsNone(result)

    def test_create_clip_item_invalid_bbox_missing_fields(self):
        """bboxに必要なフィールドが不足している場合にNoneが返されることをテスト"""
        bbox = {"x": 10.0, "y": 20.0}  # widthとheightが不足
        result = create_clip_item("test_field", "test_value", bbox)
        self.assertIsNone(result)

    def test_create_clip_item_negative_dimensions(self):
        """負の幅や高さの場合にNoneが返されることをテスト"""
        bbox = {"x": 10.0, "y": 20.0, "width": -10.0, "height": 50.0}
        result = create_clip_item("test_field", "test_value", bbox)
        self.assertIsNone(result)

    def test_create_clip_item_negative_coordinates(self):
        """負の座標でも処理を継続することをテスト（警告ログ付き）"""
        bbox = {"x": -10.0, "y": -20.0, "width": 100.0, "height": 50.0}
        with patch('src.formatter.logger') as mock_logger:
            result = create_clip_item("test_field", "test_value", bbox)
            
            # 警告ログが出力されることを確認
            mock_logger.warning.assert_called_once()
            
            # 処理は継続されることを確認
            self.assertIsNotNone(result)
            self.assertEqual(result["field_name"], "test_field")

    def test_create_clip_item_none_value(self):
        """値がNoneの場合に空文字列に変換されることをテスト"""
        bbox = {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
        result = create_clip_item("test_field", None, bbox)
        
        self.assertEqual(result["value"], "")

    def test_convert_to_clips_format_recursive_simple_value_bbox(self):
        """valueとbboxを持つ単純なデータのテスト"""
        data = {
            "field1": {
                "value": "test_value",
                "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0},
                "confidence": 0.9
            }
        }
        
        result = convert_to_clips_format_recursive(data)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["field_name"], "field1")
        self.assertEqual(result[0]["value"], "test_value")

    def test_convert_to_clips_format_recursive_nested_structure(self):
        """ネストした構造のデータのテスト"""
        data = {
            "level1": {
                "level2": {
                    "field1": {
                        "value": "nested_value",
                        "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
                    }
                }
            }
        }
        
        result = convert_to_clips_format_recursive(data)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["field_name"], "level1.level2.field1")

    def test_convert_to_clips_format_recursive_bank_details(self):
        """bank_detailsの特別処理のテスト"""
        data = {
            "bank_details": {
                "bbox": {"x": 10.0, "y": 20.0, "width": 200.0, "height": 100.0},
                "bank_name": {
                    "value": "Test Bank",
                    "bbox": {"x": 15.0, "y": 25.0, "width": 100.0, "height": 30.0}
                }
            }
        }
        
        result = convert_to_clips_format_recursive(data)
        
        # bank_detailsのbboxのみがクリップされ、field_nameは"bank"になる
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["field_name"], "bank")

    def test_convert_to_clips_format_recursive_tax_breakdown_10_percent(self):
        """tax_breakdown 10%の特別処理のテスト"""
        data = {
            "amount_info": {
                "tax_breakdown": [
                    {
                        "tax_rate": {"value": 0.1},
                        "amount_include_tax": {
                            "value": "1100",
                            "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}
                        },
                        "amount_consumption_tax": {
                            "value": "100",
                            "bbox": {"x": 10.0, "y": 60.0, "width": 100.0, "height": 30.0}
                        }
                    }
                ]
            }
        }
        
        result = convert_to_clips_format_recursive(data)
        
        # taxable_amount_for_10_percent と tax_amount_for_10_percent がクリップされる
        field_names = [clip["field_name"] for clip in result]
        self.assertIn("taxable_amount_for_10_percent", field_names)
        self.assertIn("tax_amount_for_10_percent", field_names)

    def test_convert_to_clips_format_recursive_tax_breakdown_8_percent(self):
        """tax_breakdown 8%の特別処理のテスト"""
        data = {
            "amount_info": {
                "tax_breakdown": [
                    {
                        "tax_rate": {"value": 0.08},
                        "taxable_amount": {
                            "value": "1000",
                            "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}
                        }
                    }
                ]
            }
        }
        
        result = convert_to_clips_format_recursive(data)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["field_name"], "taxable_amount_for_8_percent")

    def test_convert_to_clips_format_recursive_tax_breakdown_0_percent(self):
        """tax_breakdown 0%の特別処理のテスト"""
        data = {
            "amount_info": {
                "tax_breakdown": [
                    {
                        "tax_rate": {"value": 0.0},
                        "amount_include_tax": {
                            "value": "1000",
                            "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}
                        }
                    }
                ]
            }
        }
        
        result = convert_to_clips_format_recursive(data)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["field_name"], "taxable_amount_for_0_percent")

    def test_convert_to_clips_format_recursive_amount_mapping(self):
        """金額フィールドのマッピングのテスト"""
        data = {
            "amount_info": {
                "amount_withholding": {
                    "value": "500",
                    "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 30.0}
                },
                "tax_free_amount": {
                    "value": "1000",
                    "bbox": {"x": 10.0, "y": 60.0, "width": 100.0, "height": 30.0}
                },
                "total_amount": {
                    "value": "5000",
                    "bbox": {"x": 10.0, "y": 100.0, "width": 100.0, "height": 30.0}
                }
            }
        }
        
        result = convert_to_clips_format_recursive(data)
        
        field_names = [clip["field_name"] for clip in result]
        self.assertIn("withholding_tax_amount", field_names)
        self.assertIn("taxable_amount_for_0_percent", field_names)
        self.assertIn("total_amount", field_names)

    def test_convert_to_clips_format_recursive_page_inheritance(self):
        """ページ情報の継承のテスト"""
        data = {
            "page": 2,
            "field1": {
                "value": "test_value",
                "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
            }
        }
        
        result = convert_to_clips_format_recursive(data)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["page"], 2)

    def test_format_sqs_message_success(self):
        """正常なSQSメッセージフォーマットのテスト"""
        processed_data = {
            "processed": True,
            "corrected_data": {
                "field1": {
                    "value": "test_value",
                    "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0},
                    "confidence": 0.9
                },
                "page": 1
            }
        }
        
        result = format_sqs_message(processed_data, "test_request_id", "test_s3_key")
        
        expected_structure = {
            "clipping_request_id": "test_request_id",
            "clips": [
                {
                    "field_name": "field1",
                    "value": "test_value",
                    "x_coordinate": 10.0,
                    "y_coordinate": 20.0,
                    "width": 100.0,
                    "height": 50.0,
                    "page": 1,
                    "reliability_score": 0.9
                }
            ]
        }
        
        self.assertEqual(result, expected_structure)

    def test_format_sqs_message_processing_error(self):
        """処理エラー時のSQSメッセージフォーマットのテスト"""
        processed_data = {
            "processed": False,
            "error": "Test error message"
        }
        
        result = format_sqs_message(processed_data, "test_request_id", "test_s3_key")
        
        expected = {
            "clipping_request_id": "test_request_id",
            "clips": []
        }
        
        self.assertEqual(result, expected)

    def test_format_sqs_message_zero_bbox_filtering(self):
        """すべて0のbboxが除外されることのテスト"""
        processed_data = {
            "processed": True,
            "corrected_data": {
                "field1": {
                    "value": "test_value",
                    "bbox": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
                },
                "field2": {
                    "value": "valid_value",
                    "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
                }
            }
        }
        
        result = format_sqs_message(processed_data, "test_request_id", "test_s3_key")
        
        # field1（すべて0のbbox）は除外され、field2のみがクリップされる
        self.assertEqual(len(result["clips"]), 1)
        self.assertEqual(result["clips"][0]["field_name"], "field2")

    def test_format_sqs_message_bank_duplicate_removal(self):
        """bankフィールドの重複除去のテスト"""
        processed_data = {
            "processed": True,
            "corrected_data": {
                "bank_details": {
                    "bbox": {"x": 10.0, "y": 20.0, "width": 200.0, "height": 100.0}
                }
            }
        }
        
        # 2回処理して重複がないことを確認するために、同じbboxを持つbank要素を複数作成
        with patch('src.formatter.convert_to_clips_format_recursive') as mock_convert:
            mock_convert.return_value = [
                {
                    "field_name": "bank",
                    "value": "",
                    "position": {
                        "bounding_box": [
                            {"x": 10.0, "y": 20.0},
                            {"x": 210.0, "y": 20.0},
                            {"x": 210.0, "y": 120.0},
                            {"x": 10.0, "y": 120.0},
                        ]
                    },
                    "page": 1
                },
                {
                    "field_name": "bank",
                    "value": "",
                    "position": {
                        "bounding_box": [
                            {"x": 10.0, "y": 20.0},
                            {"x": 210.0, "y": 20.0},
                            {"x": 210.0, "y": 120.0},
                            {"x": 10.0, "y": 120.0},
                        ]
                    },
                    "page": 1
                }
            ]
            
            result = format_sqs_message(processed_data, "test_request_id", "test_s3_key")
            
            # 重複したbankクリップは1つのみになる
            self.assertEqual(len(result["clips"]), 1)
            self.assertEqual(result["clips"][0]["field_name"], "bank")

    def test_format_sqs_message_invalid_bbox_format(self):
        """無効なbbox形式の処理のテスト"""
        processed_data = {
            "processed": True,
            "corrected_data": {
                "field1": {
                    "value": "test_value",
                    "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
                }
            }
        }
        
        with patch('src.formatter.convert_to_clips_format_recursive') as mock_convert:
            # 無効なbbox形式のクリップを返す
            mock_convert.return_value = [
                {
                    "field_name": "field1",
                    "value": "test_value",
                    "position": {
                        "bounding_box": [{"x": 10.0}]  # 不完全なbbox
                    },
                    "page": 1
                }
            ]
            
            result = format_sqs_message(processed_data, "test_request_id", "test_s3_key")
            
            # 無効なbboxのクリップは除外される
            self.assertEqual(len(result["clips"]), 0)

    @patch('src.formatter.logger')
    def test_convert_to_clips_format_recursive_logging(self, mock_logger):
        """ログ出力のテスト"""
        data = {
            "field1": {
                "value": "test_value",
                "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
            }
        }
        
        convert_to_clips_format_recursive(data)
        
        # 適切なログが出力されることを確認
        mock_logger.info.assert_called()

    def test_convert_to_clips_format_recursive_list_processing(self):
        """リスト処理のテスト（tax_breakdown以外）"""
        data = {
            "items": [
                {
                    "field1": {
                        "value": "value1",
                        "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0}
                    }
                },
                {
                    "field2": {
                        "value": "value2",
                        "bbox": {"x": 10.0, "y": 80.0, "width": 100.0, "height": 50.0}
                    }
                }
            ]
        }
        
        result = convert_to_clips_format_recursive(data)
        
        self.assertEqual(len(result), 2)
        field_names = [clip["field_name"] for clip in result]
        self.assertIn("items.field1", field_names)
        self.assertIn("items.field2", field_names)


if __name__ == '__main__':
    unittest.main()
