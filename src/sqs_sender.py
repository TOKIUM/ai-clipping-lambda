import os
import json
import boto3
from src.utils.logger import setup_logger

logger = setup_logger()

# 送信先のSQSキューURLを環境変数から取得
OUTPUT_QUEUE_URL = os.environ.get("OUTPUT_QUEUE_URL")

def send_to_queue(processed_data):
    """
    処理結果をSQSキューに送信する
    
    Args:
        processed_data (dict): 送信するデータ
        
    Returns:
        str: 送信したメッセージのID
    """
    logger.info("Sending processed data to SQS")
    
    try:
        # SQSクライアントの初期化
        sqs_client = boto3.client('sqs')
        
        # 送信データの形式変換（必要に応じて）
        message_body = json.dumps(processed_data)
        
        # SQSにメッセージを送信
        response = sqs_client.send_message(
            QueueUrl=OUTPUT_QUEUE_URL,
            MessageBody=message_body
        )
        
        message_id = response.get('MessageId')
        logger.info(f"Message sent to SQS. MessageId: {message_id}")
        
        return message_id
        
    except Exception as e:
        logger.error(f"Error sending message to SQS: {str(e)}")
        raise