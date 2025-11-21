import os
from fastapi import APIRouter, HTTPException
from app.prompts import FRIEND_PERSONA, ANALYST_PERSONA # 페르소나 프롬프트 임포트
from app.llm_clients import AbstractLLMClient # 새로 정의한 추상 클라이언트 임포트
from app.caching import cached_llm_generation # 캐싱 데코레이터 임포트
from fastapi import Request # Request 객체를 받기 위해 임포트

router = APIRouter(
    prefix="/mcp",
    tags=["mcp-features"],
)

@cached_llm_generation(prefix="llm-generated-text", ttl_days=1)
async def generate_text_with_persona(
    request: Request, *, persona_name: str, user_prompt: str, llm_client: AbstractLLMClient
) -> str:
    """
    지정된 페르소나와 사용자 프롬프트를 사용하여 LLM으로부터 텍스트를 생성합니다.
    사용할 모델은 LLM_MODEL_NAME 환경 변수에서 읽어옵니다.
    """
    persona_map = {
        "friend": FRIEND_PERSONA,
        "analyst": ANALYST_PERSONA,
    }
    system_prompt = persona_map.get(persona_name)
    if not system_prompt:
        raise HTTPException(status_code=400, detail=f"알 수 없는 페르소나: {persona_name}")

    # 환경 변수에서 모델 이름을 읽어옵니다. 없으면 'gpt-4-turbo'를 기본값으로 사용합니다.
    model_name = os.getenv("LLM_MODEL_NAME", "gpt-4-turbo")

    # 추상화된 클라이언트 인터페이스를 통해 텍스트 생성
    generated_text = await llm_client.generate_chat_completion(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        model=model_name,
    )
    return generated_text

@router.get("/prompts/friend")
def get_friend_prompt():
    return {"system_prompt": FRIEND_PERSONA}

@router.get("/prompts/analyst")
def get_analyst_prompt():
    return {"system_prompt": ANALYST_PERSONA}