# app/main.py

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import httpx
import jinja2
import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import REDIS_URL, TZ, logging_config
from app.db.database import engine, get_db
from app.db.db_models import Base
from app.llm.llm_clients import GeminiChatClient  # 사용할 LLM 클라이언트들 임포트
from app.llm.llm_clients import OpenAIChatClient
from app.llm.rag import rag_engine
from app.routers import backtest, basic_analysis, history, market, opinion, reporting
from app.services.analysis import AnalysisService
from app.services.sentiment import sentiment_lifespan

load_dotenv()
logging.basicConfig(**logging_config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 애플리케이션 시작 시 데이터베이스 테이블을 생성
    Base.metadata.create_all(bind=engine)

    # Redis 연결 풀을 생성하여 애플리케이션 상태에 저장
    app.state.redis = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    app.state.tz = TZ

    # 자주 사용되는 유틸리티 함수를 애플리케이션 상태에 등록
    from app.services.market_data import _fetch_stock_info

    app.state.lookup_stock_info = _fetch_stock_info

    # LLM 프롬프트에 사용될 Jinja2 템플릿 환경 설정
    app.state.jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader("app/llm/templates")
    )

    # 외부 API 호출을 위한 HTTP 클라이언트 생성
    app.state.http_client = httpx.AsyncClient()

    # 환경 변수(LLM_PROVIDER)에 따라 사용할 LLM 클라이언트를 동적으로 선택
    llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
    app.state.llm_client = None

    logging.info(f"선택된 LLM 공급자: {llm_provider}")

    if llm_provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            app.state.llm_client = OpenAIChatClient(api_key=api_key)
    elif llm_provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            app.state.llm_client = GeminiChatClient(api_key=api_key)

    if app.state.llm_client is None:
        logging.warning(
            "LLM 클라이언트가 초기화되지 않았습니다. LLM_PROVIDER 및 해당 API 키 환경 변수를 확인하세요."
        )

    # RAG 엔진을 애플리케이션 상태에 추가
    app.state.rag_engine = rag_engine

    # lifespan 동안 사용할 DB 세션 생성
    db_session_generator = get_db()
    db = next(db_session_generator)

    try:
        # AnalysisService를 애플리케이션 상태에 추가
        app.state.analysis_service = AnalysisService(
            sentiment_pipe=None,  # sentiment_lifespan에서 채워짐
            http_client=app.state.http_client,
            db=db,
            redis_conn=app.state.redis,
        )

        async with sentiment_lifespan(app):
            yield
    # 애플리케이션 종료 시 리소스 정리
    finally:
        next(db_session_generator, None)  # DB 세션 정리
        await app.state.redis.close()
        await app.state.http_client.aclose()
        if app.state.llm_client:
            await app.state.llm_client.close()

        app.state.llm_client = None  # 클라이언트 정리


app = FastAPI(
    title="Friendantial",
    version="1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(basic_analysis.router)
app.include_router(reporting.router)
app.include_router(opinion.router)
app.include_router(history.router)
app.include_router(backtest.router)


@app.get("/health")
def health():
    from datetime import datetime

    return {"ok": True, "ts": datetime.now(TZ).isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
