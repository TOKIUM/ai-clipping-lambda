import os
import boto3
import tempfile
from src.utils.logger import setup_logger

logger = setup_logger()

def download_file(bucket_name, object_key):
    """
    S3バケットから画像またはPDFファイルをダウンロードする
    
    Args:
        bucket_name (str): S3バケット名
        object_key (str): S3オブジェクトキー
        
    Returns:
        str: ダウンロードしたファイルのローカルパス
    """
    logger.info(f"Downloading file: {object_key} from bucket: {bucket_name}")
    
    # S3クライアントの初期化
    s3_client = boto3.client('s3')
    
    # ファイル拡張子を取得
    _, file_extension = os.path.splitext(object_key)
    
    # 一時ファイルの作成
    with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
        local_file_path = temp_file.name
    
    try:
        # S3からファイルをダウンロード
        s3_client.download_file(bucket_name, object_key, local_file_path)
        logger.info(f"File downloaded successfully to {local_file_path}")
        
        return local_file_path
    
    except Exception as e:
        logger.error(f"Error downloading file from S3: {str(e)}")
        # 一時ファイルの削除
        if os.path.exists(local_file_path):
            os.remove(local_file_path)
        raise