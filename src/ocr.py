import os
from google.cloud import vision
from google.cloud import storage
import io
import fitz  # PyMuPDF
from src.utils.logger import setup_logger

logger = setup_logger()

def extract_text(file_path):
    """
    Google Cloud Visionを使用して画像またはPDFから文字を抽出する
    
    Args:
        file_path (str): 処理するファイルのパス
        
    Returns:
        str: 抽出されたテキスト
    """
    logger.info(f"Extracting text from file: {file_path}")
    
    file_extension = os.path.splitext(file_path)[1].lower()
    
    # PDFファイルの場合は、ページごとに画像として処理
    if file_extension == '.pdf':
        return extract_text_from_pdf(file_path)
    else:
        # 画像ファイルの場合は直接OCR処理
        return extract_text_from_image(file_path)

def extract_text_from_image(image_path):
    """
    Google Cloud Visionを使用して画像から文字を抽出する
    
    Args:
        image_path (str): 処理する画像のパス
        
    Returns:
        str: 抽出されたテキスト
    """
    try:
        # Vision APIクライアントの初期化
        client = vision.ImageAnnotatorClient()
        
        # 画像ファイルを開く
        with io.open(image_path, 'rb') as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        
        # OCR処理を実行
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if texts:
            # 最初の要素が全テキスト
            full_text = texts[0].description
            logger.info(f"Successfully extracted {len(full_text)} characters from image")
            return full_text
        else:
            logger.warning("No text found in the image")
            return ""
            
    except Exception as e:
        logger.error(f"Error extracting text from image: {str(e)}")
        raise

def extract_text_from_pdf(pdf_path, max_pages=1):
    """
    PDFファイルからテキストを抽出する
    - PDFをページごとに分割
    - 各ページに対してOCR処理を実行
    
    Args:
        pdf_path (str): 処理するPDFのパス
        max_pages (int): 処理する最大ページ数。デフォルトは1。
        
    Returns:
        str: 抽出されたテキスト
    """
    try:
        client = vision.ImageAnnotatorClient()
        full_text = ""
        
        # PDFドキュメントを開く
        pdf_document = fitz.open(pdf_path)
        num_pages_to_process = min(len(pdf_document), max_pages)
        
        logger.info(f"Processing {num_pages_to_process} page(s) out of {len(pdf_document)} for PDF: {pdf_path}")
        
        for page_num in range(num_pages_to_process):
            logger.info(f"Processing PDF page {page_num+1}/{num_pages_to_process}")
            
            # ページを取得して画像に変換
            page = pdf_document.load_page(page_num)
            pix = page.get_pixmap(alpha=False)
            
            # 画像データをメモリ上に保持
            img_bytes = pix.tobytes("png")
            
            # Vision APIで処理
            image = vision.Image(content=img_bytes)
            response = client.text_detection(image=image)
            
            if response.text_annotations:
                page_text = response.text_annotations[0].description
                full_text += page_text + "\n\n"
                logger.info(f"Extracted {len(page_text)} characters from page {page_num+1}")
            else:
                logger.warning(f"No text found on page {page_num+1}")
        
        logger.info(f"Completed PDF text extraction. Total characters: {len(full_text)}")
        return full_text
            
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise