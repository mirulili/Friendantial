import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException

from app.models import FeatureConf
from app.core import recommend
from app.market_data import fetch_ohlcv
from app.sentiment import analyze_news_sentiment, fetch_news_titles
from app.scoring import compute_features

router = APIRouter(
    prefix="/reporting",
    tags=["reporting"],
)

@router.get("/summary", summary="최신 추천 결과 요약 보고서 생성")
async def create_recommendation_report(request: Request):
    """/recommendations 엔드포인트를 호출하여 최신 추천 결과를 가져오고, 사람이 읽기 좋은 형태의 요약 보고서를 생성합니다."""
    # 내부적으로 /recommendations 엔드포인트를 호출하여 최신 추천 결과를 가져옵니다.
    response = await recommend(request)
    
    report = f"# 주간 추천 종목 요약 ({response.as_of})\n\n"
    report += "## 📈 추천 종목 TOP 5\n"
    for item in response.candidates:
        report += f"- **{item.name} ({item.code})**\n"
        report += f"  - 추천 점수: {item.score:.2f}\n"
        report += f"  - 분석 근거: {item.reason}\n"
        if item.news_sentiment and item.news_sentiment.details:
            report += f"  - 주요 뉴스: {item.news_sentiment.details[0].title}\n"
    return {"report": report}

@router.get("/stock/{stock_code}", summary="개별 종목 심층 분석 보고서 생성")
async def create_stock_report(request: Request, stock_code: str):
    """
    특정 종목 코드에 대한 심층 분석 보고서를 생성합니다.
    
    이 보고서는 다음을 포함합니다:
    - **기본 정보**: 종목 코드 및 이름
    - **모멘텀 분석**: 단기/중기/장기 모멘텀
    - **뉴스 감성 분석**: 최신 뉴스를 분석하여 종합적인 긍정/부정 뉘앙스 평가
    - **변동성 분석**: 최근 20일간의 주가 변동성
    """
    try:
        # 1. 데이터 수집
        ohlcv_data = await fetch_ohlcv(request, [stock_code], lookback_days=120)
        df = ohlcv_data.get(stock_code)
        if df is None or df.empty:
            raise HTTPException(status_code=404, detail=f"{stock_code}에 대한 시세 데이터를 찾을 수 없습니다.")

        # 2. 분석 수행
        conf = FeatureConf()
        features = compute_features(df, conf=conf)
        
        mom5 = features['mom5'].iloc[-2]
        mom20 = features['mom20'].iloc[-2]
        mom60 = features['mom60'].iloc[-2]
        volatility = features["ret1"].rolling(20).std().iloc[-2]

        async with httpx.AsyncClient() as client:
            news_titles = await fetch_news_titles(client, stock_code.split('.')[0], limit=3)
        news_analysis = analyze_news_sentiment(request.app.state.sentiment_pipe, news_titles)

        # 3. 보고서 생성
        report = f"# {stock_code} 심층 분석 보고서\n\n"
        report += "## 펀더멘털 요약\n"
        report += f"- **단기 모멘텀 (5일)**: {mom5:+.2%}\n"
        report += f"- **중기 모멘텀 (20일)**: {mom20:+.2%}\n"
        report += f"- **장기 모멘텀 (60일)**: {mom60:+.2%}\n"
        report += f"- **변동성 (20일)**: {volatility:.4f}\n\n"
        
        report += "## 뉴스 및 여론 분석\n"
        if news_analysis.get("details"):
            report += f"**종합 평가**: {news_analysis['summary']}\n\n"
            for news in news_analysis["details"]:
                report += f"- **[{news['label']}]** {news['title']} (신뢰도: {news['confidence']:.0%})\n"
        else:
            report += "분석할 최신 뉴스를 찾을 수 없습니다.\n"
            
        return {"report": report}

    except Exception as e:
        logging.error(f"리포트 생성 실패 ({stock_code}): {e}")
        raise HTTPException(status_code=500, detail=f"리포트 생성 중 오류가 발생했습니다: {e}")