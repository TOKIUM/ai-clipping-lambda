#!/usr/bin/env python3
"""
ローカルテスト機能を使ってPDFファイルからデータ抽出し、CSVファイルの値と比較するツール

使用方法:
python lambda_csv_comparison.py --limit 10
"""

import pandas as pd
import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime
from difflib import SequenceMatcher
from concurrent.futures import ProcessPoolExecutor, as_completed
import threading
import time

# プロジェクトのrootディレクトリをパスに追加
sys.path.append(str(Path(__file__).parent.parent))

# ローカル開発用の環境変数を設定
os.environ.setdefault("GOOGLE_CLOUD_REGION", "us-central1")
os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", "./credential.json")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.0-flash")

from src.ocr import extract_text
from src.llm import extract_information
from src.processor import process_extracted_data
from src.formatter import format_sqs_message
from src.utils.helper import convert_bounding_box_format

def read_csv_data(csv_path: str) -> pd.DataFrame:
    """CSVファイルを読み込む"""
    return pd.read_csv(csv_path)

def process_pdf_file(pdf_path: str) -> Dict[str, Any]:
    """指定されたPDFファイルに対してローカル処理を実行"""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")
    
    try:
        # OCR処理
        ocr_response = extract_text(str(pdf_path))
        if not ocr_response:
            raise Exception("OCR処理でテキストが抽出されませんでした")
        
        # Bounding Box形式の変換
        converted_ocr_data = convert_bounding_box_format(ocr_response)
        if not converted_ocr_data:
            raise Exception("Bounding Box形式の変換に失敗しました")
        
        # LLM処理
        file_identifier = os.path.splitext(os.path.basename(pdf_path))[0]  # ファイル名から拡張子を除去
        extracted_info = extract_information(converted_ocr_data, file_identifier)
        
        # トークン使用量を分離
        usage_metadata = extracted_info.pop('usage_metadata', None)
        
        # データの後処理
        processed_data = process_extracted_data(
            extracted_info,
            ocr_response,
            clipping_request_id=f"test-{os.path.basename(pdf_path)}",
            s3_key=f"test/{os.path.basename(pdf_path)}"
        )
        
        # SQSメッセージ形式へのフォーマット
        formatted_message = format_sqs_message(
            processed_data,
            f"test-{os.path.basename(pdf_path)}",
            f"test/{os.path.basename(pdf_path)}"
        )
        
        # レスポンス形式を統一
        result = {
            'statusCode': 200,
            'body': json.dumps({
                'extracted_data': extracted_info,
                'processed_data': processed_data,
                'formatted_message': formatted_message,
                'usage': usage_metadata or {}
            }, ensure_ascii=False)
        }
        
        return result
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def clean_value(value):
    """値をクリーンアップ（NaN、空文字列などをNoneに変換）"""
    if pd.isna(value) or value == '' or value == 'nan':
        return None
    if isinstance(value, str):
        return value.strip()
    return value

def normalize_phone_number(phone: str) -> str:
    """電話番号を正規化（数字のみに変換し、先頭0を削除して10桁または9桁に統一）"""
    if not isinstance(phone, str):
        phone_str = str(phone) if phone is not None else ""
    else:
        phone_str = phone
    
    # 数字以外を除去
    import re
    normalized = re.sub(r'[^\d]', '', phone_str)
    
    # CSVで.0付きの場合は末尾の0を削除
    if '.' in phone_str and normalized.endswith('0'):
        normalized = normalized[:-1]
    
    # 11桁で先頭が0の場合は先頭の0を削除（例：0474512831 → 474512831）
    if len(normalized) == 11 and normalized.startswith('0'):
        normalized = normalized[1:]
    # 10桁で先頭が0の場合も先頭の0を削除（例：0962938881 → 962938881）
    elif len(normalized) == 10 and normalized.startswith('0'):
        normalized = normalized[1:]
    
    return normalized

