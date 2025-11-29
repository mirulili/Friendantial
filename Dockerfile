# syntax=docker/dockerfile:1.8

# --- Stage 1: Builder ---
# Install dependencies into a virtual environment
FROM python:3.11.9 AS builder
ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    VENV_PATH=/opt/venv

RUN python -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

COPY requirements.txt .
# pip install 시 uvicorn이 requirements.txt에 포함되어 있어야 함
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple -r requirements.txt && \
    find $VENV_PATH -name "__pycache__" -type d -exec rm -rf {} +

# --- Stage 2: Model Downloader ---
# Download the HuggingFace model to be included in the final image
FROM builder AS downloader
ARG SENTIMENT_MODEL_ID="snunlp/KR-FinBert-SC"
ENV HF_HOME=/opt/hf_home

RUN python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='${SENTIMENT_MODEL_ID}')" && \
    # Remove unnecessary cache files from the model download
    find $HF_HOME -name "*.pyc" -type f -delete && \
    find $HF_HOME -name "__pycache__" -type d -exec rm -rf {} +

# --- Stage 3: Final Image ---
FROM python:3.11.9-slim AS final

ARG DEBIAN_FRONTEND=noninteractive

COPY --from=downloader /opt/hf_home /opt/hf_home

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=ko_KR.UTF-8 \
    LC_ALL=ko_KR.UTF-8 \
    VENV_PATH=/opt/venv \
    HF_HOME=/opt/hf_home

# 가상환경의 bin을 PATH의 가장 앞에 둠 (python 입력 시 venv python 실행됨)
ENV PATH="$VENV_PATH/bin:$PATH"

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# [수정 1] venv를 복사할 때 소유권을 appuser로 변경 (권한 문제 방지)
COPY --from=builder --chown=appuser:appuser $VENV_PATH $VENV_PATH
COPY --from=downloader --chown=appuser:appuser $HF_HOME $HF_HOME

# App Setup
WORKDIR /app

COPY --chown=appuser:appuser app app

USER appuser
EXPOSE 8000

# [수정 2] "uvicorn" 명령어를 직접 쓰는 대신 "python -m uvicorn" 사용
# 이유: PATH에 의해 잡힌 venv 파이썬이 확실하게 자신의 site-packages를 참조하도록 강제함
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]