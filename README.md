# AI Clipping Lambda

AWS Lambda を使用してS3から画像・PDFをダウンロードし、OCR処理、LLMによる情報抽出、結果の後処理（バウンディングボックス補正、クリップ形式への変換）を行い、結果をSQSに送信するサーバレスアプリケーションです。

## 機能概要

1.  S3イベント情報をSQSから受け取り、S3から画像/PDFファイルをダウンロード
2.  Google Cloud Vision APIを使ってOCR処理（文字起こし）を実行
3.  抽出されたテキストとOCR結果（単語ごとの座標情報）をLLM（OpenAI API）に送信して必要な情報を抽出
4.  LLMの抽出結果に含まれる座標情報（バウンディングボックス）を、OCRの単語座標情報を用いて補正
5.  抽出・補正された情報を後処理・正規化し、指定のクリップ形式に変換
6.  処理結果を別のSQSキューに送信

## 環境構築

### 前提条件

- Node.js 16.x 以上
- Python 3.9
- AWS CLI（設定済み）
- Serverless Framework
- Docker（ローカルテスト用）
- Poetry (Pythonパッケージ管理)

### インストール

```bash
# Serverless Frameworkのインストール（初回のみ）
npm install -g serverless

# Node.js依存関係のインストール
npm install

# Python依存関係のインストール (Poetryを使用)
poetry install

# Poetryを使用しない場合 (requirements.txt)
# python -m venv .venv
# source .venv/bin/activate  # Windows: .venv\Scripts\activate
# pip install -r requirements.txt
```

### 環境変数の設定

`.env` ファイルを作成し、必要な環境変数を設定します：

```
OPENAI_API_KEY=your_openai_api_key
# 必要に応じて他のAWS関連設定なども追加
```

Google Cloud Vision APIを使用するためには、認証情報を設定する必要があります。プロジェクトルートに `credential.json` という名前でサービスアカウントキーファイルを配置してください。

```bash
# Google Cloud認証情報を環境変数として設定する場合 (代替)
# export GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/google-credentials.json
```

## デプロイ

```bash
# 開発環境へのデプロイ
serverless deploy --stage dev

# 本番環境へのデプロイ
serverless deploy --stage prod
```

## ローカルでのテスト

### LocalStackを使用したテスト

LocalStackを使用してAWSサービス（S3, SQS）をローカルでエミュレートできます。

```bash
# Docker ComposeでLocalStackとLambdaコンテナを起動
docker-compose up -d

# LocalStackに必要なAWSリソースを作成 (init-aws.shを実行)
# (docker-compose up時に自動実行される設定の場合もあります)

# ローカルテストスクリプトを実行
python local_test.py
```

### コアロジックのテスト (`local_test.py`)

`local_test.py` スクリプトを使用すると、ローカルの画像またはPDFファイルに対して、OCR、LLM抽出、データ後処理、最終的なSQSメッセージ形式へのフォーマットというコアな処理パイプラインを実行し、その結果を確認できます。

**注意:** このスクリプトは以下の機能はテストしません。

*   SQSトリガーによるLambda起動
*   S3からのファイルダウンロード
*   SQSメッセージの解析
*   SQSへの結果送信

コアな抽出・処理ロジックのデバッグや確認に役立ちます。

```bash
# 基本的な実行方法
poetry run python local_test.py path/to/your/image_or_pdf.ext

# 結果をファイルに保存する場合
poetry run python local_test.py path/to/your/image_or_pdf.ext -o output.json

# 詳細なログを表示する場合
poetry run python local_test.py path/to/your/image_or_pdf.ext -v

# data/pdfディレクトリ内のファイルをテストする場合
poetry run python local_test.py data/pdf/hoge/001.pdf -o output_jsons/001_output.json

# Poetryを使用しない場合
python local_test.py path/to/your/image_or_pdf.ext -o output.json
```

### ユニットテストの実行

```bash
pytest tests/unit
```

## 検証ツール

`verification/`ディレクトリには、AI抽出結果の分析・検証・比較を行うための専用ツールが含まれています。

### 並列ローカルテスト実行 (`verification/run_local_tests.py`)

CSV ファイル内の複数のファイルに対して `local_test.py` を並列実行し、バッチ処理を効率的に行うスクリプトです。

```bash
# 基本的な実行方法（CSVファイル内の全ファイルを処理）
poetry run python verification/run_local_tests.py

# 並列プロセス数を指定（デフォルト：4）
poetry run python verification/run_local_tests.py --num-processes 8

# 特定の範囲のファイルのみ処理（例：最初の10ファイル）
poetry run python verification/run_local_tests.py --limit 10

# 出力ディレクトリを指定
poetry run python verification/run_local_tests.py --output-dir custom_output

# CSVファイルを指定（デフォルト：data/clipping_0521.csv）
poetry run python verification/run_local_tests.py --csv-file data/custom_file.csv

# Poetryを使用しない場合
python verification/run_local_tests.py
```

