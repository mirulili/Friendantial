from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from app.config import TZ, logging_config
from app.models import RecoResponse
from app.sentiment import get_sentiment_pipeline
from app.core import recommend

logging.basicConfig(**logging_config)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initializing sentiment model...")
    get_sentiment_pipeline()
    yield

app = FastAPI(title="Friendantial (FDR + NewsRSS + Multilingual Sentiment)", version="0.4.0", lifespan=lifespan)

@app.get("/health")
def health():
    from datetime import datetime
    return {"ok": True, "ts": datetime.now(TZ).isoformat()}

@app.get("/recommendations", response_model=RecoResponse)
async def get_recommendations(
    as_of: Optional[str] = Query(None), n: int = Query(5, ge=1, le=10), with_news: bool = Query(True)
):
    return await recommend(as_of=as_of, n=n, with_news=with_news)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
