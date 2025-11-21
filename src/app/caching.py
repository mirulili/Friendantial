import hashlib
import logging
from functools import wraps
from datetime import timedelta, datetime

from app.config import TZ # 시간대 정보를 config에서 직접 가져옵니다.

def cached_llm_generation(prefix: str, ttl_days: int = 1):
    """
    LLM 생성 함수의 결과를 캐싱하는 데코레이터입니다.

    :param prefix: 캐시 키를 위한 접두사 (예: 'llm-summary-report')
    :param ttl_days: 캐시 유효 기간 (일 단위)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            # 데코레이터가 적용된 함수가 'persona_name'과 'user_prompt'를 키워드 인자로 받을 것으로 가정합니다.
            persona_name = kwargs.get("persona_name", "default")
            user_prompt = kwargs.get("user_prompt", "")

            redis_conn = request.app.state.redis
            today_str = datetime.now(TZ).date().isoformat()

            # 캐시 키 생성 (날짜 + 페르소나 + 프롬프트 내용)
            prompt_hash = hashlib.md5(user_prompt.encode()).hexdigest()
            cache_key = f"{prefix}:{today_str}:{persona_name}:{prompt_hash}"

            # 1. 캐시 확인
            cached_result = await redis_conn.get(cache_key)
            if cached_result:
                logging.info(f"LLM 응답 캐시 히트: {cache_key}")
                return cached_result

            # 2. 캐시 미스 시, 원본 함수(LLM 생성) 호출
            logging.info(f"LLM 응답 캐시 미스: {cache_key}")
            result = await func(request, *args, **kwargs)

            # 3. 결과를 캐시에 저장
            await redis_conn.set(cache_key, result, ex=timedelta(days=ttl_days))
            return result
        return wrapper
    return decorator
