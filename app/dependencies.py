# app/dependencies.py

from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import Request
from jinja2 import Environment

from .db.database import SessionLocal


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """
    FastAPI 애플리케이션 상태(app.state)에서 관리되는 `httpx.AsyncClient`를 주입합니다.
    """
    return request.app.state.http_client


def get_db() -> SessionLocal:
    """
    요청마다 새로운 DB 세션을 생성하고, 요청이 끝나면 세션을 닫는 의존성입니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_redis_connection(request: Request) -> redis.Redis:
    """FastAPI 애플리케이션 상태에서 Redis 연결을 가져옵니다."""
    return request.app.state.redis


def get_sentiment_analyzer(request: Request) -> Any:
    """FastAPI 애플리케이션 상태에서 감성 분석 파이프라인을 가져옵니다."""
    return request.app.state.sentiment_pipe


def get_llm_client(request: Request) -> Any:
    """FastAPI 애플리케이션 상태에서 LLM 클라이언트를 가져옵니다."""
    return request.app.state.llm_client


def get_jinja_env(request: Request) -> Environment:
    """FastAPI 애플리케이션 상태에서 Jinja2 환경을 가져옵니다."""
    return request.app.state.jinja_env
