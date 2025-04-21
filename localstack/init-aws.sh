#!/bin/bash

# LocalStackの準備ができるまで待機
echo "Waiting for LocalStack to be ready..."
while ! curl -s http://localstack:4566/health | grep -q '"s3": "running"'; do
    sleep 1
done
echo "LocalStack is ready!"

# AWS CLIの設定
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=ap-northeast-1

# LocalStack用のエンドポイントURL
ENDPOINT_URL="http://localhost:4566"

# S3バケットの作成
echo "Creating S3 bucket"
awslocal s3api create-bucket \
  --bucket ai-clipping-dev-bucket \
  --region ap-northeast-1 \
  --create-bucket-configuration LocationConstraint=ap-northeast-1

# 入力SQSキューの作成
echo "Creating input SQS queue"
awslocal sqs create-queue \
  --queue-name ai-clipping-dev-input-queue

# 出力SQSキューの作成
echo "Creating output SQS queue"
awslocal sqs create-queue \
  --queue-name ai-clipping-dev-output-queue

echo "AWS resources created successfully!"

# テスト用のファイルをS3にアップロード（test-image.jpgがあれば）
if [ -f /app/tests/data/test-image.jpg ]; then
  echo "Uploading test image to S3..."
  awslocal s3 cp /app/tests/data/test-image.jpg s3://ai-clipping-dev-bucket/
fi

# テスト用のSQSメッセージを送信
echo "Sending test message to SQS input queue..."
awslocal sqs send-message \
  --queue-url http://localhost:4566/000000000000/ai-clipping-dev-input-queue \
  --message-body '{"bucket": {"name": "ai-clipping-dev-bucket"}, "object": {"key": "test-image.jpg"}}'

echo "LocalStack initialization completed!"