# Makefile for Friendantial Project

# --- Variables ---
APP_MODULE := app.main:app
HOST := 0.0.0.0
PORT := 8000
PIP := pip

# --- Docker Variables ---
IMAGE_NAME := friendantial-app
TAG := latest
CONTAINER_NAME := friendantial

.PHONY: all install run clean build up down logs shell docker-clean help lint format test

all: up

test:
	pytest

# ==============================================================================
# Local Development
# ==============================================================================

install:
	$(PIP) install -r requirements.txt --upgrade

run:
	# 환경 변수 로딩을 위해 python -m uvicorn 사용 권장
	python -m uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	# RAG 벡터 DB 데이터 정리 (필요시)
	rm -rf chromadb_data

# 코드 품질 관리 (flake8 설치 필요)
lint:
	flake8 .

# 코드 포매팅 (black 또는 isort 설치 필요)
format:
	isort .
	black .

# ==============================================================================
# Docker Operations
# ==============================================================================

build:
	docker build -t $(IMAGE_NAME):$(TAG) .

up:
	docker-compose up -d --build

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker exec -it friendantial-api /bin/bash 

docker-clean: down
	docker rmi $(IMAGE_NAME):$(TAG)
	docker system prune -f

# ==============================================================================
# Frontend Operations
# ==============================================================================

# 로컬에서 프론트엔드 실행
run-frontend:
	streamlit run app/frontend/main.py

# 프론트엔드 의존성 설치
install-frontend:
	$(PIP) install -r app/frontend/requirements.txt

# 전체 설치 (백엔드 + 프론트엔드)
install-all: install install-frontend

help:
	@echo "Available commands:"
	@echo "  make install       - Install backend dependencies"
	@echo "  make install-all   - Install backend and frontend dependencies"
	@echo "  make run           - Run local backend server"
	@echo "  make run-frontend  - Run local frontend app"
	@echo "  make all           - Build and run Docker containers"
	@echo "  make up            - Build and run Docker containers (detached)"
	@echo "  make down          - Stop and remove Docker containers"
	@echo "  make logs          - View Docker logs"
	@echo "  make test          - Run tests"
	@echo "  make lint          - Run linting"
	@echo "  make format        - Run formatting"
	@echo "  make clean         - Clean up cache files"