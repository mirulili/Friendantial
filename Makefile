# Makefile for Friendantial Project

# --- Variables ---
APP_MODULE := app.main:app
HOST := 0.0.0.0
PORT := 8000
PYTHON := python3
PIP := pip

# --- Docker Variables ---
IMAGE_NAME := friendantial-app
TAG := latest
CONTAINER_NAME := friendantial

.PHONY: all install run clean build up down logs shell docker-clean help

all: run

# ==============================================================================
# Local Development (로컬 개발용)
# ==============================================================================

# 의존성 패키지 설치
install:
	$(PIP) install -r requirements.txt --upgrade

# 로컬 서버 실행 (변경된 구조 반영: app.main:app)
run:
	uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

# 파이썬 캐시 파일 정리 (__pycache__, .pyc)
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# ==============================================================================
# Docker Operations (도커 운영용)
# ==============================================================================

# Docker 이미지 빌드
build:
	@echo "Building Docker image: $(IMAGE_NAME):$(TAG)..."
	docker build -t $(IMAGE_NAME):$(TAG) .

# Docker Compose 서비스 시작
up:
	@echo "Starting service..."
	docker-compose up -d

# 서비스 중지 및 제거
down:
	@echo "Stopping service..."
	docker-compose down

# 실행 중인 컨테이너 로그 확인
logs:
	@echo "Showing logs..."
	docker-compose logs -f

# 컨테이너 쉘 접속
shell:
	@echo "Accessing container shell..."
	docker exec -it $(CONTAINER_NAME) /bin/bash

# Docker 이미지 제거 (Clean Docker)
docker-clean: down
	@echo "Removing Docker image: $(IMAGE_NAME):$(TAG)..."
	docker rmi $(IMAGE_NAME):$(TAG)

# ==============================================================================
# Help
# ==============================================================================

help:
	@echo "Available commands:"
	@echo "  [Local]"
	@echo "  make install     - Install Python dependencies"
	@echo "  make run         - Run FastAPI server locally (uvicorn app.main:app)"
	@echo "  make clean       - Remove __pycache__ and .pyc files"
	@echo ""
	@echo "  [Docker]"
	@echo "  make build       - Build the Docker image"
	@echo "  make up          - Start the services in detached mode"
	@echo "  make down        - Stop and remove the services"
	@echo "  make logs        - Follow the logs of the services"
	@echo "  make shell       - Access the running app container's shell"
	@echo "  make docker-clean- Stop services and remove the Docker image"