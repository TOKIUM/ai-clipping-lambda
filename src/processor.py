import re
from datetime import datetime
from google.cloud import vision  # Vision APIの型ヒントのためにインポート
from typing import List, Dict, Any, Union  # 型ヒントをインポート
from src.utils.logger import setup_logger

logger = setup_logger()

# --- Bounding Box Corrector ヘルパー関数群 ---

def vertices_to_bbox(vertices):
    """OCRの頂点リストから {'x', 'y', 'width', 'height'} 形式のbboxを計算"""
    if not vertices:
        return None
    x_coords = [v.get('x', 0) for v in vertices]
    y_coords = [v.get('y', 0) for v in vertices]
    min_x = min(x_coords)
    min_y = min(y_coords)
    max_x = max(x_coords)
    max_y = max(y_coords)
    return {
        'x': min_x,
        'y': min_y,
        'width': max_x - min_x,
        'height': max_y - min_y
    }

def bbox_overlap(bbox1, bbox2):
    """2つのbboxが重なるか判定"""
    if not bbox1 or not bbox2:
        return False
    
    # bbox1の範囲
    x1_min, y1_min = bbox1['x'], bbox1['y']
    x1_max, y1_max = x1_min + bbox1['width'], y1_min + bbox1['height']
    
    # bbox2の範囲
    x2_min, y2_min = bbox2['x'], bbox2['y']
    x2_max, y2_max = x2_min + bbox2['width'], y2_min + bbox2['height']
    
    # 重なり判定
    return not (x1_max < x2_min or x2_max < x1_min or y1_max < y2_min or y2_max < y1_min)

def sort_words_naturally(words):
    """OCR単語を自然な読み順（左上から右下へ）にソート"""
    if not words:
        return []
    return sorted(words, key=lambda w: (w.bounding_box.vertices[0].y, w.bounding_box.vertices[0].x))

