import logging

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import NEWS_MAX
from app.engine.scoring import compute_features
from app.engine.presentation import generate_ma_comment
from app.schemas.models import FeatureConf
from app.services.market_data import fetch_ohlcv
from app.services.sentiment import analyze_news_sentiment, fetch_news_titles

# APIRouter 인스턴스 생성
router = APIRouter(
    prefix="/analysis",
    tags=["analysis"],  # API 문서에서 'analysis' 그룹으로 묶음
)


@router.get("/news-sentiment/{stock_name}", summary="특정 종목의 뉴스 감성 분석")
async def get_news_sentiment_for_stock(request: Request, stock_name: str):
    """
    주어진 종목 이름(또는 코드)에 대한 최신 뉴스를 수집하고 감성 분석을 수행합니다.
    """
    query_name = stock_name
    # 입력이 '005930.KS'와 같은 코드 형식인지 확인
    if stock_name.endswith((".KS", ".KQ")):
        async with httpx.AsyncClient() as client:
            try:
                # app.state에 등록된 공통 유틸리티 함수를 사용하여 종목명을 수집
                stock_info = await request.app.state.lookup_stock_info(
                    client, request.app.state.redis, stock_name
                )
                if stock_info:
                    query_name = stock_info.get("itmsNm", stock_name)
            except Exception as e:
                logging.warning(
                    f"종목 정보 조회 실패({stock_name}): {e}. 종목 코드로 검색을 시도합니다."
                )

    sentiment_pipe = request.app.state.sentiment_pipe
    async with httpx.AsyncClient() as client:
        titles = await fetch_news_titles(client, query_name, limit=NEWS_MAX)

    if not titles:
        return {
            "stock_name": stock_name,
            "summary": "뉴스를 찾을 수 없습니다.",
            "details": [],
        }

    analysis_result = analyze_news_sentiment(sentiment_pipe, titles)
    return {"stock_name": stock_name, **analysis_result}


@router.get("/technical-indicator/{stock_code}", summary="특정 종목의 기술적 지표 분석")
async def get_technical_analysis(request: Request, stock_code: str):
    """
    주어진 종목 코드에 대한 과거 데이터를 기반으로 기술적 지표(모멘텀 등)를 계산합니다.
    """
    conf = FeatureConf()
    data = await fetch_ohlcv(request, [stock_code], lookback_days=120)
    df = data.get(stock_code)

    if df is None or len(df) < conf.mom_long + 2:
        raise HTTPException(
            status_code=404,
            detail=f"'{stock_code}'에 대한 분석을 수행하기에 데이터가 충분하지 않습니다.",
        )

    features_df = compute_features(df, conf)
    latest_features = features_df.iloc[-2] # 전일 종가 기준
    # 이동평균선 값 추출
    price = latest.get("close", 0)
    ma5 = latest.get("ma5", 0)
    ma20 = latest.get("ma20", 0)
    ma60 = latest.get("ma60", 0)

    ma_comment = generate_ma_comment(price, ma5, ma20, ma60)
    return {
        "code": stock_code,
        "m5": round(latest_features.get(f"mom{conf.mom_short}", 0), 4),
        "m20": round(latest_features.get(f"mom{conf.mom_med}", 0), 4),
        "m60": round(latest_features.get(f"mom{conf.mom_long}", 0), 4),
        "close": int(latest_features.get("close", 0)),
        "rsi": round(latest_features.get("rsi", 50.0), 2),
        "summary": ma_comment
    }
