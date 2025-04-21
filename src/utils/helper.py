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
