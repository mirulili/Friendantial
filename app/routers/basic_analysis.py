import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import NEWS_MAX
from app.dependencies import get_http_client
from app.engine.presentation import generate_ma_comment
from app.engine.scoring import compute_features
from app.engine.workflow import recommend
from app.schemas.models import FeatureConf, RecoResponse
from app.services.market_data import fetch_ohlcv, get_stock_name_from_code
from app.services.sentiment import analyze_news_sentiment, fetch_news_titles

# APIRouter 인스턴스 생성
router = APIRouter(
    prefix="/basic_analysis",
    tags=["basic_analysis"],  # API 문서에서 'analysis' 그룹으로 묶음
)


@router.get("/news-sentiment/{stock_name}", summary="특정 종목의 뉴스 감성 분석")
async def get_news_sentiment_for_stock(
    request: Request,
    stock_name: str,
    client: httpx.AsyncClient = Depends(get_http_client),
):
    """
    주어진 종목 이름(또는 코드)에 대한 최신 뉴스를 수집하고 감성 분석을 수행합니다.
    """
    # 종목 코드로 종목명을 조회하는 공통 함수 사용
    query_name = await get_stock_name_from_code(request, client, stock_name)
    sentiment_pipe = request.app.state.sentiment_pipe
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
async def get_technical_analysis(
    request: Request,
    stock_code: str,
    client: httpx.AsyncClient = Depends(get_http_client),
):
    """
    주어진 종목 코드에 대한 과거 데이터를 기반으로 기술적 지표(모멘텀 등)를 계산합니다.
    """
    conf = FeatureConf()
    data = await fetch_ohlcv(client, request, [stock_code], lookback_days=120)
    df = data.get(stock_code)

    if df is None or len(df) < conf.mom_long + 2:
        raise HTTPException(
            status_code=404,
            detail=f"'{stock_code}'에 대한 분석을 수행하기에 데이터가 충분하지 않습니다.",
        )

    features_df = compute_features(df, conf)
    latest_features = features_df.iloc[-2]  # 전일 종가 기준
    # 이동평균선 값 추출
    price = latest_features.get("close", 0)
    ma5 = latest_features.get("ma5", 0)
    ma20 = latest_features.get("ma20", 0)
    ma60 = latest_features.get("ma60", 0)

    ma_comment = generate_ma_comment(price, ma5, ma20, ma60)
    return {
        "code": stock_code,
        "m5": round(latest_features.get(f"mom{conf.mom_short}", 0), 4),
        "m20": round(latest_features.get(f"mom{conf.mom_med}", 0), 4),
        "m60": round(latest_features.get(f"mom{conf.mom_long}", 0), 4),
        "close": int(latest_features.get("close", 0)),
        "rsi": round(latest_features.get("rsi", 50.0), 2),
        "summary": ma_comment,
    }


@router.get("/recommendations", response_model=RecoResponse, summary="종합 주식 추천")
async def get_recommendations(
    # Depends(recommend)가 strategy 파라미터를 인식하도록 시그니처를 맞춤
    recommendations: RecoResponse = Depends(recommend),
):
    """
    모멘텀, 거래량, 뉴스 감성 점수 및 시장 상황을 종합하여 상위 주식 종목을 추천합니다.

    FastAPI의 의존성 주입 시스템을 통해 `core.recommend` 함수를 직접 호출하여 결과를 반환합니다.
    """
    return recommendations