### JSON結果のCSV変換 (`verification/extract_json_to_csv.py`)

`output_jsons/`ディレクトリ内のJSONファイルから抽出結果を集約し、フィールドごとに整理されたCSVファイルを生成するスクリプトです。

```bash
# 基本的な実行方法（output_jsonsディレクトリを処理）
poetry run python verification/extract_json_to_csv.py

# 入力ディレクトリを指定
poetry run python verification/extract_json_to_csv.py --input-dir output_jsons_worker

# 出力CSVファイル名を指定
poetry run python verification/extract_json_to_csv.py --output extracted_results.csv

# 特定のフィールドのみ抽出
poetry run python verification/extract_json_to_csv.py --fields phone_number issuer_name

# Poetryを使用しない場合
python verification/extract_json_to_csv.py --input-dir output_jsons --output results.csv
```

### JSON結果の比較分析 (`verification/compare_json_clips.py`)

メインとワーカーの抽出結果を比較し、バウンディングボックスの座標差分を計算・分析するスクリプトです。

```bash
# 基本的な実行方法
poetry run python verification/compare_json_clips.py

# カスタム設定で実行
poetry run python verification/compare_json_clips.py \
  --csv-file data/clipping_0521.csv \
  --dir1 output_jsons \
  --dir2 output_jsons_worker \
  --output comparison_results.csv

# 特定のフィールドのみ比較
poetry run python verification/compare_json_clips.py --fields phone_number registrated_number

# Poetryを使用しない場合
python verification/compare_json_clips.py
```

**出力結果例:**
- `delta_x_cordinate`: X座標の差分
- `delta_y_cordinate`: Y座標の差分
- `delta_width`: 幅の差分
- `delta_height`: 高さの差分

### Lambda結果とCSVの並列比較 (`verification/lambda_csv_comparison.py`)

Lambda関数のローカル処理結果とCSVファイルの期待値を並列で比較し、精度を検証するスクリプトです。大量のデータを効率的に処理できるよう並列処理に対応しています。

```bash
# 基本的な実行方法（5件、4並列で処理）
poetry run python verification/lambda_csv_comparison.py

# 1000件すべてを8並列で処理
poetry run python verification/lambda_csv_comparison.py --limit 1000 --workers 8

# 100件を4並列で処理（詳細モード）
poetry run python verification/lambda_csv_comparison.py --limit 100 --workers 4 --verbose

# 500件を6並列で処理して結果を保存
poetry run python verification/lambda_csv_comparison.py --limit 500 --workers 6 --output full_comparison_results.csv

# CSVファイルを指定
poetry run python verification/lambda_csv_comparison.py --csv data/custom_file.csv --limit 100

# Poetryを使用しない場合
python verification/lambda_csv_comparison.py --limit 100 --workers 4
```

**パラメータ説明:**
- `--limit`: 処理する件数の上限（デフォルト: 5）
- `--csv`: CSVファイルのパス（デフォルト: data/clipping_0521.csv）
- `--output`: 結果出力ファイル名（デフォルト: comparison_results.csv）
- `--verbose`: 詳細な比較結果を表示
- `--workers`: 並列処理のワーカー数（デフォルト: 4）

**推奨設定:**
- **ワーカー数**: CPUコア数の1-2倍（例：8コアなら8-16ワーカー）
- **大量処理**: 1000件処理時は `--workers 8` 以上を推奨
- **メモリ制限**: 各ワーカーが独立してPDF処理を行うため、メモリ使用量に注意

**出力結果:**
- フィールド別の一致率（チップ入力結果、電話番号、発行者など）
- トークン使用量の詳細統計
- 処理時間と平均処理時間
- 予測値と期待値の比較結果（_pred列）

## PDF可視化ツール

`pdf_bbox_visualizer.py` は、AI抽出結果のバウンディングボックスをPDF上に可視化するツールです。メインとワーカーの出力結果を同時に比較表示できるデュアルモード機能も提供しています。

### 前提条件

可視化ツールを使用するには、以下のデータが必要です：

- `output_jsons/` ディレクトリ内のメイン出力JSONファイル
- `output_jsons_worker/` ディレクトリ内のワーカー出力JSONファイル（デュアルモード使用時）
- `data/hoge.csv` CSVファイル（UUIDマッピング用）
- `data/pdf/` ディレクトリ内の対応するPDFファイル

### 基本的な使用方法

