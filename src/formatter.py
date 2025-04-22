\
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.utils.logger import setup_logger

logger = setup_logger()

def create_clip_item(field_name: str, value: Any, bbox: Optional[Dict[str, float]], confidence: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """
    単一のフィールド情報からクリップアイテムを作成する。
    bbox がない、または不正な場合は None を返す。
    """
    if bbox is None:
        logger.debug(f"Skipping clip item for '{field_name}' due to missing bounding box.")
        return None

    # bbox の形式を検証 (x, y, width, height が存在するか)
    x_min = bbox.get('x')
    y_min = bbox.get('y')
    width = bbox.get('width')
    height = bbox.get('height')

    if None in [x_min, y_min, width, height] or width < 0 or height < 0:
        logger.warning(f"Invalid bbox format for field '{field_name}': {bbox}. Skipping clip item.")
        return None

    x_max = x_min + width
    y_max = y_min + height

    # 座標値が負でないことを確認 (オプションだが推奨)
    if x_min < 0 or y_min < 0 or x_max < 0 or y_max < 0:
         logger.warning(f"Negative coordinate values in bbox for field '{field_name}': {bbox}. Proceeding, but check OCR/LLM output.")
         # ここでは処理を続けるが、ログには残す

    clip_item = {
        "field_name": field_name,
        "value": str(value) if value is not None else "", # 値は文字列に変換
        "position": {
            # 座標は4点のリスト形式で表現
            "bounding_box": [
                {"x": x_min, "y": y_min},
                {"x": x_max, "y": y_min},
                {"x": x_max, "y": y_max},
                {"x": x_min, "y": y_max},
            ]
        }
    }
    if confidence is not None:
        clip_item["confidence"] = confidence

    return clip_item

def convert_to_clips_format_recursive(data: Any, parent_key: str = "") -> List[Dict[str, Any]]:
    """
    補正済みデータを再帰的に探索し、クリップアイテムのリストを生成する。
    'value' と 'bbox' を持つ辞書要素をクリップアイテムに変換する。
    """
    clips = []
    if isinstance(data, dict):
        # "value" と "bbox" を持つフィールドを探索
        if "value" in data and "bbox" in data:
            # bboxがNoneでないことを確認
            if data["bbox"] is not None:
                # フィールド名を決定: 'name' キーがあればそれを使用、なければ親キーを使用
                # 親キーも 'name' もない場合はログを出してスキップ
                field_name_part = data.get('name')
                if field_name_part:
                     field_name = f"{parent_key}.{field_name_part}" if parent_key else field_name_part
                elif parent_key: # nameはないが親キーはある場合
                     field_name = parent_key
                     # logger.debug(f"Using parent key '{parent_key}' as field name for value '{data.get('value')}' because 'name' is missing.")
                else: # nameも親キーもない場合 (通常は発生しないはず)
                     field_name = None
                     logger.warning(f"Could not determine field name for data: {data}. Skipping clip item.")

                if field_name:
                    clip = create_clip_item(
                        field_name=field_name,
                        value=data.get("value"),
                        bbox=data.get("bbox"),
                        confidence=data.get("confidence") # confidenceがあれば渡す
                    )
                    if clip:
                        clips.append(clip)

            # valueやbbox以外のキーも再帰的に探索 (リストの場合を除く)
            # ネストしたフィールド名を生成して渡す
            for key, value in data.items():
                # 'value', 'bbox', 'confidence', 'name' は既に処理済みか、キーとして使用しない
                if key not in ["value", "bbox", "confidence", "name"]:
                    # 現在のフィールド名を親キーとして渡す
                    current_parent_key = f"{parent_key}.{key}" if parent_key else key
                    clips.extend(convert_to_clips_format_recursive(value, current_parent_key))

        else: # "value" と "bbox" を持たない辞書の場合、その中身を探索
             for key, value in data.items():
                 current_key = f"{parent_key}.{key}" if parent_key else key
                 clips.extend(convert_to_clips_format_recursive(value, current_key))

    elif isinstance(data, list):
        # リストの場合は各要素を処理
        # リスト要素のフィールド名をどう扱うか？ (例: parent_key[index])
        # ここでは、リスト内の辞書が自己完結したフィールド情報を持つと仮定し、
        # 親キーを引き継いで再帰呼び出しを行う。
        for index, item in enumerate(data):
            # リストのインデックスをキーに含める場合: list_item_key = f"{parent_key}[{index}]"
            # ここでは親キーをそのまま渡す
            clips.extend(convert_to_clips_format_recursive(item, parent_key))

    # その他の型は無視
    return clips


def format_sqs_message(processed_data: Dict[str, Any], clipping_request_id: str, s3_key: str) -> Dict[str, Any]:
    """
    processorからの出力とリクエスト情報をもとに、SQSに送信する最終的なメッセージを作成する。

    Args:
        processed_data (dict): process_extracted_dataからの出力。
                               'corrected_data' キーに補正済みデータが含まれる想定。
        clipping_request_id (str): クリップ入力依頼ID。
        s3_key (str): 処理対象のS3キー。

    Returns:
        dict: SQSに送信するメッセージペイロード。
    """
    logger.info(f"Formatting SQS message for request {clipping_request_id}, file {s3_key}")

    final_message = {
        "clipping_request_id": clipping_request_id,
        "s3_key": s3_key,
        "status": "error", # デフォルトはエラー
        "clips": [],
        "error_message": processed_data.get("error"),
        "processed_timestamp": processed_data.get("process_timestamp", datetime.utcnow().isoformat())
    }

    # processor.py で処理が成功し、補正済みデータが存在する場合
    if processed_data.get("processed") and processed_data.get("corrected_data"):
        try:
            corrected_data = processed_data["corrected_data"]
            # 補正済みデータからクリップリストを生成
            clips = convert_to_clips_format_recursive(corrected_data)

            if clips:
                final_message["status"] = "success"
                final_message["clips"] = clips
                final_message["error_message"] = None # 成功時はエラーメッセージをクリア
                logger.info(f"Successfully formatted {len(clips)} clips for {s3_key}.")
            else:
                # 補正済みデータはあったが、有効なクリップが生成されなかった場合
                final_message["status"] = "warning" # または "no_clips" など
                final_message["error_message"] = "No valid clips could be generated from the processed data."
                logger.warning(f"No valid clips generated for {s3_key} although processing was marked as successful.")

        except Exception as e:
            logger.error(f"Error during final formatting for {s3_key}: {str(e)}", exc_info=True)
            final_message["status"] = "error"
            final_message["error_message"] = f"Error during final formatting: {str(e)}"
            # clips は空のまま

    elif processed_data.get("error"):
        # processor段階でエラーが発生していた場合
        logger.warning(f"Formatting SQS message with error status for {s3_key} due to processing error: {processed_data['error']}")
        # status と error_message は既に設定されている

    else:
        # 予期しないケース (processed=False だが error もない)
        logger.error(f"Unexpected state in processed_data for {s3_key}. Setting status to error.")
        final_message["status"] = "error"
        final_message["error_message"] = "Unknown error during processing or formatting."

    return final_message