def normalize_string_for_comparison(text: str) -> str:
    """比較用に文字列を正規化（スペース、特殊文字、半角全角の統一）"""
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    
    # 全角英数字を半角に変換、全角カタカナをひらがなに変換
    import unicodedata
    
    normalized = text
    # 全角英数字を半角に変換
    normalized = unicodedata.normalize('NFKC', normalized)
    # スペースを除去
    normalized = normalized.replace(' ', '').replace('　', '')
    # ハイフンを統一
    normalized = normalized.replace('ー', '-').replace('―', '-').replace('−', '-')
    # 括弧を統一
    normalized = normalized.replace('（', '(').replace('）', ')')
    
    return normalized.lower()

def fuzzy_match_strings(str1: str, str2: str, threshold: float = 0.8) -> bool:
    """ファジーマッチングで文字列の類似度を計算"""
    if str1 is None or str2 is None:
        return str1 == str2
    
    # 正規化
    norm_str1 = normalize_string_for_comparison(str1)
    norm_str2 = normalize_string_for_comparison(str2)
    
    # 完全一致チェック
    if norm_str1 == norm_str2:
        return True
    
    # 部分一致チェック（短い方が長い方に含まれる）
    if len(norm_str1) > 0 and len(norm_str2) > 0:
        if norm_str1 in norm_str2 or norm_str2 in norm_str1:
            return True
    
    # 類似度チェック
    similarity = SequenceMatcher(None, norm_str1, norm_str2).ratio()
    return similarity >= threshold

def extract_value_from_prediction(prediction) -> Any:
    """予測値から実際の値を抽出する（辞書形式の場合は'value'キーを使用）"""
    if prediction is None or prediction == "":
        return None
    
    if isinstance(prediction, str):
        try:
            # JSON文字列の場合はパース
            parsed = json.loads(prediction.replace("'", '"'))
            if isinstance(parsed, dict) and 'value' in parsed:
                return parsed['value']
            return parsed
        except (json.JSONDecodeError, ValueError):
            return prediction
    elif isinstance(prediction, dict) and 'value' in prediction:
        return prediction['value']
    
    return prediction

def get_nested_value(data: Dict[str, Any], key_path: str) -> Any:
    """ネストされたオブジェクトから値を取得する（例: 'amount_info.total_amount'）"""
    keys = key_path.split('.')
    value = data
    try:
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return None
        return value
    except (KeyError, TypeError):
        return None

def get_tax_breakdown_value(data: Dict[str, Any], tax_rate: float, field_name: str) -> Any:
    """tax_breakdown配列から指定した税率の特定フィールドの値を取得する"""
    try:
        amount_info = data.get('amount_info', {})
        tax_breakdown = amount_info.get('tax_breakdown', [])
        
        for item in tax_breakdown:
            if isinstance(item, dict):
                tax_rate_obj = item.get('tax_rate', {})
                if isinstance(tax_rate_obj, dict) and 'value' in tax_rate_obj:
                    item_tax_rate = tax_rate_obj['value']
                    # 税率が一致する場合（小数点誤差を考慮）
                    if abs(item_tax_rate - tax_rate) < 1e-9:
                        target_field = item.get(field_name, {})
                        if isinstance(target_field, dict) and 'value' in target_field:
                            return target_field
                        return target_field
        return None
    except (KeyError, TypeError, AttributeError):
        return None

