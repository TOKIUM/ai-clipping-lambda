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
from typing import TypedDict, NotRequired, Any, Dict, List, Optional

# 親ディレクトリをパスに追加して、モジュールをインポートできるようにする
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ローカル開発用の環境変数を設定
os.environ.setdefault("GOOGLE_CLOUD_REGION", "asia-northeast1")
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "./credential.json")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.0-flash")

from src.ocr import extract_text
from src.llm import extract_information
from src.processor import process_extracted_data
from src.formatter import format_sqs_message

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
    corrected_data: NotRequired[Dict[str, Any]]

class FormattedMessage(TypedDict):
    clipping_request_id: str
    s3_key: str
    status: str
    clips: List[Dict[str, Any]]
    error_message: Optional[str]
    processed_timestamp: str

def parse_arguments():
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(description='ローカル画像ファイルからテキスト抽出とLLM処理をテストします')
    parser.add_argument('file_path', help='処理する画像またはPDFファイルのパス')
    parser.add_argument('--output', '-o', help='結果を保存するJSONファイルのパス（指定しない場合は標準出力）')
    parser.add_argument('--verbose', '-v', action='store_true', help='詳細なログを出力する')
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
    print(f"- リージョン: {os.environ.get('GOOGLE_CLOUD_REGION')}")
    print(f"- 認証情報: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
    print(f"- Geminiモデル: {os.environ.get('GEMINI_MODEL')}")
    
    print(f"\n処理開始: {file_path}")
    start_time = datetime.now()

    # Dummy values for testing formatter
    dummy_request_id = "local-test-req-123"
    dummy_s3_key = f"local/{file_path.name}"
    
    try:
        # 1. OCR処理：画像からテキストを抽出 (レスポンスオブジェクトを取得)
        print_section("OCR処理")
        print("テキスト抽出中...")
        ocr_response = extract_text(str(file_path))

        llm_input_text = ""
        if isinstance(ocr_response, list): # PDF
            llm_input_text = "\n\n".join([resp.full_text_annotation.text for resp in ocr_response if resp.full_text_annotation])
        elif hasattr(ocr_response, 'full_text_annotation') and ocr_response.full_text_annotation: # Image
            llm_input_text = ocr_response.full_text_annotation.text
        else:
            print("警告: OCRレスポンスからテキストを抽出できませんでした。")

        match args.verbose, len(llm_input_text):
            case (True, _):
                print(f"\n抽出されたテキスト:\n{llm_input_text}\n")
            case (False, length) if length > 500:
                preview = llm_input_text[:500] + "..."
                print(f"\n抽出されたテキスト (プレビュー):\n{preview}\n")
            case _:
                print(f"\n抽出されたテキスト:\n{llm_input_text}\n")

        # 2. LLM処理：テキストから情報を抽出
        print_section("LLM処理")
        print("情報抽出中...")
        extracted_info = extract_information(llm_input_text)
        print("\nLLMによる抽出情報:")
        print(json.dumps(extracted_info, indent=2, ensure_ascii=False))

        # 3. データの後処理 (bbox補正など)
        print_section("データ後処理 (Processor)")
        print("データ補正中...")
        processed_data: ProcessingResult = process_extracted_data(
            extracted_info,
            ocr_response, # Pass the full OCR response
            dummy_request_id, # Pass dummy request ID
            dummy_s3_key      # Pass dummy S3 key
        )
        print("\nProcessor処理結果:")
        print(json.dumps(processed_data, indent=2, ensure_ascii=False))

        # 4. SQSメッセージ形式へのフォーマット
        print_section("最終フォーマット (Formatter)")
        print("SQSメッセージ形式へ変換中...")
        formatted_message: FormattedMessage = format_sqs_message(
            processed_data,
            dummy_request_id,
            dummy_s3_key
        )
        print("\nFormatter処理結果 (最終SQSメッセージ形式):")
        try:
            result_json = json.dumps(formatted_message, indent=2, ensure_ascii=False)
            print(result_json)

            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(result_json, encoding='utf-8')
                print(f"\n最終結果を {args.output} に保存しました")

        except TypeError as e:
            print(f"エラー: 最終結果をJSONにシリアライズできませんでした: {e}")
            print(f"最終結果 (文字列表現):\n{str(formatted_message)}")

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