import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.utils.logger import setup_logger

logger = setup_logger()

def create_clip_item(field_name: str, value: Any, bbox: Optional[Dict[str, float]], confidence: Optional[float] = None, page: Optional[int] = 0) -> Optional[Dict[str, Any]]:
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
        "value": str(value) if value is not None else "", # 値は文字列に変換 (内部処理用)
        "position": {
            # 座標は4点のリスト形式で表現
            "bounding_box": [
                {"x": x_min, "y": y_min},
                {"x": x_max, "y": y_min},
                {"x": x_max, "y": y_max},
                {"x": x_min, "y": y_max},
            ]
        },
        "page": page # ページ情報を追加
    }
    if confidence is not None:
        clip_item["confidence"] = confidence

    return clip_item

def convert_to_clips_format_recursive(data: Any, parent_key: str = "", page: int = 0) -> List[Dict[str, Any]]:
    """
    補正済みデータを再帰的に探索し、内部形式のクリップアイテムのリストを生成する。
    'value' と 'bbox' を持つ辞書要素をクリップアイテムに変換する。
    フィールド名のマッピングルールを適用する。
    """
    clips = []
    # ページ情報を抽出 (存在すれば)
    current_page = data.get("page", page) if isinstance(data, dict) else page

    if isinstance(data, dict):
        # "value" と "bbox" を持つフィールドを探索
        if "value" in data and "bbox" in data:
            if data["bbox"] is not None:
                # フィールド名を決定: 'name' キーがあればそれを使用、なければ親キーを使用
                field_name_part = data.get('name') # 'name' は通常、リスト内の要素のキー (例: 'bank_name')
                # 親キーと name から基本的なフィールド名を構築
                if parent_key and field_name_part:
                    base_field_name = f"{parent_key}.{field_name_part}"
                elif field_name_part:
                    base_field_name = field_name_part
                elif parent_key:
                    base_field_name = parent_key
                else:
                    base_field_name = None
                    logger.warning(f"Could not determine base field name for data: {data}. Skipping clip item.")

                if base_field_name:
                    final_field_name = base_field_name # デフォルト

                    # --- マッピングルール ---
                    # 1. bank_details の下の要素は 'bank' にする
                    if parent_key.startswith("bank_details"):
                         final_field_name = "bank"
                    # 2. tax_breakdown の中の特定フィールドは税率に応じて変更 (リスト処理側で対応)
                    #    ここでは tax_breakdown の中の value/bbox を持つ要素は処理しない想定
                    elif parent_key.startswith("tax_breakdown"):
                         final_field_name = None # スキップ (リスト処理に任せる)


                    if final_field_name:
                        clip = create_clip_item(
                            field_name=final_field_name,
                            value=data.get("value"),
                            bbox=data.get("bbox"),
                            confidence=data.get("confidence"),
                            page=current_page # ページ情報を渡す
                        )
                        if clip:
                            # 'bank' フィールドの重複を避けるかどうかの考慮
                            # 現状では重複を許容（複数の銀行情報 bbox があれば複数クリップされる）
                            clips.append(clip)

            # valueやbbox以外のキーも再帰的に探索
            for key, value in data.items():
                # 'value', 'bbox', 'confidence', 'name', 'page' は既に処理済みか、キーとして使用しない
                if key not in ["value", "bbox", "confidence", "name", "page"]:
                    current_parent_key = f"{parent_key}.{key}" if parent_key else key
                    # ページ情報を引き継いで再帰呼び出し
                    clips.extend(convert_to_clips_format_recursive(value, current_parent_key, current_page))

        else: # "value" と "bbox" を持たない辞書の場合、その中身を探索
             for key, value in data.items():
                 # 'page' キーは特別扱いしない
                 current_key = f"{parent_key}.{key}" if parent_key else key
                 # ページ情報を引き継いで再帰呼び出し
                 clips.extend(convert_to_clips_format_recursive(value, current_key, current_page))

    elif isinstance(data, list):
        # --- tax_breakdown リストの特別処理 ---
        if parent_key == "tax_breakdown":
            for item in data:
                 # リストアイテムのページ情報を取得 (存在すれば)
                 item_page = item.get("page", page) if isinstance(item, dict) else page
                 if isinstance(item, dict) and "tax_rate" in item:
                    tax_rate_data = item.get("tax_rate") # tax_rate が value/bbox を持つ辞書の場合がある
                    tax_rate = None
                    if isinstance(tax_rate_data, dict) and "value" in tax_rate_data:
                        try:
                            tax_rate = float(tax_rate_data["value"])
                        except (ValueError, TypeError):
                             logger.warning(f"Could not parse tax_rate value: {tax_rate_data.get('value')}")
                    elif isinstance(tax_rate_data, (int, float, str)): # 文字列の場合も考慮
                         try:
                             tax_rate = float(tax_rate_data)
                         except (ValueError, TypeError):
                             logger.warning(f"Could not parse tax_rate value: {tax_rate_data}")


                    rate_suffix = ""
                    field_prefix_map = {
                        "taxable_amount": "taxable_amount",
                        "amount_without_tax": "amount_without_tax",
                        "tax_amount": "tax_amount"
                    }
                    # 税率の比較は浮動小数点数の誤差を考慮する (例: 0.1 と 0.08)
                    if tax_rate is not None:
                        if abs(tax_rate - 0.1) < 1e-9:
                            rate_suffix = "_for_10_percent"
                        elif abs(tax_rate - 0.08) < 1e-9:
                            rate_suffix = "_for_8_percent"
                        elif abs(tax_rate - 0.0) < 1e-9:
                             rate_suffix = "_for_0_percent" # 0% も追加

                    if rate_suffix:
                        # 各金額フィールド (taxable_amount, amount_without_tax, tax_amount) を処理
                        for field_key, target_field_name_base in field_prefix_map.items():
                            if field_key in item and isinstance(item[field_key], dict) and "value" in item[field_key] and "bbox" in item[field_key]:
                                clip = create_clip_item(
                                    field_name=f"{target_field_name_base}{rate_suffix}",
                                    value=item[field_key].get("value"),
                                    bbox=item[field_key].get("bbox"),
                                    confidence=item[field_key].get("confidence"),
                                    page=item_page # アイテムごとのページ情報
                                )
                                if clip:
                                    clips.append(clip)
                    else:
                         logger.debug(f"Tax rate ({tax_rate}) does not match 10%, 8%, or 0%. Skipping specific tax field mapping for item.")
                         # 特定税率以外の項目も通常の再帰処理にかける場合
                         # clips.extend(convert_to_clips_format_recursive(item, parent_key, item_page))

                 else:
                     # tax_rate がない、または item が辞書でない場合、通常の再帰処理
                     clips.extend(convert_to_clips_format_recursive(item, parent_key, item_page))


        else: # tax_breakdown 以外のリスト
            for index, item in enumerate(data):
                # リスト内の要素を再帰的に処理。親キーとページ情報を引き継ぐ
                item_page = item.get("page", page) if isinstance(item, dict) else page
                clips.extend(convert_to_clips_format_recursive(item, parent_key, item_page))

    return clips


