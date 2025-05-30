#!/usr/bin/env python3
"""
PDF Bounding Box Visualization Tool

This tool visualizes AI-detected text regions and field extractions by overlaying
bounding box information from JSON files onto corresponding PDF documents.
"""

import json
import pandas as pd
import fitz  # PyMuPDF
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from pathlib import Path
import argparse
import sys
import io
from typing import Dict, List, Tuple, Optional
import colorsys

# 日本語フォント設定（利用可能なフォントのみ使用）
import matplotlib.font_manager as fm
plt.rcParams['font.family'] = ['Arial Unicode MS', 'DejaVu Sans', 'sans-serif']

class PDFBoundingBoxVisualizer:
    """
    A tool for visualizing bounding boxes from JSON files on PDF documents.
    """
    
    def __init__(self, base_path: str = "/Users/satoshusuke/Documents/tokium/ai-clipping-lambda"):
        self.base_path = Path(base_path)
        self.output_jsons_path = self.base_path / "output_jsons"
        self.output_jsons_worker_path = self.base_path / "output_jsons_worker"
        self.pdf_path = self.base_path / "data" / "pdf" / "sample-tanaka_re"
        self.csv_path = self.base_path / "data" / "clipping_0521.csv"
        
        # フィールドタイプ別の色定義
        self.field_colors = self._generate_field_colors()
        
    def _generate_field_colors(self) -> Dict[str, str]:
        """フィールドタイプ別の色を自動生成します"""
        # よく使われるフィールドタイプと色のマッピング
        common_fields = {
            'phone_number': '#FF6B6B',      # 赤
            'issuer_name': '#4ECDC4',       # 青緑
            'registrated_number': '#45B7D1', # 青
            'taxable_amount_for_10_percent': '#96CEB4', # 緑
            'tax_amount_for_10_percent': '#FFEAA7',     # 黄
            'taxable_amount_for_8_percent': '#DDA0DD',  # 紫
            'tax_amount_for_8_percent': '#98D8C8',      # ミント
            'bank_name': '#F7DC6F',         # 金
            'branch_name': '#BB8FCE',       # ラベンダー
            'account_type': '#85C1E9',      # 空色
            'account_number': '#F8C471',    # オレンジ
            'account_holder': '#82E0AA',    # 薄緑
            'payment_deadline': '#F1948A',  # サーモン
        }
        return common_fields
    
    def _get_field_color(self, field_name: str) -> str:
        """フィールド名に基づいて色を取得します"""
        if field_name in self.field_colors:
            return self.field_colors[field_name]
        
        # 動的に色を生成（ハッシュベース）
        hash_value = hash(field_name) % 360
        rgb = colorsys.hsv_to_rgb(hash_value / 360.0, 0.7, 0.9)
        return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
    
    def load_json_data(self, json_file: str) -> Optional[Dict]:
        """JSONファイルからバウンディングボックスデータを読み込みます"""
        json_path = self.output_jsons_path / json_file
        
        if not json_path.exists():
            print(f"JSON file not found: {json_path}")
            return None
            
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading JSON file: {e}")
            return None

    def load_worker_json_data(self, uuid: str) -> Optional[Dict]:
        """ワーカーディレクトリからJSONファイルを読み込みます"""
        # CSVからワーカーUUIDを取得
        worker_uuid = self.get_worker_uuid_from_csv(uuid)
        if not worker_uuid:
            print(f"Worker UUID not found for main UUID: {uuid}")
            return None
            
        json_path = self.output_jsons_worker_path / f"{worker_uuid}.json"
        
        if not json_path.exists():
            print(f"Worker JSON file not found: {json_path}")
            return None
            
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading worker JSON file: {e}")
            return None
    
    def get_worker_uuid_from_csv(self, main_uuid: str) -> Optional[str]:
        """CSVからメインUUIDに対応するワーカーUUIDを取得します"""
        try:
            csv_data = pd.read_csv(self.csv_path)
            matching_rows = csv_data[csv_data['サンプリングUUID'] == main_uuid]
            
            if matching_rows.empty:
                return None
                
            return matching_rows.iloc[0]['UUID']
        except Exception as e:
            print(f"Error reading CSV for worker UUID: {e}")
            return None

    def load_dual_json_data(self, json_filename: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """メインとワーカー両方のJSONデータを読み込みます"""
        # メインデータを読み込み
        main_data = self.load_json_data(json_filename)
        
        # UUIDを抽出してワーカーデータを読み込み
        uuid = self.extract_uuid_from_json_filename(json_filename)
        worker_data = self.load_worker_json_data(uuid)
        
        return main_data, worker_data
    
    def find_pdf_file(self, uuid: str) -> Optional[Path]:
        """UUIDに基づいて対応するPDFファイルを検索します"""
        # CSVファイルからファイルパスを検索
        try:
            csv_data = pd.read_csv(self.csv_path)
            matching_rows = csv_data[csv_data['サンプリングUUID'] == uuid]
            
            if matching_rows.empty:
                print(f"UUID not found in CSV: {uuid}")
                return None
                
            file_path = matching_rows.iloc[0]['ファイルパス']
            pdf_file_path = self.base_path / "data" / file_path
            
            if pdf_file_path.exists():
                return pdf_file_path
            else:
                print(f"PDF file not found: {pdf_file_path}")
                return None
                
        except Exception as e:
            print(f"Error finding PDF file: {e}")
            return None
    
    def extract_uuid_from_json_filename(self, json_filename: str) -> str:
        """JSONファイル名からUUIDを抽出します"""
        # '_output.json'を除去してUUIDを取得
        return json_filename.replace('_output.json', '')
    
    def render_pdf_page(self, pdf_path: Path, page_num: int = 0, dpi: int = 150) -> Tuple[np.ndarray, Tuple[float, float], float]:
        """PDFの指定ページを画像として描画します"""
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num]
            
            # OCR.pyと同じ方法でDPIに基づいてzoom係数を計算
            zoom = dpi / 72  # 72dpiがPyMuPDFのデフォルト
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # PNG形式で取得
            img_data = pix.tobytes("png")
            
            # NumPy配列に変換
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(img_data))
            img_array = np.array(img)
            
            # ページサイズを取得（ポイント単位）
            page_rect = page.rect
            page_size = (page_rect.width, page_rect.height)
            
            doc.close()
            return img_array, page_size, zoom
            
        except Exception as e:
            print(f"Error rendering PDF page: {e}")
            return None, None, None
    
    def visualize_bounding_boxes(self, json_filename: str, page_num: int = 0, 
                               show_labels: bool = True, show_values: bool = True,
                               filter_fields: Optional[List[str]] = None,
                               min_confidence: float = 0.0, dual_mode: bool = False,
                               output_dir: str = 'output_bbox'):
        """
        バウンディングボックスを可視化します
        
        Args:
            json_filename: JSONファイル名
            page_num: 表示するページ番号（0から開始）
            show_labels: フィールド名を表示するか
            show_values: 抽出された値を表示するか
            filter_fields: 表示するフィールドのリスト（Noneの場合は全て表示）
            min_confidence: 最小信頼度スコア
            dual_mode: メインとワーカーの結果を同時に表示するか
        """
        if dual_mode:
            # デュアルモード: メインとワーカーの両方を表示
            main_data, worker_data = self.load_dual_json_data(json_filename)
            
            if not main_data and not worker_data:
                print("メインまたはワーカーのJSONファイルが見つかりません")
                return
        else:
            # 通常モード: メインのみ表示
            main_data = self.load_json_data(json_filename)
            worker_data = None
            
            if not main_data:
                return
            
        # UUIDを抽出してPDFファイルを検索
        uuid = self.extract_uuid_from_json_filename(json_filename)
        pdf_path = self.find_pdf_file(uuid)
        if not pdf_path:
            return
            
        # PDFページを描画
        img_array, page_size, zoom = self.render_pdf_page(pdf_path, page_num)
        if img_array is None:
            return
            
        # プロット設定
        fig, ax = plt.subplots(1, 1, figsize=(16, 20))
        ax.imshow(img_array)
        
        # データを処理してバウンディングボックスを描画
        main_clips = []
        worker_clips = []
        
        if main_data:
            clips = main_data.get('clips', [])
            main_clips = [clip for clip in clips if clip.get('page', 1) == page_num + 1]
            
        if worker_data:
            clips = worker_data.get('clips', [])
            worker_clips = [clip for clip in clips if clip.get('page', 1) == page_num + 1]
        
        # フィルタリング
        if filter_fields:
            main_clips = [clip for clip in main_clips if clip.get('field_name') in filter_fields]
            worker_clips = [clip for clip in worker_clips if clip.get('field_name') in filter_fields]
        
        if min_confidence > 0:
            main_clips = [clip for clip in main_clips if clip.get('reliability_score', 0) >= min_confidence]
            worker_clips = [clip for clip in worker_clips if clip.get('reliability_score', 0) >= min_confidence]
        
        print(f"画像サイズ: {img_array.shape[1]}x{img_array.shape[0]}px, PDFページサイズ: {page_size[0]:.0f}x{page_size[1]:.0f}pt")
        
        # メインデータのバウンディングボックスを描画
        displayed_fields = set()
        
        for clip in main_clips:
            self._draw_bounding_box(ax, clip, img_array, show_labels, show_values, 
                                  source_type="main", displayed_fields=displayed_fields)
        
        # ワーカーデータのバウンディングボックスを描画
        for clip in worker_clips:
            self._draw_bounding_box(ax, clip, img_array, show_labels, show_values, 
                                  source_type="worker", displayed_fields=displayed_fields)
        
        # タイトル設定
        title_parts = [f"PDF: {pdf_path.name} (Page {page_num + 1})"]
        if dual_mode:
            main_status = "✓" if main_data else "✗"
            worker_status = "✓" if worker_data else "✗"
            title_parts.append(f"Main {main_status} / Worker {worker_status}")
        else:
            title_parts.append(f"JSON: {json_filename}")
            
        ax.set_title("\n".join(title_parts), fontsize=14, pad=20)
        ax.axis('off')
        
        # 凡例を作成
        if displayed_fields:
            self._create_legend(ax, displayed_fields, dual_mode, main_clips, worker_clips)
        
        plt.tight_layout()
        
        # 画像を保存
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # ファイル名を生成
        if dual_mode:
            filename = f"{uuid}_page{page_num + 1}_dual.png"
        else:
            filename = f"{uuid}_page{page_num + 1}.png"
            
        save_path = output_path / filename
        plt.savefig(save_path, dpi=300, bbox_inches='tight', 
                   facecolor='white', edgecolor='none')
        print(f"画像を保存しました: {save_path}")
        
        plt.show()
        
        # 統計情報を表示
        self._print_statistics(json_filename, pdf_path, page_num, main_clips, worker_clips, dual_mode)

    def _draw_bounding_box(self, ax, clip: Dict, img_array: np.ndarray, 
                          show_labels: bool, show_values: bool, source_type: str,
                          displayed_fields: set):
        """バウンディングボックスを描画する"""
        field_name = clip.get('field_name', 'unknown')
        value = clip.get('value', '')
        
        # Vision APIから返された座標を取得（既にピクセル座標）
        x = clip.get('x_coordinate', 0)
        y = clip.get('y_coordinate', 0) 
        width = clip.get('width', 0)
        height = clip.get('height', 0)
        
        confidence = clip.get('reliability_score', 0)
        
        # 座標が画像範囲内にあるかチェック
        if x < 0 or y < 0 or x + width > img_array.shape[1] or y + height > img_array.shape[0]:
            print(f"警告: {field_name} ({source_type}) の座標が画像範囲外です - 調整されます")
            x = max(0, min(x, img_array.shape[1] - 10))
            y = max(0, min(y, img_array.shape[0] - 10))
            width = min(width, img_array.shape[1] - x)
            height = min(height, img_array.shape[0] - y)
        
        # 色を取得
        color = self._get_field_color(field_name)
        
        # ソースタイプに応じてスタイルを設定
        if source_type == "main":
            linestyle = '-'      # 実線
            alpha = 0.3
            linewidth = 2
            label_prefix = "[M]"
        else:  # worker
            linestyle = '--'     # 点線
            alpha = 0.2
            linewidth = 2.5
            label_prefix = "[W]"
        
        # バウンディングボックスを描画
        rect = patches.Rectangle((x, y), width, height, 
                               linewidth=linewidth, edgecolor=color, 
                               facecolor=color, alpha=alpha, linestyle=linestyle)
        ax.add_patch(rect)
        
        # ラベルテキストを構成
        label_parts = []
        if show_labels:
            label_parts.append(f"{label_prefix} {field_name}")
        if show_values and value:
            # 長い値は切り詰める
            display_value = value[:20] + "..." if len(value) > 20 else value
            label_parts.append(f": {display_value}")
        if confidence < 1.0:
            label_parts.append(f" ({confidence:.2f})")
            
        if label_parts:
            label_text = "".join(label_parts)
            # ワーカーのラベルは少し下にずらす
            y_offset = -5 if source_type == "main" else -25
            ax.text(x, y + y_offset, label_text, fontsize=7, 
                   bbox=dict(boxstyle="round,pad=0.2", facecolor=color, alpha=0.9),
                   verticalalignment='bottom')
        
        displayed_fields.add(field_name)

    def _create_legend(self, ax, displayed_fields: set, dual_mode: bool, 
                      main_clips: List[Dict], worker_clips: List[Dict]):
        """凡例を作成する"""
        legend_elements = []
        
        # フィールド別の凡例
        for field in sorted(displayed_fields):
            color = self._get_field_color(field)
            legend_elements.append(patches.Patch(color=color, label=field))
            
        # デュアルモードの場合はソースタイプの凡例も追加
        if dual_mode and main_clips and worker_clips:
            legend_elements.append(patches.Patch(color='gray', label='─────────'))
            legend_elements.append(patches.Patch(color='black', linestyle='-', 
                                               label='[M] Main Output', fill=False))
            legend_elements.append(patches.Patch(color='black', linestyle='--', 
                                               label='[W] Worker Output', fill=False))
        
        ax.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(1, 1))

    def _print_statistics(self, json_filename: str, pdf_path: Path, page_num: int,
                         main_clips: List[Dict], worker_clips: List[Dict], dual_mode: bool):
        """統計情報を表示する"""
        print(f"\n=== 検出情報 ===")
        print(f"JSON ファイル: {json_filename}")
        print(f"PDF ファイル: {pdf_path.name}")
        print(f"ページ: {page_num + 1}")
        
        if dual_mode:
            print(f"メイン検出フィールド数: {len(main_clips)}")
            print(f"ワーカー検出フィールド数: {len(worker_clips)}")
            
            # フィールドの比較
            main_fields = set(clip.get('field_name') for clip in main_clips)
            worker_fields = set(clip.get('field_name') for clip in worker_clips)
            
            common_fields = main_fields & worker_fields
            main_only = main_fields - worker_fields
            worker_only = worker_fields - main_fields
            
            if common_fields:
                print(f"共通フィールド: {', '.join(sorted(common_fields))}")
            if main_only:
                print(f"メインのみ: {', '.join(sorted(main_only))}")
            if worker_only:
                print(f"ワーカーのみ: {', '.join(sorted(worker_only))}")
        else:
            print(f"検出されたフィールド数: {len(main_clips)}")
        
        # 詳細情報
        if main_clips or worker_clips:
            print(f"\n=== フィールド詳細 ===")
            
            # メインクリップ
            if main_clips:
                print("【メイン出力】")
                for clip in main_clips:
                    field_name = clip.get('field_name', 'unknown')
                    value = clip.get('value', '')
                    confidence = clip.get('reliability_score', 0)
                    print(f"  {field_name}: {value} (信頼度: {confidence:.2f})")
            
            # ワーカークリップ
            if worker_clips:
                print("【ワーカー出力】")
                for clip in worker_clips:
                    field_name = clip.get('field_name', 'unknown')
                    value = clip.get('value', '')
                    confidence = clip.get('reliability_score', 0)
                    print(f"  {field_name}: {value} (信頼度: {confidence:.2f})")
    
    def list_available_files(self) -> List[str]:
        """利用可能なJSONファイルのリストを取得します"""
        json_files = list(self.output_jsons_path.glob("*_output.json"))
        return [f.name for f in json_files]

    def list_dual_mode_files(self) -> List[Tuple[str, bool, bool]]:
        """デュアルモード用のファイル情報を取得します"""
        main_files = set(f.stem.replace('_output', '') for f in self.output_jsons_path.glob("*_output.json"))
        
        # CSVファイルを読み込んでマッピングを取得
        uuid_mapping = {}
        try:
            csv_data = pd.read_csv(self.csv_path)
            for _, row in csv_data.iterrows():
                main_uuid = row['サンプリングUUID']
                worker_uuid = row['UUID']
                if pd.notna(main_uuid) and pd.notna(worker_uuid):
                    uuid_mapping[main_uuid] = worker_uuid
        except Exception as e:
            print(f"Warning: Could not read CSV mapping: {e}")
        
        file_info = []
        
        for main_uuid in sorted(main_files):
            main_exists = True  # main_filesから取得しているので必ず存在
            worker_exists = False
            
            # CSVマッピングからワーカーUUIDを取得
            worker_uuid = uuid_mapping.get(main_uuid)
            if worker_uuid:
                worker_path = self.output_jsons_worker_path / f"{worker_uuid}.json"
                worker_exists = worker_path.exists()
            
            main_filename = f"{main_uuid}_output.json"
            file_info.append((main_filename, main_exists, worker_exists))
        
        return file_info
    
    def analyze_field_distribution(self) -> Dict[str, int]:
        """全JSONファイルのフィールド分布を分析します"""
        field_counts = {}
        json_files = self.list_available_files()
        
        print(f"分析中... {len(json_files)} ファイル")
        
        for json_file in json_files[:100]:  # 最初の100ファイルを分析
            data = self.load_json_data(json_file)
            if data:
                clips = data.get('clips', [])
                for clip in clips:
                    field_name = clip.get('field_name', 'unknown')
                    field_counts[field_name] = field_counts.get(field_name, 0) + 1
        
        return field_counts


