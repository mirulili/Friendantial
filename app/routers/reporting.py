# app/routers/reporting.py

import logging
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from jinja2 import Environment

from app.core.strategies import get_strategy
from app.dependencies import get_jinja_env, get_llm_client, get_redis_connection
from app.llm.llm_service import generate_text_with_persona
from app.llm.prompt_builder import build_prompt
from app.routers.basic_analysis import get_analysis_service
from app.schemas.enums import PersonaEnum, StrategyEnum
from app.services.analysis import AnalysisService

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/summary", summary="최신 추천 결과 요약 보고서 생성")
async def create_summary_report(
    strategy: StrategyEnum = Query(
        StrategyEnum.DAY_TRADER, description="투자 전략 선택"
    ),
    persona: PersonaEnum = Query(PersonaEnum.FRIEND, description="에이전트 성격 선택"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    llm_client: Any = Depends(get_llm_client),
    jinja_env: Environment = Depends(get_jinja_env),
    redis_conn: redis.Redis = Depends(get_redis_connection),
):
    """
    현재 시점의 추천 종목들을 종합하여 시장 상황과 전략에 따른 요약 보고서를 생성합니다.
    """
    try:
        # 1. 데이터 가져오기
        reco_response = await analysis_service.get_recommendations(strategy=strategy)

        # 2. 전략별 관점 설정
        perspective_instruction = get_strategy(strategy.value).description

        # 3. 템플릿 렌더링
        user_prompt = build_prompt(
            jinja_env,
            "reports/summary_report.jinja2",
            as_of=reco_response.as_of,
            candidates=reco_response.candidates,
            perspective_instruction=perspective_instruction,
        )

        # 4. LLM 호출
        report = await generate_text_with_persona(
            persona_name=persona.value,
            user_prompt=user_prompt,
            llm_client=llm_client,
            redis_conn=redis_conn,
            jinja_env=jinja_env,
        )
        return {"report": report}

    except Exception as e:
        logging.error(f"LLM 리포트 생성 실패: {e}")
        raise HTTPException(
            status_code=500, detail=f"LLM 리포트 생성 중 오류가 발생했습니다: {e}"
        )


@router.get("/stock/{stock_code}", summary="개별 종목 심층 분석 보고서 생성")
async def create_stock_report(
    stock_code: str = Path(..., description="종목 코드 (예: 005930.KS)"),
    persona: PersonaEnum = Query(PersonaEnum.FRIEND, description="에이전트 성격 선택"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    llm_client: Any = Depends(get_llm_client),
    jinja_env: Environment = Depends(get_jinja_env),
    redis_conn: redis.Redis = Depends(get_redis_connection),
):
    """특정 종목 코드에 대한 심층 분석 보고서를 생성합니다."""
    try:
        analysis = await analysis_service.get_detailed_stock_analysis(stock_code)

        # 템플릿에 전달할 데이터 정리
        tech_analysis = analysis.get("technical_analysis") or {}
        price = tech_analysis.get("close", 0)

        user_prompt = build_prompt(
            jinja_env,
            "reports/stock_report.jinja2",
            stock_code=analysis["stock_code"],
            stock_name=analysis["stock_name"],
            price=price,
            tech_analysis=tech_analysis,
            news_analysis=analysis["news_analysis"],
        )

        report = await generate_text_with_persona(
            persona_name=persona.value,
            user_prompt=user_prompt,
            llm_client=llm_client,
            redis_conn=redis_conn,
            jinja_env=jinja_env,
        )
        return {"report": report}
    except Exception as e:
        logging.error(f"리포트 생성 실패 ({stock_code}): {e}")
        raise HTTPException(
            status_code=500, detail=f"리포트 생성 중 오류가 발생했습니다: {e}"
        )
