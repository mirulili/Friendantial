# app/utils/caching.py

import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps

import redis.asyncio as redis

from app.config import TZ


def _find_redis_conn(*args, **kwargs) -> redis.Redis:
    """Декораторға берілген аргументтерден redis.Redis данасын табады."""
    if "redis_conn" in kwargs:
        return kwargs["redis_conn"]
    for arg in args:
        if isinstance(arg, redis.Redis):
            return arg
    raise TypeError(
        "Redis connection not found in decorated function's arguments."
        "Please provide 'redis_conn' as a keyword argument."
    )


def cached_llm_generation(prefix: str, ttl_days: int = 1):
    """
    LLM 생성 함수의 결과를 캐싱하는 데코레이터입니다.
    이제 request 객체 대신 redis_conn을 직접 인자로 받습니다.

    :param prefix: 캐시 키를 위한 접두사 (예: 'llm-summary-report')
    :param ttl_days: 캐시 유효 기간 (일 단위)
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            persona_name = kwargs.get("persona_name", "default")
            user_prompt = kwargs.get("user_prompt", "")

            redis_conn = _find_redis_conn(*args, **kwargs)
            today_str = datetime.now(TZ).date().isoformat()

            prompt_hash = hashlib.md5(user_prompt.encode()).hexdigest()
            cache_key = f"{prefix}:{today_str}:{persona_name}:{prompt_hash}"

            # 1. 캐시 확인
            cached_result = await redis_conn.get(cache_key)
            if cached_result:
                logging.info(f"LLM 응답 캐시 히트: {cache_key}")
                return cached_result

            # 2. 캐시 미스 시, 원본 함수(LLM 생성) 호출
            logging.info(f"LLM 응답 캐시 미스: {cache_key}")
            result = await func(*args, **kwargs)

            # 3. 결과를 캐시에 저장
            await redis_conn.set(cache_key, result, ex=timedelta(days=ttl_days))
            return result

        return wrapper

    return decorator