def normalize_value(value, field_type="text"):
    """値を正規化する"""
    if value is None:
        return ""
    text = str(value).strip()
    
    if field_type == "number":
        text = re.sub(r'[¥,￥\s]', '', text)
        try:
            if '.' in text:
                num = float(text)
                if num == int(num):
                    text = str(int(num))
        except ValueError:
            pass
        return text
        
    elif field_type == "date":
        text = text.replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-').replace('.', '-')
        parts = re.split(r'[-/\s]', text)
        try:
            if len(parts) == 3:
                p1, p2, p3 = parts[0], parts[1], parts[2]
                if len(p1) == 4:
                    year, month, day = p1, p2, p3
                elif len(p3) == 4:
                    year, month, day = p3, p2, p1
                else:
                    return text
                year = year.zfill(4)
                month = month.zfill(2)
                day = day.zfill(2)
                return f"{year}-{month}-{day}"
        except Exception:
            pass
        return text

    else:
        text = text.replace('　', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

def find_matching_word_sequence(target_value, sorted_words, field_type="text"):
    """正規化された値に一致する連続したOCR単語シーケンスを見つける"""
    normalized_target = normalize_value(target_value, field_type)
    if not normalized_target or not sorted_words:
        return None

    n = len(sorted_words)
    for length in range(1, n + 1):
        for i in range(n - length + 1):
            sequence = sorted_words[i : i + length]
            combined_text = "".join([symbol.text for word in sequence for symbol in word.symbols])
            normalized_combined = normalize_value(combined_text, field_type)

            match = False
            if field_type == "number" or field_type == "date":
                if normalized_combined == normalized_target:
                    match = True
            else:
                normalized_combined_text_for_search = normalize_value(combined_text, "text")
                if normalized_combined_text_for_search == normalized_target or normalized_target in normalized_combined_text_for_search:
                    match = True
            
            if match:
                return sequence

    return None

def calculate_minimum_bbox(words):
    """単語リストから最小のbboxを計算"""
    all_vertices = []
    for word in words:
        if word.bounding_box and word.bounding_box.vertices:
            all_vertices.extend(word.bounding_box.vertices)
            
    if not all_vertices:
        return None
        
    vertices_list = [{'x': v.x, 'y': v.y} for v in all_vertices]
    return vertices_to_bbox(vertices_list)

def correct_bounding_boxes_recursive(data, ocr_words):
    """抽出データ内のbboxを再帰的に補正する"""
    if isinstance(data, dict):
        corrected_data = {}
        field_value = data.get("value")
        llm_bbox = data.get("bbox")
        
        if field_value is not None and isinstance(llm_bbox, dict) and all(k in llm_bbox for k in ['x', 'y', 'width', 'height']):
            overlapping_words = []
            for word in ocr_words:
                if word.bounding_box and word.bounding_box.vertices:
                    ocr_bbox = vertices_to_bbox([{'x': v.x, 'y': v.y} for v in word.bounding_box.vertices])
                    if ocr_bbox and bbox_overlap(llm_bbox, ocr_bbox):
                        overlapping_words.append(word)

            if overlapping_words:
                sorted_overlapping_words = sort_words_naturally(overlapping_words)
                field_type = "text"
                if isinstance(field_value, (int, float)) or re.match(r'^[\d,¥￥.]+$', str(field_value)):
                    field_type = "number"
                elif isinstance(field_value, str) and re.search(r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?', field_value):
                    field_type = "date"

                matching_sequence = find_matching_word_sequence(field_value, sorted_overlapping_words, field_type)
                
                if matching_sequence:
                    corrected_bbox = calculate_minimum_bbox(matching_sequence)
                    if corrected_bbox:
                        corrected_data = data.copy()
                        corrected_data["bbox"] = corrected_bbox
                    else:
                        corrected_data = data
                else:
                    corrected_data = data
            else:
                corrected_data = data

            for key, value in data.items():
                if key not in ["value", "bbox"]:
                    corrected_data[key] = correct_bounding_boxes_recursive(value, ocr_words)
            
            return corrected_data

        else:
            corrected_dict = {}
            for key, value in data.items():
                corrected_dict[key] = correct_bounding_boxes_recursive(value, ocr_words)
            return corrected_dict

    elif isinstance(data, list):
        return [correct_bounding_boxes_recursive(item, ocr_words) for item in data]
    else:
        return data

def get_all_words_from_ocr_response(ocr_response: Union[vision.AnnotateImageResponse, List[vision.AnnotateImageResponse]]) -> List[vision.Word]:
    """OCRレスポンスオブジェクトまたはそのリストから全てのWordオブジェクトを抽出する"""
    all_words = []
    if isinstance(ocr_response, list):
        for page_response in ocr_response:
            if page_response.full_text_annotation:
                for page in page_response.full_text_annotation.pages:
                    for block in page.blocks:
                        for paragraph in block.paragraphs:
                            all_words.extend(paragraph.words)
    elif ocr_response and ocr_response.full_text_annotation:
        for page in ocr_response.full_text_annotation.pages:
            for block in page.blocks:
                for paragraph in block.paragraphs:
                    all_words.extend(paragraph.words)
    return all_words

def correct_bounding_boxes(extraction_result: Dict[str, Any], ocr_response: Union[vision.AnnotateImageResponse, List[vision.AnnotateImageResponse]]) -> Dict[str, Any]:
    """
    LLM抽出結果のバウンディングボックスをOCR情報で補正する (メイン関数)
    
    Args:
        extraction_result (dict): LLMからの抽出データ
        ocr_response (Union[vision.AnnotateImageResponse, List[vision.AnnotateImageResponse]]): Vision APIのレスポンス
        
    Returns:
        dict: バウンディングボックスが補正された抽出データ
    """
    logger.info("Starting bounding box correction using OCR data.")

    ocr_words = get_all_words_from_ocr_response(ocr_response)

    if not ocr_words:
        logger.warning("No OCR words found in the response. Skipping bounding box correction.")
        return extraction_result

    logger.info(f"Found {len(ocr_words)} words in OCR data for correction.")

    try:
        corrected_result = correct_bounding_boxes_recursive(extraction_result, ocr_words)
        logger.info("Bounding box correction process completed.")
        return corrected_result
    except Exception as e:
        logger.error(f"Error during bounding box correction: {str(e)}", exc_info=True)
        return extraction_result

def process_extracted_data(extracted_data: Dict[str, Any],
                           ocr_response: Union[vision.AnnotateImageResponse, List[vision.AnnotateImageResponse], None],
                           clipping_request_id: str,
                           s3_key: str) -> Dict[str, Any]:
    """
    LLMから抽出されたデータを後処理し、必要であればbboxを補正する。
    
    Args:
        extracted_data (dict): LLMから抽出されたデータ
        ocr_response (Union[vision.AnnotateImageResponse, List[vision.AnnotateImageResponse], None]): Vision APIのレスポンスオブジェクトまたはそのリスト
        clipping_request_id (str): 処理中のリクエストID
        s3_key (str): 処理中のS3オブジェクトキー
        
    Returns:
        dict: 後処理および補正されたデータを含む辞書
    """
    logger.info(f"Processing extracted data for request {clipping_request_id}, file {s3_key}")

    result = {
        "processed": False,
        "original_data": extracted_data,
        "corrected_data": None,
        "error": None,
        "process_timestamp": datetime.utcnow().isoformat()
    }

    try:
        if not extracted_data or not isinstance(extracted_data, dict) or (extracted_data.get("raw_response") and len(extracted_data.keys()) == 1):
            logger.warning(f"No structured data from LLM for {s3_key}. Skipping further processing.")
            result["error"] = "No structured data from LLM"
            return result

        if ocr_response:
            logger.info(f"Attempting bounding box correction for {s3_key}")
            corrected_data = correct_bounding_boxes(extracted_data, ocr_response)
            result["corrected_data"] = corrected_data
        else:
            logger.info(f"No OCR data provided for {s3_key}, skipping bounding box correction.")
            result["corrected_data"] = extracted_data

        result["processed"] = True
        logger.info(f"Data processing completed successfully for {s3_key}")

    except Exception as e:
        logger.error(f"Error processing extracted data for {s3_key}: {str(e)}", exc_info=True)
        result["processed"] = False
        result["error"] = str(e)

    return result

def parse_date(date_str):
    """
    様々な形式の日付文字列をdatetimeオブジェクトに変換する (現在は未使用)
    
    Args:
        date_str (str): 日付文字列
        
    Returns:
        datetime: 変換されたdatetimeオブジェクト
    """
    formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y.%m.%d",
        "%d-%m-%Y", "%d/%m/%Y", "%m-%d-%Y", "%m/%d/%Y",
    ]
    
    if not date_str: return None

    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except (ValueError, TypeError):
            continue
            
    logger.warning(f"Could not parse date string: {date_str} with known formats.")
    return None