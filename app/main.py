from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

import redis.asyncio as redis
from fastapi import FastAPI

from app.config import REDIS_URL, TZ, logging_config
from app.db.database import engine
from app.db.db_models import Base
from app.llm.llm_clients import GeminiChatClient  # 사용할 LLM 클라이언트들 임포트
from app.llm.llm_clients import OpenAIChatClient
from app.routers import (analysis, backtest, history, market, mcp, recommend,
                         reporting)
from app.services.sentiment import sentiment_lifespan

logging.basicConfig(**logging_config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 데이터베이스 테이블 생성
    Base.metadata.create_all(bind=engine)

    # Redis 연결 풀 생성
    app.state.redis = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

    # 공통 유틸리티 함수 등록
    from app.services.market_data import _fetch_stock_info

    app.state.lookup_stock_info = _fetch_stock_info

    # 환경 변수에 따라 LLM 클라이언트를 동적으로 선택
    llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    app.state.llm_client = None

    logging.info(f"선택된 LLM 제공자: {llm_provider}")

    if llm_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            app.state.llm_client = OpenAIChatClient(api_key=api_key)
    elif llm_provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")  # Gemini를 위한 별도 API 키
        if api_key:
            app.state.llm_client = GeminiChatClient(api_key=api_key)

    if app.state.llm_client is None:
        logging.warning(
            "LLM 클라이언트가 초기화되지 않았습니다. LLM_PROVIDER 및 해당 API 키 환경 변수를 확인하세요."
        )

    try:
        async with sentiment_lifespan(app):
            yield
    finally:
        await app.state.redis.close()
        app.state.llm_client = None  # 클라이언트 정리


app = FastAPI(
    title="Friendantial (FDR + NewsRSS + Multilingual Sentiment)",
    version="0.4.0",
    lifespan=lifespan,
)

app.include_router(analysis.router)
app.include_router(recommend.router)
app.include_router(market.router)
app.include_router(reporting.router)
app.include_router(history.router)
app.include_router(mcp.router)
app.include_router(backtest.router)


@app.get("/health")
def health():
    from datetime import datetime

    return {"ok": True, "ts": datetime.now(TZ).isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
