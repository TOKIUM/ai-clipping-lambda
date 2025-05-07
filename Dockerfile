FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

# # Poetryをインストール
# RUN pip install poetry

# # 依存関係ファイルをコピー
# COPY poetry.lock pyproject.toml ./

# # 本番環境の依存関係のみインストール
# # --no-root はプロジェクト自体をインストールしないオプション
# RUN poetry install --no-root

# requirements.txt を使って依存関係を ${LAMBDA_TASK_ROOT} にインストール
COPY requirements.txt ./
RUN pip install -r requirements.txt


# アプリケーションコードをコピー
COPY src/ ${LAMBDA_TASK_ROOT}/src
COPY handler.py ${LAMBDA_TASK_ROOT}/
COPY credential.json ${LAMBDA_TASK_ROOT}/

# Lambdaハンドラーを指定
CMD ["handler.process_document"]
