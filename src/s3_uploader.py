import boto3
import os
from botocore.exceptions import ClientError
from src.utils.logger import setup_logger

logger = setup_logger()

def upload_to_s3(data: str, bucket_name: str, object_key: str) -> bool:
    """
    指定されたデータをS3バケットにアップロードします。

    Args:
        data: アップロードするデータ（文字列）。
        bucket_name: アップロード先のS3バケット名。
        object_key: S3オブジェクトキー。

    Returns:
        アップロードが成功した場合はTrue、失敗した場合はFalse。
    """
    s3_client = boto3.client('s3')
    try:
        s3_client.put_object(Bucket=bucket_name, Key=object_key, Body=data.encode('utf-8'))
        logger.info(f"Successfully uploaded data to s3://{bucket_name}/{object_key}")
        return True
    except ClientError as e:
        logger.error(f"Failed to upload data to s3://{bucket_name}/{object_key}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 upload to s3://{bucket_name}/{object_key}: {e}")
        return False

