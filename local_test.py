#!/usr/bin/env python3
"""
ローカル画像ファイルを指定してAI抽出処理をテストするためのスクリプト
Python 3.12の新機能を活用して最適化
"""
import os
import sys
import json
import tempfile
import argparse
import shutil
from datetime import datetime
from pathlib import Path
from typing import TypedDict, NotRequired, Any

# 親ディレクトリをパスに追加して、モジュールをインポートできるようにする
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ローカル開発用の環境変数を設定
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "your-project-id")  # プロジェクトIDを設定
os.environ.setdefault("GOOGLE_CLOUD_REGION", "asia-northeast1")
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "./credential.json")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.0-flash")

from src.ocr import extract_text
from src.llm import extract_information
from src.processor import process_extracted_data

# Python 3.12の型ヒントの強化を活用
class ExtractedInfo(TypedDict):
    raw_response: NotRequired[str]

class ProcessingResult(TypedDict):
    processed: bool
    normalized: NotRequired[dict[str, Any]]
    data: NotRequired[ExtractedInfo]
    error: NotRequired[str]
    process_timestamp: str
    original_data: NotRequired[ExtractedInfo]

def parse_arguments():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(description='ローカル画像ファイルからテキスト抽出とLLM処理をテストします')
    parser.add_argument('file_path', help='処理する画像またはPDFファイルのパス')
    parser.add_argument('--output', '-o', help='結果を保存するJSONファイルのパス（指定しない場合は標準出力）')
    parser.add_argument('--verbose', '-v', action='store_true', help='詳細なログを出力する')
    parser.add_argument('--project', '-p', help='Google Cloudプロジェクトのプロジェクトid（指定しない場合は環境変数かデフォルト値を使用）')
    parser.add_argument('--credentials', '-c', default='./credential.json', help='Google Cloud認証情報ファイルのパス（指定しない場合はデフォルト値を使用）')
    return parser.parse_args()

def print_section(title):
    """セクションタイトルを表示する"""
    print(f"\n{'='*80}")
    print(f"= {title}")
    print(f"{'='*80}\n")

def main():
    """メイン処理"""
    args = parse_arguments()
    
    # Google Cloud設定をコマンドライン引数から更新
    if args.project:
        os.environ["GOOGLE_CLOUD_PROJECT"] = args.project
    if args.credentials:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = args.credentials
        
        # 認証情報ファイルの存在確認
        if not Path(args.credentials).exists():
            print(f"警告: 指定した認証情報ファイル '{args.credentials}' が見つかりません")
    
    # ファイルの存在確認
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"エラー: ファイル '{file_path}' が見つかりません")
        sys.exit(1)
    
    # Vertex AI用の認証情報の設定を表示
    print(f"Google Cloud設定:")
    print(f"- プロジェクト: {os.environ.get('GOOGLE_CLOUD_PROJECT')}")
    print(f"- リージョン: {os.environ.get('GOOGLE_CLOUD_REGION')}")
    print(f"- 認証情報: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
    print(f"- Geminiモデル: {os.environ.get('GEMINI_MODEL')}")
    
    print(f"\n処理開始: {file_path}")
    start_time = datetime.now()
    
    try:
        # 1. OCR処理：画像からテキストを抽出
        print_section("OCR処理")
        print("テキスト抽出中...")
        extracted_text = extract_text(str(file_path))
        
        # Python 3.12: マッチステートメントを使用して表示方法を決定
        match args.verbose, len(extracted_text):
            case (True, _):
                print(f"\n抽出されたテキスト:\n{extracted_text}\n")
            case (False, length) if length > 500:
                preview = extracted_text[:500] + "..."
                print(f"\n抽出されたテキスト (プレビュー):\n{preview}\n")
            case _:
                print(f"\n抽出されたテキスト:\n{extracted_text}\n")
        
        # 2. LLM処理：テキストから情報を抽出
        print_section("LLM処理")
        print("情報抽出中...")
        extracted_info = extract_information(extracted_text)
        
        print("\n抽出された情報:")
        print(json.dumps(extracted_info, indent=2, ensure_ascii=False))
        
        # 3. データの後処理
        print_section("データ後処理")
        print("データ正規化中...")
        processed_data = process_extracted_data(extracted_info)
        
        print("\n処理結果:")
        # Python 3.12: JSON関連のエラーハンドリング改善
        try:
            result_json = json.dumps(processed_data, indent=2, ensure_ascii=False)
            print(result_json)
            
            # 結果を保存
            if args.output:
                output_path = Path(args.output)
                # 親ディレクトリが存在しない場合は作成（Python 3.12: Path.exists_ok=True相当）
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(result_json, encoding='utf-8')
                print(f"\n結果を {args.output} に保存しました")
        
        except TypeError as e:
            e.add_note("JSON変換できないオブジェクトが含まれています")
            print(f"エラー: 結果をJSONに変換できません - {str(e)}")
            print(f"処理結果 (文字列表現):\n{str(processed_data)}")
        
        elapsed_time = datetime.now() - start_time
        print(f"\n処理完了: 処理時間 {elapsed_time.total_seconds():.2f} 秒")
        
    except Exception as e:
        # Python 3.12: 例外注釈を使用して詳細情報を追加
        e.add_note(f"ファイル処理中のエラー: {file_path}")
        print(f"エラーが発生しました: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()