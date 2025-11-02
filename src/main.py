from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from app.config import TZ, logging_config
from app.sentiment import get_sentiment_pipeline
from app.routers import analysis, recommend, market, reporting

logging.basicConfig(**logging_config)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initializing sentiment model...")
    get_sentiment_pipeline()
    yield

app = FastAPI(title="Friendantial (FDR + NewsRSS + Multilingual Sentiment)", version="0.4.0", lifespan=lifespan)

app.include_router(analysis.router)
app.include_router(recommend.router)
app.include_router(market.router)
app.include_router(reporting.router)

@app.get("/health")
def health():
    from datetime import datetime
    return {"ok": True, "ts": datetime.now(TZ).isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
