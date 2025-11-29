# app/routers/reporting.py

import logging
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from jinja2 import Environment

from app.dependencies import (get_jinja_env, get_llm_client,
                              get_redis_connection)
from app.llm.llm_service import generate_text_with_persona
from app.llm.prompt_builder import build_prompt
from app.routers.basic_analysis import get_analysis_service
from app.schemas.enums import PersonaEnum, StrategyEnum
from app.services.analysis import AnalysisService

router = APIRouter(prefix="/reporting", tags=["reporting"])


@router.get("/summary", summary="최신 추천 결과 요약 보고서 생성")
async def create_summary_report(
    request: Request,
    strategy: StrategyEnum = Query(StrategyEnum.DAY_TRADER, description="전략 선택"),
    persona: PersonaEnum = Query(PersonaEnum.FRIEND, description="답변 페르소나 선택"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    llm_client: Any = Depends(get_llm_client),
    jinja_env: Environment = Depends(get_jinja_env),
    redis_conn: redis.Redis = Depends(get_redis_connection),
):
    try:
        # 1. 데이터 가져오기
        reco_response = await analysis_service.get_recommendations(strategy=strategy)

        # 2. 전략별 관점 설정
        perspective_instruction = ""
        if strategy == StrategyEnum.DAY_TRADER:
            perspective_instruction = "<perspective>단기 트레이더 관점: '5일선 이탈', '거래량 급등' 등 단기 신호와 최신 뉴스 위주 분석.</perspective>"
        elif strategy == StrategyEnum.LONG_TERM:
            perspective_instruction = "<perspective>장기 투자자 관점: 장기 모멘텀(m60), '장기 추세' 및 펀더멘털 안정성 위주 분석.</perspective>"

        format_instruction = (
            "이모지를 사용하여 친근함을 더합니다."
            if persona == PersonaEnum.FRIEND
            else ""
        )

        # 3. 템플릿 렌더링 (데이터 객체를 그대로 전달!)
        # 주의: 템플릿 내부 변수명(candidates)과 전달하는 키 이름을 맞춰야 합니다.
        user_prompt = build_prompt(
            jinja_env,
            "reports/summary_report.jinja2",  # ✅ reports 폴더 명시
            as_of=reco_response.as_of,
            candidates=reco_response.candidates,  # ✅ 리스트 객체 전달
            format_instruction=format_instruction,
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
    stock_code: str,
    request: Request,
    persona: PersonaEnum = Query(PersonaEnum.FRIEND, description="답변 페르소나 선택"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    llm_client: Any = Depends(get_llm_client),
    jinja_env: Environment = Depends(get_jinja_env),
    redis_conn: redis.Redis = Depends(get_redis_connection),
):
    """특정 종목 코드에 대한 심층 분석 보고서를 생성합니다."""
    try:
        analysis = await analysis_service.get_detailed_stock_analysis(stock_code)

        format_instruction = (
            "친구에게 말하듯이 친근한 말투와 이모지를 사용합니다."
            if persona == PersonaEnum.FRIEND
            else ""
        )

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
            format_instruction=format_instruction,
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