def format_sqs_message(processed_data: Dict[str, Any], clipping_request_id: str, s3_key: str) -> Dict[str, Any]:
    """
    processorからの出力とリクエスト情報をもとに、SQSに送信する最終的なメッセージを作成する。
    要求仕様に合わせた形式に変換する。

    Args:
        processed_data (dict): process_extracted_dataからの出力。
                               'corrected_data' キーに補正済みデータが含まれる想定。
        clipping_request_id (str): クリップ入力依頼ID。
        s3_key (str): 処理対象のS3キー (ログ出力用)。

    Returns:
        dict: SQSに送信するメッセージペイロード。
    """
    logger.info(f"Formatting SQS message for request {clipping_request_id}, file {s3_key}")

    # SQSメッセージの基本構造 (要求仕様に合わせる)
    final_message = {
        "clipping_request_id": clipping_request_id,
        "clips": [],
    }

    # processor.py で処理が成功し、補正済みデータが存在する場合
    if processed_data.get("processed") and processed_data.get("corrected_data"):
        try:
            corrected_data = processed_data["corrected_data"]
            # 内部形式のクリップリストを生成 (ページ情報は corrected_data のトップレベルにある想定)
            # TODO: ページ情報がどこから来るか確認・調整が必要
            initial_page = corrected_data.get("page", 0) if isinstance(corrected_data, dict) else 0
            internal_clips = convert_to_clips_format_recursive(corrected_data, page=initial_page)

            if internal_clips:
                # 内部形式から要求仕様の形式に変換
                formatted_clips = []
                processed_bank_bboxes = set() # 同じbboxを持つbankクリップをまとめるためのセット

                for clip in internal_clips:
                    bbox_data = None
                    # position.bounding_box から x, y, width, height を抽出
                    if "position" in clip and "bounding_box" in clip["position"]:
                         box_points = clip["position"]["bounding_box"]
                         if len(box_points) == 4:
                             # x, y は左上の座標 (min x, min y)
                             x_min = min(p.get('x', float('inf')) for p in box_points)
                             y_min = min(p.get('y', float('inf')) for p in box_points)
                             x_max = max(p.get('x', float('-inf')) for p in box_points)
                             y_max = max(p.get('y', float('-inf')) for p in box_points)
                             # 有効な座標かチェック
                             if all(v not in [float('inf'), float('-inf')] for v in [x_min, y_min, x_max, y_max]):
                                 width = x_max - x_min
                                 height = y_max - y_min
                                 # 幅と高さが非負であることも確認
                                 if width >= 0 and height >= 0:
                                     bbox_data = {
                                         "x_coordinate": x_min,
                                         "y_coordinate": y_min,
                                         "width": width,
                                         "height": height,
                                     }

                    if bbox_data:
                         # --- bank フィールドの重複排除ロジック ---
                         # field_name が 'bank' の場合、同じ bbox のクリップが既に追加されていないか確認
                         is_duplicate_bank = False
                         if clip.get("field_name") == "bank":
                             # bbox情報をタプルに変換してセットで管理
                             bbox_tuple = (
                                 bbox_data["x_coordinate"],
                                 bbox_data["y_coordinate"],
                                 bbox_data["width"],
                                 bbox_data["height"],
                                 clip.get("page", 0) # ページも考慮
                             )
                             if bbox_tuple in processed_bank_bboxes:
                                 is_duplicate_bank = True
                                 logger.debug(f"Skipping duplicate bank clip for bbox: {bbox_tuple}")
                             else:
                                 processed_bank_bboxes.add(bbox_tuple)

                         if not is_duplicate_bank:
                             formatted_clip = {
                                 "field_name": clip.get("field_name"),
                                 "x_coordinate": bbox_data["x_coordinate"],
                                 "y_coordinate": bbox_data["y_coordinate"],
                                 "width": bbox_data["width"],
                                 "height": bbox_data["height"],
                                 "page": clip.get("page", 0), # 内部クリップからページ情報を取得
                                 "reliability_score": clip.get("confidence") # confidence を reliability_score にマッピング
                             }
                             # reliability_score が None の場合はキー自体を含めないか、デフォルト値を入れるか？ -> 仕様確認。一旦そのまま入れる
                             if formatted_clip["reliability_score"] is None:
                                 # del formatted_clip["reliability_score"] # またはデフォルト値設定
                                 pass # None のままにする

                             formatted_clips.append(formatted_clip)
                    else:
                         logger.warning(f"Could not format clip due to invalid or missing bbox for field '{clip.get('field_name')}': {clip.get('position')}")


                if formatted_clips:
                    final_message["clips"] = formatted_clips
                    logger.info(f"Successfully formatted {len(formatted_clips)} clips for SQS message (request {clipping_request_id}).")
                else:
                    logger.warning(f"No valid clips could be formatted for SQS message (request {clipping_request_id}).")
            else:
                 logger.warning(f"No internal clips were generated for SQS message (request {clipping_request_id}).")


        except Exception as e:
            logger.error(f"Error during final SQS message formatting for request {clipping_request_id}: {str(e)}", exc_info=True)
            # エラーが発生した場合も、clips は空のリストのまま final_message を返す

    # processor 段階でエラーがあった場合や予期しないケースでも、
    # 要求仕様に従い clipping_request_id と空の clips を持つメッセージを返す
    elif processed_data.get("error"):
        logger.warning(f"Formatting empty SQS clips for request {clipping_request_id} due to processing error: {processed_data['error']}")
    else:
        logger.error(f"Unexpected state in processed_data for request {clipping_request_id}. Formatting empty SQS clips.")


    return final_message