def compare_values(result_body: Dict[str, Any], csv_row: pd.Series) -> Tuple[Dict[str, bool], Dict[str, Any]]:
    """処理結果とCSV行の値を比較し、比較結果と予測値を返す"""
    
    # extracted_dataから値を取得
    extracted_data = result_body.get('extracted_data', {})
    
    # フィールドマッピング（CSVヘッダー -> 抽出データのフィールド名）
    # 注意: 税率別の金額項目（10%税込金額等）は専用ロジックで処理されるため、ここでは定義不要
    field_mapping = {
        'チップ入力結果': 'chip_input_result',
        '電話番号': 'phone_number',
        '発行者': 'issuer_name',
        '登録番号': 'registrated_number',
        '繰越額＋当月額': 'amount_info.total_amount',
        '支払期限': 'due_date',
        '銀行名': 'bank_details.bank_name',
        '支店名': 'bank_details.branch_name',
        '口座種別': 'bank_details.account_type',
        '口座番号': 'bank_details.account_number',
        '口座名義人': 'bank_details.account_holder',
        '振込手数料負担': 'bank_transfer_fee_payer'
    }
    
    # 文字列フィールドの定義（ファジーマッチングを適用）
    string_fields = {
        'チップ入力結果', '電話番号', '発行者', '登録番号', '支払期限',
        '銀行名', '支店名', '口座種別', '口座番号', '口座名義人', '振込手数料負担'
    }
    
    # 処理対象のCSVフィールドを定義（field_mappingにないものも含める）
    all_csv_fields = list(field_mapping.keys()) + [
        '10%税込金額', '10%税抜金額', '10%消費税',
        '8%税込金額', '8%税抜金額', '8%消費税',
        '0%対象金額', '源泉徴収税額'
    ]
    
    comparison_results = {}
    predicted_values = {}
    
    for csv_field in all_csv_fields:
        # field_mappingから取得、なければNone
        extract_field = field_mapping.get(csv_field)
        # CSV値の取得とクリーンアップ
        csv_value = clean_value(csv_row.get(csv_field))
        
        # 抽出データからの値取得（ネストされたキーに対応）
        raw_extract_value = None
        
        # 税率別の金額項目は専用ロジックで処理
        if csv_field in ['10%税込金額', '10%税抜金額', '10%消費税']:
            if csv_field == '10%税込金額':
                raw_extract_value = get_tax_breakdown_value(extracted_data, 0.1, 'amount_include_tax')
            elif csv_field == '10%税抜金額':
                raw_extract_value = get_tax_breakdown_value(extracted_data, 0.1, 'amount_exclude_tax')
            elif csv_field == '10%消費税':
                raw_extract_value = get_tax_breakdown_value(extracted_data, 0.1, 'amount_consumption_tax')
        elif csv_field in ['8%税込金額', '8%税抜金額', '8%消費税']:
            if csv_field == '8%税込金額':
                raw_extract_value = get_tax_breakdown_value(extracted_data, 0.08, 'amount_include_tax')
            elif csv_field == '8%税抜金額':
                raw_extract_value = get_tax_breakdown_value(extracted_data, 0.08, 'amount_exclude_tax')
            elif csv_field == '8%消費税':
                raw_extract_value = get_tax_breakdown_value(extracted_data, 0.08, 'amount_consumption_tax')
        elif csv_field == '0%対象金額':
            # 0%は税無しの金額なので、tax_free_amountから取得
            raw_extract_value = get_nested_value(extracted_data, 'amount_info.tax_free_amount')
        elif csv_field == '源泉徴収税額':
            # 源泉徴収税額はamount_withholdingから取得
            raw_extract_value = get_nested_value(extracted_data, 'amount_info.amount_withholding')
        else:
            # 通常のネストされたキーの処理
            if extract_field:
                raw_extract_value = get_nested_value(extracted_data, extract_field)
            else:
                raw_extract_value = None
        
        # 予測値から実際の値を抽出
        extract_value = extract_value_from_prediction(raw_extract_value)
        extract_value = clean_value(extract_value)
        
        # 0や0.0の値はLambdaから返されない想定なのでNoneとして扱う
        if extract_value == 0 or extract_value == 0.0 or extract_value == "0" or extract_value == "0.0":
            extract_value = None
        
        # 予測値を記録（_pred列用）- valueのみを保存
        pred_value_for_csv = None
        if raw_extract_value is not None and isinstance(raw_extract_value, dict) and 'value' in raw_extract_value:
            pred_value_for_csv = raw_extract_value['value']
        elif raw_extract_value is not None:
            pred_value_for_csv = raw_extract_value
        
        # 0や0.0の値はLambdaから返されない想定なので空文字として記録
        if pred_value_for_csv == 0 or pred_value_for_csv == 0.0 or pred_value_for_csv == "0" or pred_value_for_csv == "0.0":
            predicted_values[f"{csv_field}_pred"] = ""
        else:
            predicted_values[f"{csv_field}_pred"] = pred_value_for_csv if pred_value_for_csv is not None else ""
        
        # 比較
        # 両方がNoneの場合はTrue
        if csv_value is None and extract_value is None:
            comparison_results[csv_field] = True
        elif csv_value is None or extract_value is None:
            comparison_results[csv_field] = False
        else:
            # 電話番号は専用の正規化ロジックを使用
            if csv_field == '電話番号':
                csv_phone = normalize_phone_number(str(csv_value))
                extract_phone = normalize_phone_number(str(extract_value))
                comparison_results[csv_field] = csv_phone == extract_phone
            # 文字列フィールドはファジーマッチング、数値は通常の比較
            elif csv_field in string_fields:
                comparison_results[csv_field] = fuzzy_match_strings(str(csv_value), str(extract_value))
            else:
                # 数値の場合は数値として比較
                try:
                    csv_num = float(csv_value)
                    extract_num = float(extract_value)
                    comparison_results[csv_field] = abs(csv_num - extract_num) < 0.01  # 微小な差は許容
                except (ValueError, TypeError):
                    # 数値変換に失敗した場合は文字列として厳密比較
                    comparison_results[csv_field] = str(csv_value) == str(extract_value)
    
    return comparison_results, predicted_values

