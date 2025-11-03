# syntax=docker/dockerfile:1.8

# --- Stage 1: Builder ---
# Install dependencies into a virtual environment
FROM python:3.10-slim as builder
ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    VENV_PATH=/opt/venv

RUN python -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt && \
    find $VENV_PATH -name "__pycache__" -type d -exec rm -rf {} +

# --- Stage 2: Model Downloader ---
# Download the HuggingFace model to be included in the final image
FROM builder as downloader
ARG SENTIMENT_MODEL_ID
ENV HF_HOME=/opt/hf_home

RUN python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='${SENTIMENT_MODEL_ID}')" && \
    # Remove unnecessary cache files from the model download
    find $HF_HOME -name "*.pyc" -type f -delete && \
    find $HF_HOME -name "__pycache__" -type d -exec rm -rf {} +

# --- Stage 3: Final Image ---
FROM python:3.10-slim
ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LANG=ko_KR.UTF-8 \
    LC_ALL=ko_KR.UTF-8 \
    VENV_PATH=/opt/venv \
    HF_HOME=/opt/hf_home

ENV PATH="$VENV_PATH/bin:$PATH"

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder $VENV_PATH $VENV_PATH
COPY --from=downloader $HF_HOME $HF_HOME

# App
WORKDIR /app
COPY --chown=appuser:appuser src/ .

USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
