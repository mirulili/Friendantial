# Makefile for Friendantial Python project

# 가상 환경 디렉토리. Windows에서는 Scripts, 다른 OS에서는 bin
VENV_BIN := .venv/bin
ifeq ($(OS),Windows_NT)
    VENV_BIN := .venv/Scripts
endif

.PHONY: help install run clean format lint

help:
	@echo "Makefile for Friendantial"
	@echo ""
	@echo "Usage:"
	@echo "  make install    - 의존성 설치"
	@echo "  make run        - 개발 서버 실행 (uvicorn)"
	@echo "  make clean      - __pycache__ 및 .pytest_cache 삭제"
	@echo "  make format     - black과 isort로 코드 포맷팅"

install:
	@echo "Installing dependencies from requirements.txt..."
	@$(VENV_BIN)/pip install -r requirements.txt

run:
	@echo "Starting development server..."
	@$(VENV_BIN)/uvicorn main:app --host 0.0.0.0 --port 8000 --reload

clean:
	@echo "Cleaning up python cache files..."
	@find . -type f -name "*.py[co]" -delete
	@find . -type d -name "__pycache__" -delete