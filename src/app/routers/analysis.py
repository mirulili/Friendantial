from fastapi import APIRouter, HTTPException
import httpx

from app.config import NEWS_MAX
from app.models import FeatureConf
from app.sentiment import analyze_news_sentiment, fetch_news_titles
from app.market_data import fetch_ohlcv
from app.scoring import compute_features

# APIRouter 인스턴스 생성
router = APIRouter(
    prefix="/analysis",  # 이 라우터의 모든 엔드포인트에 /analysis 접두사 추가
    tags=["analysis"],   # API 문서에서 'analysis' 그룹으로 묶음
)

@router.get("/news-sentiment/{stock_name}", summary="특정 종목의 뉴스 감성 분석")
async def get_news_sentiment_for_stock(stock_name: str):
    """
    주어진 종목 이름(또는 코드)에 대한 최신 뉴스를 수집하고 감성 분석을 수행합니다.
    """
    async with httpx.AsyncClient() as client:
        titles = await fetch_news_titles(client, stock_name, limit=NEWS_MAX)

    if not titles:
        return {"stock_name": stock_name, "summary": "뉴스를 찾을 수 없습니다.", "details": []}

    analysis_result = analyze_news_sentiment(titles)
    return {"stock_name": stock_name, **analysis_result}

@router.get("/technical-indicator/{stock_code}", summary="특정 종목의 기술적 지표 분석")
async def get_technical_analysis(stock_code: str):
    """
    주어진 종목 코드에 대한 과거 데이터를 기반으로 기술적 지표(모멘텀 등)를 계산합니다.
    """
    conf = FeatureConf()
    data = fetch_ohlcv([stock_code], lookback_days=120)
    df = data.get(stock_code)

    if df is None or len(df) < conf.mom_long + 2:
        raise HTTPException(status_code=404, detail=f"'{stock_code}'에 대한 분석을 수행하기에 데이터가 충분하지 않습니다.")

    features_df = compute_features(df, conf)
    latest_features = features_df.iloc[-2]

    return {
        "code": stock_code,
        "momentum_short": latest_features.get(f"mom{conf.mom_short}"),
        "momentum_medium": latest_features.get(f"mom{conf.mom_med}"),
        "momentum_long": latest_features.get(f"mom{conf.mom_long}"),
        "last_close": latest_features.get("close"),
    }
