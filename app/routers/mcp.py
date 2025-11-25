import os

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from app.llm.llm_clients import AbstractLLMClient  # 추상 클라이언트 임포트
from app.llm.prompts import ANALYST_PERSONA, FRIEND_PERSONA  # 페르소나 프롬프트 임포트
from app.services.rag import rag_engine
from app.services.sentiment import fetch_news_titles
from app.utils.caching import cached_llm_generation  # 캐싱 데코레이터 임포트

router = APIRouter(
    prefix="/mcp",
    tags=["mcp-features"],
)


@cached_llm_generation(prefix="llm-generated-text", ttl_days=1)
async def generate_text_with_persona(
    request: Request,
    *,
    persona_name: str,
    user_prompt: str,
    llm_client: AbstractLLMClient,
) -> str:
    """
    지정된 페르소나와 사용자 프롬프트를 사용하여 LLM으로부터 텍스트를 생성합니다.
    사용할 모델은 LLM_MODEL_NAME 환경 변수에서 읽어옵니다.
    """
    llm_client: AbstractLLMClient = request.app.state.llm_client
    if not llm_client:
        raise HTTPException(
            status_code=503, detail="LLM 클라이언트가 초기화되지 않았습니다."
        )

    persona_map = {
        "friend": FRIEND_PERSONA,
        "analyst": ANALYST_PERSONA,
    }
    system_prompt = persona_map.get(persona_name)
    if not system_prompt:
        raise HTTPException(
            status_code=400, detail=f"알 수 없는 페르소나: {persona_name}"
        )

    # 환경 변수에서 모델 이름을 읽어옴
    # 없으면 'gpt-4-turbo'를 기본값으로 사용
    model_name = os.getenv("LLM_MODEL_NAME", "gpt-4-turbo")

    # 추상화된 클라이언트 인터페이스를 통해 텍스트 생성
    generated_text = await llm_client.generate_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=model_name,
    )
    return generated_text


@router.get("/prompts/friend")
def get_friend_prompt():
    return {"system_prompt": FRIEND_PERSONA}


@router.get("/prompts/analyst")
def get_analyst_prompt():
    return {"system_prompt": ANALYST_PERSONA}


@router.get("/ask/{stock_code}", summary="종목 관련 질문 답변 (RAG)")
async def ask_about_stock(
    request: Request,
    stock_code: str,
    question: str = Query(..., description="질문 내용 (예: 왜 떨어져?)"),
    persona: str = Query("friend", description="friend 또는 analyst"),
):
    """
    특정 종목의 최신 뉴스를 기반으로 사용자의 질문에 답변합니다 (RAG 적용).
    """
    # 1. 종목명 조회
    stock_name = stock_code
    async with httpx.AsyncClient() as client:
        try:
            # app.state에 등록된 공통 유틸리티 사용 (main.py에서 등록됨)
            if hasattr(request.app.state, "lookup_stock_info"):
                stock_info = await request.app.state.lookup_stock_info(
                    client, request.app.state.redis, stock_code
                )
                if stock_info:
                    stock_name = stock_info.get("itmsNm", stock_name)
        except Exception:
            pass  # 조회 실패 시 코드명 그대로 사용

    # 2. 최신 뉴스 수집 (지식 베이스 구축)
    # RAG를 위해 평소보다 많은 뉴스를 수집 (예: 15개)
    async with httpx.AsyncClient() as client:
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

    persona_prompt = FRIEND_PERSONA if persona == "friend" else ANALYST_PERSONA

    system_msg = f"""
    {persona_prompt}
    
    [지시사항]
    사용자는 '{stock_name}({stock_code})'에 대해 질문했습니다.
    아래 제공된 '최신 뉴스' 내용을 근거로 답변해주세요.
    뉴스에 없는 내용은 "뉴스에서 확인할 수 없다"고 솔직하게 말해주세요.
    """

    user_msg = f"""
    [최신 뉴스]
    {context_text}
    
    [질문]
    {question}
    """

    # 5. LLM 답변 생성
    llm_client: AbstractLLMClient = request.app.state.llm_client
    model_name = os.getenv("LLM_MODEL_NAME", "gpt-4-turbo")

    answer = await llm_client.generate_chat_completion(
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        model=model_name,
    )

    return {
        "stock": stock_name,
        "question": question,
        "context_used": relevant_news,  # 어떤 뉴스를 참고했는지 명시
        "answer": answer,
    }
