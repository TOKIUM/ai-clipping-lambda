FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

# Poetryをインストール
RUN pip install poetry

# 依存関係ファイルをコピー
COPY poetry.lock pyproject.toml ./

# 本番環境の依存関係のみインストール
# --no-root はプロジェクト自体をインストールしないオプション
RUN poetry install --no-root

# アプリケーションコードをコピー
COPY src/ ${LAMBDA_TASK_ROOT}/src
COPY handler.py ${LAMBDA_TASK_ROOT}/
COPY credential.json ${LAMBDA_TASK_ROOT}/

# 環境変数の設定 (serverless.yml で設定されるものが優先される場合が多い)
# ENV ENVIRONMENT=development
# ENV LOG_LEVEL=INFO

# Lambdaハンドラーを指定
CMD ["handler.process_document"]
