# AI Clipping Lambda

AWS Lambda を使用してS3から画像・PDFをダウンロードし、OCR処理、LLMによる情報抽出を行い、結果をSQSに送信するサーバレスアプリケーションです。

## 機能概要

1. S3イベント情報をSQSから受け取り、S3から画像/PDFファイルをダウンロード
2. Google Cloud Vision APIを使ってOCR処理（文字起こし）を実行
3. 抽出されたテキストをLLM（OpenAI API）に送信して必要な情報を抽出
4. 抽出された情報の後処理・正規化を実施
5. 処理結果を別のSQSキューに送信

## 環境構築

### 前提条件

- Node.js 16.x 以上
- Python 3.9
- AWS CLI（設定済み）
- Serverless Framework
- Docker（ローカルテスト用）

### インストール

```bash
# Serverless Frameworkのインストール（初回のみ）
npm install -g serverless

# 依存関係のインストール
npm install

# Pythonの仮想環境を作成
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Python依存関係のインストール
pip install -r requirements.txt
```

### 環境変数の設定

`.env` ファイルを作成し、必要な環境変数を設定します：

```
OPENAI_API_KEY=your_openai_api_key
```

Google Cloud Vision APIを使用するためには、認証情報を設定する必要があります：

```bash
# Google Cloud認証情報を環境変数として設定
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/google-credentials.json
```

## デプロイ

```bash
# 開発環境へのデプロイ
serverless deploy --stage dev

# 本番環境へのデプロイ
serverless deploy --stage prod
```

## ローカルでのテスト

```bash
# Dockerを使ったテスト
docker-compose up

# ユニットテストの実行
pytest tests/unit
```

## ディレクトリ構成

```
.
├── handler.py          # メインハンドラー
├── serverless.yml      # Serverless設定ファイル
├── requirements.txt    # Python依存関係
├── Dockerfile          # Dockerファイル
├── docker-compose.yml  # Docker Compose設定
└── src
    ├── download.py     # S3からのファイルダウンロード
    ├── ocr.py          # OCR処理（Google Cloud Vision）
    ├── llm.py          # LLMによる情報抽出（OpenAI）
    ├── processor.py    # データ後処理
    ├── queue.py        # SQSへの送信
    └── utils
        ├── helper.py   # ヘルパー関数
        └── logger.py   # ログ設定
```

## 使用方法

1. S3バケットにファイル（画像またはPDF）をアップロード
2. S3イベント通知が入力SQSキューに送信される
3. Lambdaがトリガーされ、処理を実行
4. 処理結果が出力SQSキューに送信される

## ライセンス

プロプライエタリ - 無断での利用、複製、配布を禁じます。