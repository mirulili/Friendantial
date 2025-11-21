import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.models import FeatureConf
from app.routers.mcp import generate_text_with_persona
from app.database import get_db
from app.core import recommend
from app.market_data import fetch_ohlcv
from app.sentiment import analyze_news_sentiment, fetch_news_titles
from app.scoring import compute_features

router = APIRouter(
    prefix="/reporting",
    tags=["reporting"],
)


@router.get("/summary", summary="최신 추천 결과 요약 보고서 생성")
async def create_recommendation_report(
    request: Request,
    strategy: str = "default",
    persona: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """/recommendations 로직을 사용하여 추천 데이터를 생성하고, LLM을 통해 자연스러운 요약 보고서를 생성합니다."""
    try:
        # 1. 내부적으로 /recommendations 로직을 호출하여 추천 데이터를 가져옵니다.
        # API 파라미터로 받은 strategy를 recommend 함수에 전달합니다.
        reco_response = await recommend(request=request, strategy=strategy, db=db)
        
        # --- 페르소나 결정 로직: 쿼리 파라미터가 없으면 'friend'를 기본값으로 사용 ---
        persona_name = persona or "friend"

        # 2. LLM 프롬프트 생성을 위한 데이터 부분 구성
        stock_data_xml = ""
        for item in reco_response.candidates:
            news_xml = ""
            if item.news_sentiment and item.news_sentiment.details:
                news_items_xml = "".join(
                    f"<item label='{news_item.label}'>{news_item.title}</item>"
                    for news_item in item.news_sentiment.details
                )
                news_xml = f"<news>{news_items_xml}</news>"

            stock_data_xml += f"""
  <stock code='{item.code}' name='{item.name}'>
    <score>{item.score}</score>
    <reason>{item.reason}</reason>
    <momentum m5='{item.momentum.get('m5', 0):.2%}' m20='{item.momentum.get('m20', 0):.2%}' m60='{item.momentum.get('m60', 0):.2%}' />
    {news_xml}
  </stock>"""

        # 3. LLM에 전달할 지시사항(instructions) 부분 구성
        perspective_instruction = ""
        if strategy == "day_trader":
            perspective_instruction = "<perspective>단기 트레이더의 관점에서 분석합니다. 특히 '5일선 이탈', '거래량 급등'과 같은 단기 신호와 최신 뉴스의 영향을 중요하게 다룹니다.</perspective>"
        elif strategy == "long_term":
            perspective_instruction = "<perspective>장기 투자자의 관점에서 분석합니다. 장기 모멘텀(m60)과 '장기 추세 이탈' 같은 안정성을 중심으로 설명합니다.</perspective>"
        
        # 4. 최종 프롬프트 조합 (f-string 사용)
        user_prompt = f"""
<data>
<date>{reco_response.as_of}</date>
<stocks>{stock_data_xml}
</stocks>
</data>

<instructions>
  <goal>제공된 <data>를 분석하여, 각 종목의 투자 매력도를 설명하는 주간 추천 리포트를 생성합니다.</goal>
  <format>각 종목을 제목으로 하고, 핵심 내용을 1~2문단으로 요약하여 설명합니다. {'이모지를 사용하여 친근함을 더합니다.' if persona_name == 'friend' else ''}</format>
  {perspective_instruction}
</instructions>
"""

        # 캐싱 로직이 내장된 generate_text_with_persona 함수를 호출합니다.
        report = await generate_text_with_persona(
            request=request,
            persona_name=persona_name,
            user_prompt=user_prompt,
            llm_client=request.app.state.llm_client
        )
        
        return {"report": report}
    
    except Exception as e:
        logging.error(f"LLM 리포트 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=f"LLM 리포트 생성 중 오류가 발생했습니다: {e}")

@router.get("/stock/{stock_code}", summary="개별 종목 심층 분석 보고서 생성")
async def create_stock_report(
    request: Request,
    stock_code: str,
    persona: Optional[str] = None,
):
    """
    특정 종목 코드에 대한 심층 분석 보고서를 생성합니다.
    
    이 보고서는 다음을 포함합니다:
    - **기본 정보**: 종목 코드 및 이름
    - **모멘텀 분석**: 단기/중기/장기 모멘텀
    - **뉴스 감성 분석**: 최신 뉴스를 분석하여 종합적인 긍정/부정 뉘앙스 평가
    - **변동성 분석**: 최근 20일간의 주가 변동성
    """
    try:
        # --- 종목 정보 조회 (코드 -> 이름) ---
        stock_name = stock_code.split('.')[0] # 기본값 설정
        async with httpx.AsyncClient() as client:
            try:
                # app.state에 등록된 공통 유틸리티 함수를 사용하여 종목명을 가져옵니다.
                stock_info = await request.app.state.lookup_stock_info(client, request.app.state.redis, stock_code)
                if stock_info:
                    stock_name = stock_info.get("itmsNm", stock_name)
            except HTTPException as e:
                # 404와 같은 예상된 HTTP 오류는 그대로 전달
                logging.warning(f"종목 정보 조회 실패 ({stock_code}): {e.detail}. 코드로 계속 진행합니다.")
            except Exception as e:
                logging.error(f"종목 정보 조회 중 예상치 못한 오류 발생: {e}")

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
            news_titles = await fetch_news_titles(client, stock_name, limit=3)
        news_analysis = analyze_news_sentiment(request.app.state.sentiment_pipe, news_titles)

        # 3. LLM에 전달할 프롬프트 생성
        news_analysis_xml = "<summary>분석할 최신 뉴스가 없습니다.</summary>"
        if news_analysis.get("details"):
            news_items_xml = "".join(
                f"<item label='{news['label']}'>{news['title']}</item>"
                for news in news_analysis["details"]
            )
            news_analysis_xml = f"""
      <summary>{news_analysis['summary']}</summary>
      <items>{news_items_xml}</items>
"""

        if persona:
            persona_name = persona
        else:
            persona_name = os.getenv("LLM_PERSONA", "friend")

        user_prompt = f"""
<data>
  <stock code='{stock_code}' name='{stock_name}'>
    <technical_indicators>
      <momentum m5='{mom5:+.2%}' m20='{mom20:+.2%}' m60='{mom60:+.2%}' />
      <volatility std20='{volatility:.4f}' />
    </technical_indicators>
    <news_analysis>{news_analysis_xml}</news_analysis>
  </stock>
</data>

<instructions>
  <goal>제공된 <data>를 종합하여, 특정 종목에 대한 심층 분석 리포트를 생성합니다.</goal>
  <format>기술적 분석, 뉴스 분석, 그리고 최종 결론 순서로 문단을 나누어 설명합니다. {'친구에게 말하듯이 친근한 말투와 이모지를 사용합니다.' if persona_name == 'friend' else ''}</format>
  <perspective>모멘텀(상승/하락 추세), 변동성(안정성), 그리고 최신 뉴스가 주가에 미치는 영향을 종합적으로 연결하여 하나의 흥미로운 스토리로 풀어냅니다.</perspective>
</instructions>
"""

        # 4. LLM 호출하여 리포트 생성
        report = await generate_text_with_persona(
            request=request,
            persona_name=persona_name,
            user_prompt=user_prompt,
            llm_client=request.app.state.llm_client,
        )

        return {"report": report}

    except Exception as e:
        logging.error(f"리포트 생성 실패 ({stock_code}): {e}")
        raise HTTPException(status_code=500, detail=f"리포트 생성 중 오류가 발생했습니다: {e}")