```bash
# 利用可能なJSONファイル一覧を表示
poetry run python pdf_bbox_visualizer.py --list-files

# デュアルモード対応ファイル一覧を表示（メイン/ワーカーの存在状況を確認）
poetry run python pdf_bbox_visualizer.py --list-dual

# 通常モード：メイン出力のみを可視化
poetry run python pdf_bbox_visualizer.py -j {uuid}_output.json

# UUIDを直接指定して可視化
poetry run python pdf_bbox_visualizer.py --uuid {uuid}

# デュアルモード：メインとワーカーの結果を同時比較
poetry run python pdf_bbox_visualizer.py --uuid {uuid} --dual-mode

# 出力ディレクトリを指定
poetry run python pdf_bbox_visualizer.py --uuid {uuid} --dual-mode --output-dir results
```

### 高度な使用方法

```bash
# 特定のフィールドのみを表示（フィールドフィルタリング）
poetry run python pdf_bbox_visualizer.py --uuid {uuid} --dual-mode \
  -f phone_number issuer_name registrated_number

# 信頼度による閾値フィルタ（0.5以上のフィールドのみ表示）
poetry run python pdf_bbox_visualizer.py --uuid {uuid} --dual-mode \
  --min-confidence 0.5

# ラベルや値を非表示にする
poetry run python pdf_bbox_visualizer.py --uuid {uuid} \
  --no-labels --no-values

# 特定のページを表示（2ページ目を表示）
poetry run python pdf_bbox_visualizer.py --uuid {uuid} --page 1

# フィールド分布を分析
poetry run python pdf_bbox_visualizer.py --analyze
```

### デュアルモードの機能

デュアルモードでは以下の機能が利用できます：

- **視覚的差別化**：メイン出力は実線（`[M]`プレフィックス）、ワーカー出力は点線（`[W]`プレフィックス）で表示
- **自動UUIDマッピング**：CSVファイルの「サンプリングUUID」（メイン）と「UUID」（ワーカー）を自動変換
- **比較統計**：共通フィールド、メインのみ、ワーカーのみの分析表示
- **信頼度比較**：メインとワーカーの信頼度スコア比較
- **フィルタリング対応**：両方のデータセットに対してフィールドフィルタや信頼度フィルタを適用

### 実用的な使用例

```bash
# 1. まず対応ファイルを確認
poetry run python pdf_bbox_visualizer.py --list-dual

# 2. 基本的なデュアルモード比較
poetry run python pdf_bbox_visualizer.py --uuid {uuid} --dual-mode

# 3. 重要フィールドのみに絞った比較
poetry run python pdf_bbox_visualizer.py --uuid {uuid} --dual-mode \
  -f phone_number issuer_name registrated_number taxable_amount_for_10_percent

# 4. 高い信頼度のフィールドのみ表示（ノイズ除去）
poetry run python pdf_bbox_visualizer.py --uuid {uuid} --dual-mode \
  --min-confidence 0.8

# 5. バッチ処理（複数ファイルを処理）
for uuid in $(head -5 data/hoge.csv | tail -4 | cut -d',' -f1); do
  poetry run python pdf_bbox_visualizer.py --uuid "$uuid" --dual-mode --output-dir batch_results
done

# 6. フィールド分布の事前分析
poetry run python pdf_bbox_visualizer.py --analyze
```

### 出力ファイル

実行すると以下のファイルが生成されます：

- **PNG画像ファイル**（指定したoutput-dirに保存）
  - 通常モード：`{UUID}_page{ページ番号}.png`
  - デュアルモード：`{UUID}_page{ページ番号}_dual.png`
- **画像コンテンツ**
  - バウンディングボックス（色分けされたフィールド別）
  - フィールド名とプレフィックス（`[M]`/`[W]`）
  - 抽出された値（20文字制限、切り詰め表示）
  - 信頼度スコア（1.00未満の場合のみ表示）
  - 凡例（フィールド色とソースタイプの説明）

### 統計出力

ツール実行時には以下の統計情報がコンソールに表示されます：

```
=== 検出情報 ===
JSON ファイル: 00021091-7ae9-4c3f-b350-3e9675f4a9f1_output.json
PDF ファイル: 00021091-7ae9-4c3f-b350-3e9675f4a9f1.pdf
ページ: 1
メイン検出フィールド数: 7
ワーカー検出フィールド数: 3
共通フィールド: issuer_name, phone_number, registrated_number

=== フィールド詳細 ===
【メイン出力】
  phone_number: 047-451-2831 (信頼度: 1.00)
  issuer_name: 日本リファイン株式会社 (信頼度: 1.00)
  registrated_number: T7021001015409 (信頼度: 1.00)
【ワーカー出力】
  phone_number:  (信頼度: 0.00)
  issuer_name:  (信頼度: 0.00)
  registrated_number:  (信頼度: 0.00)
```

