import logging
import os
import json

def setup_logger(name='ai-clipping-lambda'):
    """
    ロギング設定を行い、設定済みのロガーを返す
    
    Args:
        name (str): ロガーの名前
        
    Returns:
        logging.Logger: 設定済みのロガーオブジェクト
    """
    # すでに設定済みのロガーがあれば、それを返す
    if name in logging.Logger.manager.loggerDict:
        return logging.getLogger(name)
    
    # 新しいロガーの作成
    logger = logging.getLogger(name)
    
    # ログレベルの設定（環境変数から取得、デフォルトはINFO）
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Lambda環境ではハンドラを追加する必要がない場合がある
    if not logger.handlers:
        # コンソールハンドラの作成
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        
        # フォーマッタの作成
        if os.environ.get('ENVIRONMENT') == 'production':
            # JSON形式のフォーマットを使用（CloudWatchでの検索を容易にするため）
            class JsonFormatter(logging.Formatter):
                def format(self, record):
                    log_record = {
                        'timestamp': self.formatTime(record),
                        'level': record.levelname,
                        'message': record.getMessage(),
                        'name': record.name,
                    }
                    
                    # 例外情報がある場合は追加
                    if record.exc_info:
                        log_record['exception'] = self.formatException(record.exc_info)
                    
                    return json.dumps(log_record)
                    
            formatter = JsonFormatter()
        else:
            # 開発環境用のわかりやすいフォーマット
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger