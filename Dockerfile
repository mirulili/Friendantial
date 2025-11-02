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
    pip install -r requirements.txt

# --- Stage 2: Model Downloader ---
# Download the HuggingFace model to be included in the final image
FROM python:3.10-slim as downloader
ENV HF_HOME=/opt/hf_home
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python -c "from app.sentiment import get_sentiment_pipeline; get_sentiment_pipeline()"

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
COPY --chown=appuser:appuser app/ ./app
COPY --chown=appuser:appuser main.py .

USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