### コマンドライン引数一覧

| 引数 | 短縮形 | 説明 |
|------|--------|------|
| `--json-file` | `-j` | JSONファイル名を直接指定 |
| `--uuid` | `-u` | UUIDを指定（自動的にJSONファイル名を生成） |
| `--dual-mode` | `-d` | デュアルモード（メイン+ワーカー同時表示） |
| `--page` | `-p` | 表示するページ番号（0ベース、デフォルト：0） |
| `--filter-fields` | `-f` | 表示するフィールドを限定 |
| `--min-confidence` | `-c` | 最小信頼度スコア（デフォルト：0.0） |
| `--output-dir` | `-o` | 画像保存ディレクトリ（デフォルト：output_bbox） |
| `--no-labels` | | フィールド名を非表示 |
| `--no-values` | | 抽出値を非表示 |
| `--list-files` | `-l` | 利用可能なJSONファイル一覧を表示 |
| `--list-dual` | | デュアルモード対応ファイル一覧を表示 |
| `--analyze` | `-a` | フィールド分布を分析 |

### トラブルシューティング

**CSVファイルが見つからない**
```bash
# CSVファイルのパスを確認
ls -la data/hoge.csv
```

**PDFファイルが見つからない**
```bash
# PDFファイルの存在確認
find data/pdf -name "*.pdf" | head -5
```

**ワーカーJSONファイルが見つからない**
```bash
# ワーカーディレクトリの確認
ls -la output_jsons_worker/ | head -5

# マッピング確認（CSVの最初の数行）
head -3 data/hoge.csv
```

**Poetryが使用できない場合**
```bash
# requirements.txtを生成してpipで実行
poetry export -f requirements.txt --output requirements.txt
pip install -r requirements.txt
python pdf_bbox_visualizer.py --help
```

## ディレクトリ構成

```
.
├── credential.json     # Google Cloud認証情報ファイル (配置が必要)
├── docker-compose.yml  # Docker Compose設定 (LocalStack用)
├── Dockerfile          # Lambda実行環境用Dockerファイル
├── handler.py          # Lambdaエントリーポイント
├── local_test.py       # ローカルテスト用スクリプト
├── pdf_bbox_visualizer.py # PDF可視化ツール
├── poetry.lock         # Poetryロックファイル
├── pyproject.toml      # Poetry設定ファイル
├── README.md           # このファイル
├── requirements.txt    # Python依存関係リスト (Poetryから生成可能)
├── serverless.yml      # Serverless Framework設定ファイル
├── data/               # データファイル
│   ├── hoge.csv        # UUIDマッピング用CSVファイル
│   └── pdf/            # PDFファイル（sample-tanaka_re/配下）
├── output_jsons/       # メイン出力JSONファイル
├── output_jsons_worker/ # ワーカー出力JSONファイル
├── output_bbox/        # 可視化画像出力ディレクトリ（デフォルト）
├── localstack/
│   └── init-aws.sh     # LocalStack初期化スクリプト
├── src/                # ソースコードディレクトリ
│   ├── download.py     # S3からのファイルダウンロード
│   ├── llm.py          # LLMによる情報抽出（OpenAI）
│   ├── ocr.py          # OCR処理（Google Cloud Vision）
│   ├── processor.py    # データ後処理、bbox補正、クリップ形式変換
│   ├── queue.py        # SQS処理関連 (受信など)
│   ├── sqs_sender.py   # SQSへの送信処理
│   ├── prompts/        # LLM用プロンプト
│   │   ├── system_prompt.txt
│   │   └── user_prompt.txt
│   └── utils/          # ユーティリティ
│       ├── helper.py   # ヘルパー関数
│       └── logger.py   # ログ設定
├── tests/              # テストコードディレクトリ
│   ├── data/           # テスト用データ
│   └── unit/           # ユニットテスト
│       └── test_handler.py # ハンドラーのユニットテスト例
└── verification/       # 検証用スクリプト
    ├── extract_json_to_csv.py # JSON→CSV変換スクリプト
    └── run_local_tests.py     # 並列ローカルテスト実行スクリプト
```

## 使用方法

1.  設定済みのS3バケットにファイル（画像またはPDF）をアップロード
2.  S3イベント通知が入力SQSキューに送信される
3.  Lambda関数がSQSメッセージをトリガーに実行される
4.  Lambda内でダウンロード、OCR、LLM抽出、後処理（bbox補正、クリップ形式変換）が実行される
5.  最終的な処理結果（クリップ形式）が出力SQSキューに送信される

## ライセンス

プロプライエタリ - 無断での利用、複製、配布を禁じます。