def calculate_tokens_used(result_body: Dict[str, Any]) -> Dict[str, int]:
    """結果からトークン使用量の詳細を取得"""
    usage = result_body.get('usage', {})
    
    # 詳細なトークン使用量を取得
    token_details = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_input_tokens': 0,
        'total_tokens': 0
    }
    
    if 'prompt_token_count' in usage:
        token_details['input_tokens'] = usage['prompt_token_count']
    if 'candidates_token_count' in usage:
        token_details['output_tokens'] = usage['candidates_token_count']
    if 'cached_content_token_count' in usage:
        token_details['cached_input_tokens'] = usage['cached_content_token_count']
    if 'total_token_count' in usage:
        token_details['total_tokens'] = usage['total_token_count']
    elif token_details['input_tokens'] and token_details['output_tokens']:
        token_details['total_tokens'] = token_details['input_tokens'] + token_details['output_tokens'] + token_details['cached_input_tokens']
    
    return token_details

def process_single_row(args_tuple):
    """並列処理用のワーカー関数：単一行を処理する"""
    index, row, verbose = args_tuple
    
    filename = row['ファイル名']
    file_path = row['ファイルパス']
    
    # data/配下のPDFファイルパス
    pdf_path = os.path.join('data', file_path)
    
    result_data = {
        'index': index,
        'filename': filename,
        'file_path': file_path,
        'status': 'processing',
        'error': None,
        'result_row': None,
        'tokens': 0
    }
    
    if not os.path.exists(pdf_path):
        result_data['status'] = 'error'
        result_data['error'] = f"ファイルが見つかりません: {pdf_path}"
        result_data['result_row'] = {
            'ファイル名': filename,
            'ファイルパス': file_path,
            'エラー': result_data['error'],
            'input_tokens': 0,
            'output_tokens': 0,
            'cached_input_tokens': 0,
            'total_tokens': 0
        }
        return result_data
    
    try:
        # ローカル処理を実行
        result = process_pdf_file(pdf_path)
        
        if result.get('statusCode') != 200:
            error_body = json.loads(result['body'])
            raise Exception(f"処理エラー: {error_body.get('error', 'Unknown error')}")
        
        # レスポンスボディをパース
        body = json.loads(result['body'])
        
        # raw_responseが含まれている場合の警告（ここでは記録のみ）
        extracted_data = body.get('extracted_data', {})
        if 'raw_response' in extracted_data:
            result_data['warning'] = f"raw_responseが検出されました: {filename}"
        
        # 比較実行
        comparison, predicted_values = compare_values(body, row)
        
        # トークン数を取得
        token_details = calculate_tokens_used(body)
        result_data['tokens'] = token_details['total_tokens']
        
        # 結果をまとめる（比較結果と予測値の両方を含める）
        result_row = {
            'ファイル名': filename,
            'ファイルパス': file_path,
            'input_tokens': token_details['input_tokens'],
            'output_tokens': token_details['output_tokens'],
            'cached_input_tokens': token_details['cached_input_tokens'],
            'total_tokens': token_details['total_tokens']
        }
        result_row.update(comparison)
        result_row.update(predicted_values)
        
        # 一致率を計算
        match_count = sum(comparison.values())
        total_fields = len(comparison)
        match_rate = (match_count / total_fields) * 100 if total_fields > 0 else 0
        
        result_data['status'] = 'success'
        result_data['result_row'] = result_row
        result_data['match_rate'] = match_rate
        result_data['match_count'] = match_count
        result_data['total_fields'] = total_fields
        
        # 詳細表示の準備（verboseモード用）
        if verbose:
            result_data['verbose_info'] = []
            field_mapping = {
                'チップ入力結果': 'chip_input_result',
                '電話番号': 'phone_number',
                '発行者': 'issuer_name',
                '登録番号': 'registrated_number'
            }
            for csv_field, extract_field in field_mapping.items():
                csv_val = clean_value(row.get(csv_field))
                pred_val = extract_value_from_prediction(predicted_values.get(f"{csv_field}_pred"))
                match = comparison.get(csv_field)
                result_data['verbose_info'].append(f"  {csv_field}: {match} (CSV: '{csv_val}' vs 予測: '{pred_val}')")
        
        return result_data
        
    except Exception as e:
        result_data['status'] = 'error'
        result_data['error'] = str(e)
        result_data['result_row'] = {
            'ファイル名': filename,
            'ファイルパス': file_path,
            'エラー': str(e),
            'input_tokens': 0,
            'output_tokens': 0,
            'cached_input_tokens': 0,
            'total_tokens': 0
        }
        return result_data

