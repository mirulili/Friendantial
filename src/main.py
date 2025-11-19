from __future__ import annotations

import logging

from dotenv import load_dotenv
load_dotenv() # .env 파일에서 환경 변수를 로드합니다.

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from app.config import TZ, logging_config, REDIS_URL
from app.sentiment import sentiment_lifespan
from app.database import engine
import redis.asyncio as redis
from app.db_models import Base, RecommendationRun, RecommendedStock
from app.routers import analysis, market, history, recommend, reporting

logging.basicConfig(**logging_config)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 데이터베이스 테이블 생성
    Base.metadata.create_all(bind=engine)

    # Redis 연결 풀 생성
    app.state.redis = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)

    try:
        async with sentiment_lifespan(app):
            yield
    finally:
        await app.state.redis.close()

app = FastAPI(title="Friendantial (FDR + NewsRSS + Multilingual Sentiment)", version="0.4.0", lifespan=lifespan)

app.include_router(analysis.router)
app.include_router(recommend.router) # recommend.py가 core.py로 변경되었을 수 있으므로 수정
app.include_router(market.router)
app.include_router(reporting.router)
app.include_router(history.router)

@app.get("/health")
def health():
    from datetime import datetime
    return {"ok": True, "ts": datetime.now(TZ).isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