def main():
    parser = argparse.ArgumentParser(description='PDF Bounding Box Visualizer')
    parser.add_argument('--json-file', '-j', type=str, 
                       help='JSON file name (e.g., "00004622-f2fb-426e-84c7-48f8fc435110_output.json")')
    parser.add_argument('--page', '-p', type=int, default=0,
                       help='Page number to display (0-based, default: 0)')
    parser.add_argument('--no-labels', action='store_true',
                       help='Hide field labels')
    parser.add_argument('--no-values', action='store_true',
                       help='Hide extracted values')
    parser.add_argument('--filter-fields', '-f', nargs='+',
                       help='Show only specified fields')
    parser.add_argument('--min-confidence', '-c', type=float, default=0.0,
                       help='Minimum confidence score (default: 0.0)')
    parser.add_argument('--dual-mode', '-d', action='store_true',
                       help='Compare main and worker outputs simultaneously')
    parser.add_argument('--list-files', '-l', action='store_true',
                       help='List available JSON files')
    parser.add_argument('--list-dual', action='store_true',
                       help='List files with main/worker availability status')
    parser.add_argument('--analyze', '-a', action='store_true',
                       help='Analyze field distribution')
    parser.add_argument('--uuid', '-u', type=str,
                       help='UUID to visualize (for dual-mode or single mode)')
    parser.add_argument('--output-dir', '-o', type=str, default='output_bbox',
                       help='Output directory for generated images (default: output_bbox)')
    
    args = parser.parse_args()
    
    # 可視化ツールを初期化
    visualizer = PDFBoundingBoxVisualizer()
    
    if args.list_files:
        print("利用可能なJSONファイル:")
        files = visualizer.list_available_files()
        for i, file in enumerate(files[:20], 1):  # 最初の20ファイルを表示
            print(f"  {i:2d}. {file}")
        if len(files) > 20:
            print(f"  ... 他 {len(files) - 20} ファイル")
        return

    if args.list_dual:
        print("デュアルモード対応ファイル一覧:")
        print("  ファイル名                                           Main Worker")
        print("  " + "="*60)
        
        file_info = visualizer.list_dual_mode_files()
        both_count = 0
        main_only_count = 0
        worker_only_count = 0
        
        for i, (filename, main_exists, worker_exists) in enumerate(file_info[:30], 1):
            main_status = "✓" if main_exists else "✗"
            worker_status = "✓" if worker_exists else "✗"
            
            # カウント
            if main_exists and worker_exists:
                both_count += 1
            elif main_exists:
                main_only_count += 1
            else:
                worker_only_count += 1
            
            # 短縮表示用のファイル名
            display_name = filename[:45] + "..." if len(filename) > 48 else filename
            print(f"  {i:2d}. {display_name:<48} {main_status:^4} {worker_status:^6}")
            
        if len(file_info) > 30:
            print(f"  ... 他 {len(file_info) - 30} ファイル")
            
        print(f"\n統計:")
        print(f"  両方存在: {both_count} ファイル")
        print(f"  メインのみ: {main_only_count} ファイル") 
        print(f"  ワーカーのみ: {worker_only_count} ファイル")
        return
    
    if args.analyze:
        print("フィールド分布を分析中...")
        field_dist = visualizer.analyze_field_distribution()
        print("\n=== フィールド分布 ===")
        for field, count in sorted(field_dist.items(), key=lambda x: x[1], reverse=True):
            print(f"  {field}: {count} 回")
        return
    
    if not args.json_file and not args.uuid:
        print("JSONファイルまたはUUIDを指定してください。利用可能なファイルを確認するには --list-files を使用してください。")
        print("\n例:")
        print("  # JSONファイル指定（通常モード）")
        print("  python pdf_bbox_visualizer.py -j 00004622-f2fb-426e-84c7-48f8fc435110_output.json")
        print("\n  # UUID指定（デュアルモード）")
        print("  python pdf_bbox_visualizer.py --uuid 0000e9e0-d04e-4cd5-bc49-f9567932f10d --dual-mode")
        print("\n  # フィールドフィルタリング")
        print("  python pdf_bbox_visualizer.py -j 00004622-f2fb-426e-84c7-48f8fc435110_output.json -d -f phone_number issuer_name")
        return
    
    # JSONファイル名の決定
    if args.uuid:
        json_filename = f"{args.uuid}_output.json"
    else:
        json_filename = args.json_file
    
    # バウンディングボックスを可視化
    visualizer.visualize_bounding_boxes(
        json_filename=json_filename,
        page_num=args.page,
        show_labels=not args.no_labels,
        show_values=not args.no_values,
        filter_fields=args.filter_fields,
        min_confidence=args.min_confidence,
        dual_mode=args.dual_mode,
        output_dir=args.output_dir
    )


if __name__ == "__main__":
    main()
