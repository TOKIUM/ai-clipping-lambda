#!/usr/bin/env python3
"""
output_jsonsフォルダ内のJSONファイルから各field_nameのvalueを抽出し、CSVファイルにまとめるスクリプト
"""

import json
import csv
import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set


def extract_data_from_json_files(json_folder: str) -> Dict[str, Dict[str, str]]:
    """
    JSONファイルからデータを抽出する
    
    Args:
        json_folder: JSONファイルが含まれるフォルダのパス
        
    Returns:
        {filename: {field_name: value}} の辞書
    """
    data = {}
    json_folder_path = Path(json_folder)
    
    # JSONファイルを処理
    for json_file in json_folder_path.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            filename = json_file.stem  # 拡張子を除いたファイル名
            file_data = {}
            
            # clipsからfield_nameとvalueを抽出
            if 'clips' in json_data and isinstance(json_data['clips'], list):
                for clip in json_data['clips']:
                    if 'field_name' in clip and 'value' in clip:
                        field_name = clip['field_name']
                        value = clip['value']
                        file_data[field_name] = value
            
            data[filename] = file_data
            print(f"処理完了: {json_file.name}")
            
        except Exception as e:
            print(f"エラー - {json_file.name}: {e}")
            continue
    
    return data


def get_all_field_names(data: Dict[str, Dict[str, str]]) -> List[str]:
    """
    すべてのファイルから出現するfield_nameを収集してソートする
    
    Args:
        data: 抽出されたデータ
        
    Returns:
        ソートされたfield_nameのリスト
    """
    all_fields = set()
    for file_data in data.values():
        all_fields.update(file_data.keys())
    
    return sorted(list(all_fields))


def write_to_csv(data: Dict[str, Dict[str, str]], output_file: str):
    """
    データをCSVファイルに書き出す
    
    Args:
        data: 抽出されたデータ
        output_file: 出力CSVファイルのパス
    """
    if not data:
        print("データが空です。CSVファイルは作成されませんでした。")
        return
    
    all_field_names = get_all_field_names(data)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        # CSVヘッダー: filename + すべてのfield_name
        fieldnames = ['filename'] + all_field_names
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        # ヘッダーを書き込み
        writer.writeheader()
        
        # データ行を書き込み
        for filename, file_data in data.items():
            row = {'filename': filename}
            # 各field_nameの値を設定（存在しない場合は空文字）
            for field_name in all_field_names:
                row[field_name] = file_data.get(field_name, '')
            writer.writerow(row)
    
    print(f"CSVファイルが作成されました: {output_file}")
    print(f"処理ファイル数: {len(data)}")
    print(f"フィールド数: {len(all_field_names)}")


def main():
    """メイン処理"""
    # 設定
    json_folder = "output_jsons"
    output_csv = "extracted_field_data.csv"
    
    print("=== JSON to CSV 抽出スクリプト ===")
    print(f"入力フォルダ: {json_folder}")
    print(f"出力ファイル: {output_csv}")
    print()
    
    # JSONフォルダの存在確認
    if not os.path.exists(json_folder):
        print(f"エラー: フォルダ '{json_folder}' が見つかりません。")
        return
    
    # データ抽出
    print("JSONファイルからデータを抽出中...")
    data = extract_data_from_json_files(json_folder)
    
    if not data:
        print("処理できるJSONファイルが見つかりませんでした。")
        return
    
    print()
    
    # CSV出力
    print("CSVファイルに書き出し中...")
    write_to_csv(data, output_csv)
    
    print("\n処理完了!")


if __name__ == "__main__":
    main()
