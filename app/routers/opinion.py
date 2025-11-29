# app/routers/opinion/opinion.py

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, Depends, Query, Request
from jinja2 import Environment

from app.dependencies import (get_http_client, get_jinja_env,
                              get_redis_connection, get_llm_client)
from app.llm.llm_service import generate_text_with_persona
from app.llm.prompt_builder import build_prompt
from app.schemas.enums import PersonaEnum
from app.services.analysis import AnalysisService

# APIRouter 인스턴스 생성
router = APIRouter(
    tags=["opinion"],
)


def get_analysis_service(
    request: Request,
) -> AnalysisService:
    """FastAPI 애플리케이션 상태에서 AnalysisService를 가져옵니다."""
    return request.app.state.analysis_service


@router.get("/opinion/{stock_code}", summary="종목 관련 질문 답변 (RAG)")
async def ask_about_stock(
    request: Request,
    stock_code: str,
    question: str = Query(..., description="질문 내용 (예: 왜 떨어져?)"),
    persona: PersonaEnum = Query(PersonaEnum.FRIEND, description="답변 페르소나 선택"),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    client: httpx.AsyncClient = Depends(get_http_client),
    jinja_env: Environment = Depends(get_jinja_env),
    redis_conn: redis.Redis = Depends(get_redis_connection),
    llm_client: httpx.AsyncClient = Depends(get_llm_client),
):
    """
    특정 종목의 최신 뉴스를 기반으로 사용자의 질문에 답변합니다 (RAG 적용).
    """
    # 1. 기본 분석 데이터 가져오기 (기술적 분석 + 뉴스)
    analysis_result = await analysis_service.get_detailed_stock_analysis(stock_code)
    stock_name = analysis_result["stock_name"]
    tech_analysis = analysis_result["technical_analysis"]
    news_titles = [item['title'] for item in analysis_result["news_analysis"]["details"]]

    # 2. 뉴스 데이터가 없으면 간단한 답변 반환
    if not news_titles:
        return {"answer": "관련된 최신 뉴스를 찾지 못해서 답변하기 어려워 😢"}

    # 3. RAG: 벡터 DB에 저장 및 검색
    rag_engine = request.app.state.rag_engine
    # (1) 지식 저장 (Ingestion)
    rag_engine.create_collection(stock_code, news_titles)

    # (2) 관련 문서 검색 (Retrieval)
    relevant_news = rag_engine.query(stock_code, question, n_results=5)  # type: ignore

    # 4. 프롬프트 구성
    context_text = "\n".join([f"- {title}" for title in relevant_news])

    user_prompt = build_prompt(
        jinja_env,
        "rag/rag_opinion.jinja2",  # ✅ 경로 수정 (../ 제거)
        stock_name=stock_name,
        stock_code=stock_code,
        context_text=context_text,
        tech_analysis=tech_analysis,
        question=question,
    )

    # 5. LLM 답변 생성
    answer = await generate_text_with_persona(
        persona_name=persona.value,
        user_prompt=user_prompt,
        llm_client=llm_client,
        redis_conn=redis_conn,
        jinja_env=jinja_env,
    )

    return {
        "stock": stock_name,  # type: ignore
        "question": question,
        "context_used": relevant_news,  # 어떤 뉴스를 참고했는지 명시
        "answer": answer,
    }
