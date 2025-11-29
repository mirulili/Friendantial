# app/routers/basic_analysis.py

from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.dependencies import (get_db, get_http_client, get_redis_connection,
                              get_sentiment_analyzer)
from app.schemas.enums import StrategyEnum
from app.schemas.models import RecoResponse
from app.services.analysis import AnalysisService

# APIRouter 인스턴스 생성
router = APIRouter(
    prefix="/basic_analysis",
    tags=["basic_analysis"],
)


# 서비스 의존성 주입
def get_analysis_service(
    sentiment_pipe: Any = Depends(get_sentiment_analyzer),
    client: httpx.AsyncClient = Depends(get_http_client),
    db: Session = Depends(get_db),
    redis_conn: redis.Redis = Depends(get_redis_connection),
):
    return AnalysisService(
        sentiment_pipe=sentiment_pipe,
        http_client=client,
        db=db,
        redis_conn=redis_conn,
    )


@router.get("/news-sentiment/{stock_identifier}", summary="특정 종목의 뉴스 감성 분석")
async def get_news_sentiment_for_stock(
    stock_identifier: str = Path(
        ..., description="종목 이름 또는 코드 (예: 삼성전자 또는 005930.KS)"
    ),
    analysis_service: AnalysisService = Depends(get_analysis_service),
):
    """
    주어진 종목 이름(또는 코드)에 대한 최신 뉴스를 수집하고 감성 분석을 수행합니다.
    """
    try:
        analysis_result = await analysis_service.get_detailed_stock_analysis(
            stock_identifier
        )
        return {
            "stock_identifier": stock_identifier,
            **analysis_result["news_analysis"],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/technical-indicator/{stock_code}", summary="특정 종목의 기술적 지표")
async def get_technical_analysis(
    stock_code: str = Path(..., description="종목 코드 (예: 005930.KS)"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
):
    """
    주어진 종목 코드에 대한 과거 데이터를 기반으로 기술적 지표(모멘텀 등)를 계산합니다.
    """
    try:
        analysis_result = await analysis_service.get_detailed_stock_analysis(stock_code)
        return {"code": stock_code, **analysis_result["technical_analysis"]}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/recommendations", response_model=RecoResponse, summary="종합 주식 추천")
async def get_recommendations(
    strategy: StrategyEnum = Query(
        StrategyEnum.DAY_TRADER, description="투자 전략 선택"
    ),
    analysis_service: AnalysisService = Depends(get_analysis_service),
):
    """
    모멘텀, 거래량, 뉴스 감성 점수 및 시장 상황을 종합하여 상위 주식 종목을 추천합니다.
    """
    recommendations = await analysis_service.get_recommendations(strategy=strategy)
    return recommendations
