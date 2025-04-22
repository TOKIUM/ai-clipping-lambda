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
# スクリプトの実行例
python local_test.py path/to/your/image_or_pdf.ext

# 結果をファイルに保存する場合
python local_test.py path/to/your/image_or_pdf.ext -o output.json

# 詳細なログを表示する場合
python local_test.py path/to/your/image_or_pdf.ext -v
```

### ユニットテストの実行

```bash
pytest tests/unit
```

## ディレクトリ構成

```
.
├── credential.json     # Google Cloud認証情報ファイル (配置が必要)
├── docker-compose.yml  # Docker Compose設定 (LocalStack用)
├── Dockerfile          # Lambda実行環境用Dockerファイル
├── handler.py          # Lambdaエントリーポイント
├── local_test.py       # ローカルテスト用スクリプト
├── poetry.lock         # Poetryロックファイル
├── pyproject.toml      # Poetry設定ファイル
├── README.md           # このファイル
├── requirements.txt    # Python依存関係リスト (Poetryから生成可能)
├── serverless.yml      # Serverless Framework設定ファイル
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
└── tests/              # テストコードディレクトリ
    ├── data/           # テスト用データ
    └── unit/           # ユニットテスト
        └── test_handler.py # ハンドラーのユニットテスト例
```

## 使用方法

1.  設定済みのS3バケットにファイル（画像またはPDF）をアップロード
2.  S3イベント通知が入力SQSキューに送信される
3.  Lambda関数がSQSメッセージをトリガーに実行される
4.  Lambda内でダウンロード、OCR、LLM抽出、後処理（bbox補正、クリップ形式変換）が実行される
5.  最終的な処理結果（クリップ形式）が出力SQSキューに送信される

## ライセンス

プロプライエタリ - 無断での利用、複製、配布を禁じます。