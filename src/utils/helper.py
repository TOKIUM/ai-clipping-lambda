import os
import json
from pathlib import Path

def get_prompt_template(prompt_type='user'):
    """
    LLMに送信するプロンプトテンプレートを取得する
    
    Args:
        prompt_type (str): プロンプトの種類 ('system' または 'user')
        
    Returns:
        str: プロンプトテンプレート
    """
    # プロンプトファイルのデフォルトパス
    base_path = Path(__file__).parent.parent / "prompts"
    default_paths = {
        'system': base_path / "system_prompt.txt",
        'user': base_path / "user_prompt.txt"
    }
    
    # 環境変数からプロンプトパスを取得、または標準の場所を使用
    env_paths = {
        'system': os.environ.get('SYSTEM_PROMPT_PATH'),
        'user': os.environ.get('USER_PROMPT_PATH')
    }
    
    # 指定されたタイプのプロンプトパスを取得
    prompt_path = env_paths.get(prompt_type) or default_paths.get(prompt_type)
    
    if prompt_path and os.path.exists(prompt_path):
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    # デフォルトのプロンプトを返す
    if prompt_type == 'system':
        return """あなたは文書から情報を抽出する専門家です。必要な情報を正確にJSON形式で返してください。"""
    else:  # user prompt
        return """
以下のテキストから必要な情報を抽出してください。JSONフォーマットで返してください。

テキスト:
{text}
"""

def _convert_vertices_to_simple_box(vertices):
    """Verticesリストを {x, y, width, height} 形式に変換する内部ヘルパー"""
    if not vertices or len(vertices) != 4:
        return None
    try:
        # 左上の座標
        x = vertices[0].x
        y = vertices[0].y
        # 幅と高さ (右上のx - 左上のx, 左下のy - 左上のy)
        width = vertices[1].x - vertices[0].x
        height = vertices[3].y - vertices[0].y
        # Ensure non-negative dimensions
        width = max(0, width)
        height = max(0, height)
        return {'x': x, 'y': y, 'width': width, 'height': height}
    except (AttributeError, IndexError, TypeError) as e:
        print(f"Error converting vertices: {e}. Vertices: {vertices}")
        return None

def _process_element_to_dict(element):
    """OCR要素を辞書に変換し、必要な属性とシンプル形式のBBのみ含める"""
    element_dict = {}
    # description または text 属性があればコピー
    if hasattr(element, 'description'):
        element_dict['description'] = element.description
    if hasattr(element, 'text'): # 主に fullTextAnnotation 内の symbol で使用
        element_dict['text'] = element.text

    # locale や confidence など、後続処理で必要そうな属性をコピー
    if hasattr(element, 'locale'):
         element_dict['locale'] = element.locale
    if hasattr(element, 'confidence'):
         element_dict['confidence'] = element.confidence

    # バウンディングボックスを処理し、シンプル形式のみ追加
    bounding_poly = getattr(element, 'bounding_poly', None)
    bounding_box = getattr(element, 'boundingBox', None)
    vertices = None
    if bounding_poly and hasattr(bounding_poly, 'vertices'):
        vertices = bounding_poly.vertices
    elif bounding_box and hasattr(bounding_box, 'vertices'):
        vertices = bounding_box.vertices

    if vertices:
        simple_box = _convert_vertices_to_simple_box(vertices)
        if simple_box:
            # 'simple_bounding_box' というキーで新しい辞書に追加
            element_dict['simple_bounding_box'] = simple_box

    # 再帰的に子要素を処理 (word, symbolなど)
    if hasattr(element, 'words'):
         element_dict['words'] = [_process_element_to_dict(word) for word in element.words]
    if hasattr(element, 'symbols'):
         element_dict['symbols'] = [_process_element_to_dict(symbol) for symbol in element.symbols]

    return element_dict

def convert_single_response_bounding_box(response):
    """単一のOCRレスポンスオブジェクトを、シンプルBBを持つ軽量な辞書に変換する"""
    if not response:
        return None

    result_dict = {}

    # 1. textAnnotations を処理 -> description と simple_bounding_box のみ持つ辞書のリスト
    if hasattr(response, 'text_annotations') and response.text_annotations:
        result_dict['textAnnotations'] = [
            _process_element_to_dict(annotation)
            for annotation in response.text_annotations
        ]

    # 2. fullTextAnnotation を処理 -> 必要な属性とシンプルBBを持つ階層的な辞書
    if hasattr(response, 'full_text_annotation') and response.full_text_annotation:
        full_text_dict = {}
        if hasattr(response.full_text_annotation, 'text'):
             full_text_dict['text'] = response.full_text_annotation.text

        if hasattr(response.full_text_annotation, 'pages'):
            full_text_dict['pages'] = []
            for page in response.full_text_annotation.pages:
                page_dict = {}
                # page のプロパティ (width, height など) をコピー
                if hasattr(page, 'width'): page_dict['width'] = page.width
                if hasattr(page, 'height'): page_dict['height'] = page.height

                if hasattr(page, 'blocks'):
                    page_dict['blocks'] = []
                    for block in page.blocks:
                        block_dict = {} # block 自体の辞書
                        # block の boundingBox を処理
                        if hasattr(block, 'boundingBox') and block.boundingBox and hasattr(block.boundingBox, 'vertices'):
                            simple_box = _convert_vertices_to_simple_box(block.boundingBox.vertices)
                            if simple_box:
                                block_dict['simple_bounding_box'] = simple_box
                        # block の confidence など必要ならコピー
                        if hasattr(block, 'confidence'): block_dict['confidence'] = block.confidence

                        if hasattr(block, 'paragraphs'):
                            block_dict['paragraphs'] = []
                            for paragraph in block.paragraphs:
                                para_dict = {} # paragraph 自体の辞書
                                # paragraph の boundingBox を処理
                                if hasattr(paragraph, 'boundingBox') and paragraph.boundingBox and hasattr(paragraph.boundingBox, 'vertices'):
                                    simple_box = _convert_vertices_to_simple_box(paragraph.boundingBox.vertices)
                                    if simple_box:
                                        para_dict['simple_bounding_box'] = simple_box
                                # paragraph の confidence など必要ならコピー
                                if hasattr(paragraph, 'confidence'): para_dict['confidence'] = paragraph.confidence

                                if hasattr(paragraph, 'words'):
                                    # words は _process_element_to_dict で再帰的に処理
                                    para_dict['words'] = [_process_element_to_dict(word) for word in paragraph.words]
                                block_dict['paragraphs'].append(para_dict)
                        page_dict['blocks'].append(block_dict)
                full_text_dict['pages'].append(page_dict)
        result_dict['fullTextAnnotation'] = full_text_dict

    return result_dict

def convert_bounding_box_format(ocr_data):
    """
    OCRレスポンス(またはリスト)を、シンプルBBを持つ軽量な辞書(またはリスト)に変換する。

    Args:
        ocr_data: Google Cloud VisionのOCRレスポンスオブジェクト、またはそのリスト。

    Returns:
        変換された辞書形式のOCRデータ、またはそのリスト。
    """
    if isinstance(ocr_data, list): # PDFの場合 (レスポンスのリスト)
        return [convert_single_response_bounding_box(response) for response in ocr_data]
    else: # 画像の場合 (単一レスポンス)
        return convert_single_response_bounding_box(ocr_data)

def clean_temp_files(file_paths):
    """
    一時ファイルをクリーンアップする
    
    Args:
        file_paths (list): 削除するファイルパスのリスト
    """
    for file_path in file_paths:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Error removing temp file {file_path}: {str(e)}")
