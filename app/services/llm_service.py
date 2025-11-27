import os

from fastapi import HTTPException, Request

from app.llm.llm_clients import AbstractLLMClient
from app.llm.prompts import ANALYST_PERSONA, FRIEND_PERSONA
from app.utils.caching import cached_llm_generation


def get_persona_details(persona: str | None) -> tuple[str, str]:
    """
    페르소나 이름을 기반으로 실제 페르소나 이름과 프롬프트에 사용할 지시사항을 반환합니다.
    """
    persona_name = persona or "friend"
    format_instruction = ""

    if persona_name == "friend":
        format_instruction = "친구에게 말하듯이 친근한 말투와 이모지를 사용합니다."
    elif persona_name == "analyst":
        format_instruction = (
            "객관적인 데이터와 사실에 기반하여 전문가적인 톤으로 분석합니다."
        )

    return persona_name, format_instruction


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