def main():
    parser = argparse.ArgumentParser(description='Lambda関数の結果とCSVファイルを比較')
    parser.add_argument('--limit', type=int, default=5, help='処理する件数の上限（デフォルト: 5）')
    parser.add_argument('--csv', type=str, default='data/clipping_0521.csv', help='CSVファイルのパス')
    parser.add_argument('--output', type=str, default='comparison_results.csv', help='結果出力ファイル名')
    parser.add_argument('--verbose', action='store_true', help='詳細な比較結果を表示')
    parser.add_argument('--workers', type=int, default=4, help='並列処理のワーカー数（デフォルト: 4）')
    
    args = parser.parse_args()
    
    # CSVファイルを読み込み
    print(f"CSVファイルを読み込み中: {args.csv}")
    df = read_csv_data(args.csv)
    
    # 処理件数を制限
    df_limited = df.head(args.limit)
    print(f"処理対象: {len(df_limited)}件")
    print(f"並列ワーカー数: {args.workers}")
    
    results = []
    total_tokens = 0
    completed_count = 0
    
    # 進行状況表示用のロック
    progress_lock = threading.Lock()
    
    def update_progress(result_data):
        nonlocal completed_count, total_tokens
        with progress_lock:
            completed_count += 1
            total_tokens += result_data.get('tokens', 0)
            
            status_emoji = "✅" if result_data['status'] == 'success' else "❌"
            print(f"{status_emoji} ({completed_count}/{len(df_limited)}) {result_data['filename']}")
            
            if result_data['status'] == 'success':
                match_rate = result_data.get('match_rate', 0)
                match_count = result_data.get('match_count', 0)
                total_fields = result_data.get('total_fields', 0)
                tokens = result_data.get('tokens', 0)
                print(f"   一致率: {match_rate:.1f}% ({match_count}/{total_fields}) | トークン: {tokens:,}")
                
                # 詳細表示（verboseモード）
                if args.verbose and 'verbose_info' in result_data:
                    print(f"   詳細比較結果:")
                    for info in result_data['verbose_info']:
                        print(f"   {info}")
                        
                # 警告表示
                if 'warning' in result_data:
                    print(f"   ⚠️ {result_data['warning']}")
            else:
                print(f"   エラー: {result_data['error']}")
    
    print(f"\n🚀 並列処理を開始...")
    start_time = time.time()
    
    # 並列処理で各行を処理
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # タスクを投入
        future_to_index = {}
        for index, row in df_limited.iterrows():
            future = executor.submit(process_single_row, (index, row, args.verbose))
            future_to_index[future] = index
        
        # 完了したタスクから結果を取得
        for future in as_completed(future_to_index):
            try:
                result_data = future.result()
                results.append(result_data['result_row'])
                update_progress(result_data)
                
            except Exception as e:
                index = future_to_index[future]
                row = df_limited.iloc[index - df_limited.index[0]]
                filename = row['ファイル名']
                print(f"❌ 予期しないエラー: {filename} - {str(e)}")
                
                # エラーの場合の結果を追加
                error_row = {
                    'ファイル名': filename,
                    'ファイルパス': row['ファイルパス'],
                    'エラー': f"予期しないエラー: {str(e)}",
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'cached_input_tokens': 0,
                    'total_tokens': 0
                }
                results.append(error_row)
                completed_count += 1
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    print(f"\n⏱️ 処理時間: {processing_time:.2f}秒")
    print(f"📊 平均処理時間: {processing_time/len(df_limited):.2f}秒/件")
    
    # 結果をDataFrameに変換して保存
    if results:
        results_df = pd.DataFrame(results)
        results_df.to_csv(args.output, index=False, encoding='utf-8-sig')
        print(f"\n📄 結果を保存しました: {args.output}")
        
        # 統計情報を表示
        print(f"\n📈 統計情報:")
        print(f"総件数: {len(results)}")
        print(f"総トークン使用量: {total_tokens:,}")
        
        if len(results) > 0:
            # トークン使用量の詳細統計
            input_total = sum(row.get('input_tokens', 0) for row in results if isinstance(row.get('input_tokens'), int))
            output_total = sum(row.get('output_tokens', 0) for row in results if isinstance(row.get('output_tokens'), int))
            cached_total = sum(row.get('cached_input_tokens', 0) for row in results if isinstance(row.get('cached_input_tokens'), int))
            
            print(f"入力トークン合計: {input_total:,}")
            print(f"出力トークン合計: {output_total:,}")
            if cached_total > 0:
                print(f"キャッシュ入力トークン合計: {cached_total:,}")
            
            # 各フィールドの一致率を計算（_pred列とトークン列は除外）
            field_columns = [col for col in results_df.columns 
                           if col not in ['ファイル名', 'ファイルパス', 'input_tokens', 'output_tokens', 'cached_input_tokens', 'total_tokens', 'エラー'] 
                           and not col.endswith('_pred')]
            if field_columns:
                print(f"\n📊 フィールド別一致率:")
                for field in field_columns:
                    if field in results_df.columns:
                        match_count = results_df[field].sum() if results_df[field].dtype == bool else 0
                        total_count = len(results_df[results_df[field].notna()])
                        if total_count > 0:
                            rate = (match_count / total_count) * 100
                            print(f"  {field}: {rate:.1f}% ({match_count}/{total_count})")
    else:
        print("⚠️ 処理された結果がありません")

if __name__ == '__main__':
    main()
