import httpx
from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import get_http_client
from app.schemas.enums import PersonaEnum
from app.services.llm_service import generate_text_with_persona
from app.services.market_data import get_stock_name_from_code
from app.services.prompt_builder import build_prompt
from app.services.rag import rag_engine
from app.services.sentiment import fetch_news_titles

# APIRouter 인스턴스 생성
router = APIRouter(
    tags=["opinion"],  # API 문서에서 'recommendations' 그룹으로 묶음
)


@router.get("/opinion/{stock_code}", summary="종목 관련 질문 답변 (RAG)")
async def ask_about_stock(
    request: Request,
    stock_code: str,
    question: str = Query(..., description="질문 내용 (예: 왜 떨어져?)"),
    persona: PersonaEnum = Query(PersonaEnum.FRIEND, description="답변 페르소나 선택"),
    client: httpx.AsyncClient = Depends(get_http_client),
):
    """
    특정 종목의 최신 뉴스를 기반으로 사용자의 질문에 답변합니다 (RAG 적용).
    """
    # 1. 종목명 조회 (공통 함수 사용)
    stock_name = await get_stock_name_from_code(request, client, stock_code)
    news_titles = await fetch_news_titles(client, stock_name, limit=15)

    if not news_titles:
        return {"answer": "관련된 최신 뉴스를 찾지 못해서 답변하기 어려워 😢"}

    # 3. RAG: 벡터 DB에 저장 및 검색
    # (1) 지식 저장 (Ingestion)
    rag_engine.create_collection(stock_code, news_titles)

    # (2) 관련 문서 검색 (Retrieval)
    relevant_news = rag_engine.query(stock_code, question, n_results=5)

    # 4. 프롬프트 구성 (Context Stuffing)
    context_text = "\n".join([f"- {title}" for title in relevant_news])

    user_prompt = build_prompt(
        request,
        "rag_opinion.jinja2",
        stock_name=stock_name,
        stock_code=stock_code,
        context_text=context_text,
        question=question,
    )

    # 5. LLM 답변 생성
    answer = await generate_text_with_persona(
        request=request,
        persona_name=persona.value,
        user_prompt=user_prompt,
        llm_client=request.app.state.llm_client,
    )

    return {
        "stock": stock_name,
        "question": question,
        "context_used": relevant_news,  # 어떤 뉴스를 참고했는지 명시
        "answer": answer,
    }
