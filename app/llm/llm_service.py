# app/llm/llm_service.py

import os

import redis.asyncio as redis
from fastapi import HTTPException
from jinja2 import Environment

from app.llm.llm_clients import AbstractLLMClient
from app.utils.caching import cached_llm_generation


@cached_llm_generation(prefix="llm-prompt", ttl_days=1)
async def generate_text_with_persona(
    *,
    persona_name: str,
    user_prompt: str,
    llm_client: AbstractLLMClient,
    redis_conn: redis.Redis,
    jinja_env: Environment,
) -> str:
    """
    지정된 페르소나 템플릿과 사용자 프롬프트를 사용하여 LLM으로부터 텍스트를 생성합니다."""
    if not llm_client:
        raise HTTPException(
            status_code=503, detail="LLM 클라이언트가 초기화되지 않았습니다."
        )

    try:
        # system 폴더 아래의 {persona_name}.jinja2 템플릿을 사용
        template = jinja_env.get_template(f"system/{persona_name}.jinja2")
        system_prompt = template.render()
    except Exception:
        raise HTTPException(
            status_code=400, detail=f"알 수 없는 페르소나: {persona_name}"
        )

    model_name = os.getenv("LLM_MODEL_NAME", "gpt-4-turbo")

    generated_text = await llm_client.generate_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=model_name,
    )
    return generated_text
