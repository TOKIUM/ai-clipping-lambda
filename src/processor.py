import json
import uuid
from datetime import datetime
from src.utils.logger import setup_logger

logger = setup_logger()

def process_extracted_data(extracted_data):
    """
    LLMから抽出されたデータを後処理する
    
    Args:
        extracted_data (dict): LLMから抽出されたデータ
        
    Returns:
        dict: 後処理されたデータ
    """
    logger.info("Processing extracted data")
    
    try:
        # 生のレスポンスのみの場合は、そのまま返す
        if "raw_response" in extracted_data:
            logger.warning("Only raw response available, no structured data to process")
            return {
                "processed": False,
                "data": extracted_data,
                "process_timestamp": datetime.utcnow().isoformat()
            }
        
        # クリップ形式に変換
        clips_data = convert_to_clips_format(extracted_data)
        
        processed_data = {
            "processed": True,
            "original": extracted_data,
            "normalized": clips_data,
            "process_timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info("Data processing completed successfully")
        return processed_data
        
    except Exception as e:
        logger.error(f"Error processing extracted data: {str(e)}")
        return {
            "processed": False,
            "error": str(e),
            "original_data": extracted_data,
            "process_timestamp": datetime.utcnow().isoformat()
        }

def convert_to_clips_format(extracted_data):
    """
    LLMから抽出されたデータをクリップ形式に変換する
    
    Args:
        extracted_data (dict): LLMから抽出されたデータ
        
    Returns:
        dict: クリップ形式に変換されたデータ
    """
    logger.info("Converting extracted data to clips format")
    
    # 結果を格納するリスト
    clips = []
    
    # ランダムなリクエストIDを生成（実際の環境では外部から提供される可能性あり）
    clipping_request_id = str(uuid.uuid4())
    
    # 電話番号のクリップ追加
    if "issuer_phone_number" in extracted_data and "bbox" in extracted_data["issuer_phone_number"]:
        phone_data = extracted_data["issuer_phone_number"]
        if phone_data["value"]:  # 値が空でない場合のみ追加
            clips.append(create_clip_item(
                field_name="phone_number",
                field_type=0,
                bbox=phone_data["bbox"]
            ))
    
    # 発行者名のクリップ追加
    if "issuer_name" in extracted_data and "bbox" in extracted_data["issuer_name"]:
        issuer_data = extracted_data["issuer_name"]
        if issuer_data["value"]:
            clips.append(create_clip_item(
                field_name="issuer_name",
                field_type=1,
                bbox=issuer_data["bbox"]
            ))
    
    # 登録番号のクリップ追加
    if "registration_number" in extracted_data and "bbox" in extracted_data["registration_number"]:
        reg_data = extracted_data["registration_number"]
        if reg_data["value"]:
            clips.append(create_clip_item(
                field_name="registrated_number",
                field_type=2,
                bbox=reg_data["bbox"]
            ))
    
    # 金額情報の処理
    if "amount_info" in extracted_data and "tax_breakdown" in extracted_data["amount_info"]:
        tax_breakdown = extracted_data["amount_info"]["tax_breakdown"]
        for tax_item in tax_breakdown:
            if isinstance(tax_item, dict) and "tax_rate" in tax_item:
                tax_rate = tax_item["tax_rate"]["value"]
                
                # 10%の課税対象金額
                if tax_rate == 0.1 and "amount_include_tax" in tax_item:
                    if "bbox" in tax_item["amount_include_tax"]:
                        clips.append(create_clip_item(
                            field_name="taxable_amount_for_10_percent",
                            field_type=5,
                            bbox=tax_item["amount_include_tax"]["bbox"]
                        ))
                
                # 10%の税抜金額
                if tax_rate == 0.1 and "amount_exclude_tax" in tax_item:
                    if "bbox" in tax_item["amount_exclude_tax"]:
                        clips.append(create_clip_item(
                            field_name="amount_without_tax_for_10_percent",
                            field_type=6,
                            bbox=tax_item["amount_exclude_tax"]["bbox"]
                        ))
                
                # 10%の消費税額
                if tax_rate == 0.1 and "amount_consumption_tax" in tax_item:
                    if "bbox" in tax_item["amount_consumption_tax"]:
                        clips.append(create_clip_item(
                            field_name="tax_amount_for_10_percent",
                            field_type=7,
                            bbox=tax_item["amount_consumption_tax"]["bbox"]
                        ))
                
                # 8%の課税対象金額
                if tax_rate == 0.08 and "amount_include_tax" in tax_item:
                    if "bbox" in tax_item["amount_include_tax"]:
                        clips.append(create_clip_item(
                            field_name="taxable_amount_for_8_percent",
                            field_type=8,
                            bbox=tax_item["amount_include_tax"]["bbox"]
                        ))
                
                # 8%の税抜金額
                if tax_rate == 0.08 and "amount_exclude_tax" in tax_item:
                    if "bbox" in tax_item["amount_exclude_tax"]:
                        clips.append(create_clip_item(
                            field_name="amount_without_tax_for_8_percent",
                            field_type=9,
                            bbox=tax_item["amount_exclude_tax"]["bbox"]
                        ))
                
                # 8%の消費税額
                if tax_rate == 0.08 and "amount_consumption_tax" in tax_item:
                    if "bbox" in tax_item["amount_consumption_tax"]:
                        clips.append(create_clip_item(
                            field_name="tax_amount_for_8_percent",
                            field_type=10,
                            bbox=tax_item["amount_consumption_tax"]["bbox"]
                        ))
    
    # 非課税金額があれば追加
    if "amount_info" in extracted_data and "tax_free_amount" in extracted_data["amount_info"]:
        tax_free_data = extracted_data["amount_info"]["tax_free_amount"]
        if tax_free_data["value"] and "bbox" in tax_free_data:
            clips.append(create_clip_item(
                field_name="taxable_amount_for_0_percent",
                field_type=11,
                bbox=tax_free_data["bbox"]
            ))
    
    # 源泉徴収税額があれば追加
    if "amount_info" in extracted_data and "amount_withholding" in extracted_data["amount_info"]:
        withholding_data = extracted_data["amount_info"]["amount_withholding"]
        if withholding_data["value"] and "bbox" in withholding_data:
            clips.append(create_clip_item(
                field_name="withholding_tax_amount",
                field_type=12,
                bbox=withholding_data["bbox"]
            ))
    
    # 支払期日の処理
    if "due_date" in extracted_data and "bbox" in extracted_data["due_date"]:
        due_date_data = extracted_data["due_date"]
        if due_date_data["value"]:
            clips.append(create_clip_item(
                field_name="due_date",
                field_type=4,
                bbox=due_date_data["bbox"]
            ))
    
    # 支払期日の補足情報があれば追加
    if "due_date_sub_info" in extracted_data and "bbox" in extracted_data["due_date_sub_info"]:
        due_date_sub_data = extracted_data["due_date_sub_info"]
        if due_date_sub_data["value"]:
            clips.append(create_clip_item(
                field_name="due_date_sub_info",
                field_type=4,  # 同じく支払期日の種別
                bbox=due_date_sub_data["bbox"]
            ))
    
    # 銀行情報の処理
    if "bank_details" in extracted_data and "bbox" in extracted_data["bank_details"]:
        # 銀行情報全体をまとめてクリップとして追加
        clips.append(create_clip_item(
            field_name="bank",
            field_type=3,
            bbox=extracted_data["bank_details"]["bbox"]
        ))
        
        # 銀行情報の各項目も個別に追加（必要な場合）
        bank_details = extracted_data["bank_details"]
        for key in ["bank_name", "branch_name", "account_type", "bank_code", "account_number", "account_holder"]:
            if key in bank_details and "bbox" in bank_details[key] and bank_details[key]["value"]:
                # 口座名義人だけはfield_nameを変えて別途追加
                if key == "account_holder":
                    clips.append(create_clip_item(
                        field_name="account_holder",
                        field_type=3,  # 銀行関連情報
                        bbox=bank_details[key]["bbox"]
                    ))
    
    # 手数料負担先があれば追加
    if "fee_payer" in extracted_data and "bbox" in extracted_data["fee_payer"]:
        fee_data = extracted_data["fee_payer"]
        if fee_data["value"]:
            clips.append(create_clip_item(
                field_name="fee_payer",
                field_type=3,  # 銀行関連情報
                bbox=fee_data["bbox"]
            ))
    
    return {
        "clipping_request_id": clipping_request_id,
        "clips": clips
    }

def create_clip_item(field_name, field_type, bbox, reliability_score=1, page=1):
    """
    クリップアイテムを作成する
    
    Args:
        field_name (str): フィールド名
        field_type (int): フィールドタイプ
        bbox (dict): 座標情報
        reliability_score (float): 信頼度スコア。デフォルトは1。
        page (int): ページ番号。デフォルトは1。
    
    Returns:
        dict: クリップアイテム
    """
    return {
        "field_name": field_name,
        "field_type": field_type,
        "x_coordinate": bbox["x"],
        "y_coordinate": bbox["y"],
        "width": bbox["width"],
        "height": bbox["height"],
        "page": page,
        "reliability_score": reliability_score
    }

def parse_date(date_str):
    """
    様々な形式の日付文字列をdatetimeオブジェクトに変換する
    
    Args:
        date_str (str): 日付文字列
        
    Returns:
        datetime: 変換されたdatetimeオブジェクト
    """
    # よくある日付形式のリスト
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y年%m月%d日",
        "%Y.%m.%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m-%d-%Y",
        "%m/%d/%Y",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except:
            continue
    
    # いずれの形式にも合致しない場合は例外を発生
    raise ValueError(f"Could not parse date: {date_str}")