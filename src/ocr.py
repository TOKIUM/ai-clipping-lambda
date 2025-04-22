import os
from google.cloud import vision
import io
import fitz  # PyMuPDF
from src.utils.logger import setup_logger

logger = setup_logger()

def extract_text(file_path):
    """
    Google Cloud Visionを使用して画像またはPDFからOCR結果を取得する

    Args:
        file_path (str): 処理するファイルのパス

    Returns:
        google.cloud.vision.AnnotateImageResponse | list[google.cloud.vision.AnnotateImageResponse]:
            画像の場合はVision APIのレスポンスオブジェクト。
            PDFの場合はページごとのレスポンスオブジェクトのリスト。
            テキストが検出されなかった場合はNoneまたは空のリスト。
    """
    logger.info(f"Extracting text data from file: {file_path}")

    file_extension = os.path.splitext(file_path)[1].lower()

    if file_extension == '.pdf':
        return extract_ocr_data_from_pdf(file_path)
    else:
        return extract_ocr_data_from_image(file_path)

def extract_ocr_data_from_image(image_path):
    """
    Google Cloud Visionを使用して画像からOCR結果を取得する

    Args:
        image_path (str): 処理する画像のパス

    Returns:
        google.cloud.vision.AnnotateImageResponse | None:
            Vision APIのレスポンスオブジェクト。テキストが検出されなかった場合はNone。
    """
    try:
        client = vision.ImageAnnotatorClient()

        with io.open(image_path, 'rb') as image_file:
            content = image_file.read()

        image = vision.Image(content=content)

        logger.info(f"Requesting document text detection for image: {image_path}")
        response = client.document_text_detection(image=image)

        if response.error.message:
             logger.error(f"Vision API error for {image_path}: {response.error.message}")
             raise Exception(
                '{}\nFor more info on error messages, check: '
                'https://cloud.google.com/apis/design/errors'.format(
                    response.error.message))

        if response.full_text_annotation:
            logger.info(f"Successfully extracted OCR data from image: {image_path}")
            return response
        else:
            logger.warning(f"No text found in the image: {image_path}")
            return None

    except Exception as e:
        logger.error(f"Error extracting OCR data from image {image_path}: {str(e)}")
        raise

def extract_ocr_data_from_pdf(pdf_path, max_pages=1):
    """
    PDFファイルからページごとにOCR結果を取得する
    - PDFをページごとに画像に変換
    - 各ページに対してOCR処理を実行

    Args:
        pdf_path (str): 処理するPDFのパス
        max_pages (int): 処理する最大ページ数。デフォルトは1。

    Returns:
        list[google.cloud.vision.AnnotateImageResponse]:
            ページごとのVision APIレスポンスオブジェクトのリスト。
            エラーが発生したページやテキストがないページは含まれない可能性がある。
    """
    try:
        client = vision.ImageAnnotatorClient()
        responses = []

        pdf_document = fitz.open(pdf_path)
        num_pages_to_process = min(len(pdf_document), max_pages)

        logger.info(f"Processing {num_pages_to_process} page(s) out of {len(pdf_document)} for PDF: {pdf_path}")

        for page_num in range(num_pages_to_process):
            logger.info(f"Processing PDF page {page_num+1}/{num_pages_to_process}")

            page = pdf_document.load_page(page_num)
            pix = page.get_pixmap(alpha=False)

            img_bytes = pix.tobytes("png")

            image = vision.Image(content=img_bytes)
            logger.info(f"Requesting document text detection for PDF page {page_num+1}")
            response = client.document_text_detection(image=image)

            if response.error.message:
                logger.error(f"Vision API error for PDF {pdf_path} page {page_num+1}: {response.error.message}")
                continue

            if response.full_text_annotation:
                logger.info(f"Extracted OCR data from page {page_num+1}")
                responses.append(response)
            else:
                logger.warning(f"No text found on page {page_num+1}")

        logger.info(f"Completed PDF OCR data extraction. Processed {len(responses)} pages successfully.")
        return responses

    except Exception as e:
        logger.error(f"Error extracting OCR data from PDF {pdf_path}: {str(e)}")
        raise