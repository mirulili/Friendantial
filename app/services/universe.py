import logging
import os
import re
from typing import List, Tuple

from fastapi import Request

from .market_data import get_universe_from_market_data

ENV_TICKERS = [t.strip() for t in os.getenv("TICKERS", "").split(",") if t.strip()]

# 상위 20개의 대장주를 미리 정의
DEFAULT_UNIVERSE: List[Tuple[str, str]] = [
    ("005930.KS", "삼성전자"),  # 1
    ("373220.KS", "LG에너지솔루션"),  # 2
    ("000660.KS", "SK하이닉스"),  # 3
    ("207940.KS", "삼성바이오로직스"),  # 4
    ("005935.KS", "삼성전자우"),  # 5
    ("005380.KS", "현대차"),  # 6
    ("000270.KS", "기아"),  # 7
    ("068270.KS", "셀트리온"),  # 8
    ("005490.KS", "POSCO홀딩스"),  # 9
    ("051910.KS", "LG화학"),  # 10
    ("035420.KS", "NAVER"),  # 11
    ("028260.KS", "삼성물산"),  # 12
    ("105560.KS", "KB금융"),  # 13
    ("012330.KS", "현대모비스"),  # 14
    ("055550.KS", "신한지주"),  # 15
    ("066570.KS", "LG전자"),  # 16
    ("035720.KS", "카카오"),  # 17
    ("006400.KS", "삼성SDI"),  # 18
    ("086790.KS", "하나금융지주"),  # 19
    ("042700.KS", "한미반도체"),  # 20
]


def parse_env_universe() -> List[Tuple[str, str]]:
    if not ENV_TICKERS:
        return []  # 환경 변수가 없으면 빈 리스트 반환
    return [(sym, re.sub(r"\.[A-Z]{2}$", "", sym)) for sym in ENV_TICKERS]


import httpx

# ...

async def get_universe(
    client: httpx.AsyncClient, request: Request, market_code: str
) -> List[Tuple[str, str]]:
    # 1. 환경 변수에 TICKERS가 지정되어 있으면 최우선으로 사용
    env_uni = parse_env_universe()
    if env_uni:
        logging.info(
            f"환경변수 TICKERS에 설정된 {len(env_uni)}개 종목을 유니버스로 사용합니다."
        )
        return env_uni

    # 2. 환경 변수가 없으면, 공공데이터 API를 사용하여 유니버스를 구성
    try:
        universe = await get_universe_from_market_data(client, request, market_code)
        if universe:
            return universe
    except Exception as e:
        logging.warning(
            f"공공데이터 API를 통한 유니버스 생성 실패: {e}. 기본 유니버스를 사용합니다."
        )

    # 3. API 호출 실패 시, 미리 정의된 기본 유니버스를 사용
    logging.info(
        f"기본 유니버스(DEFAULT_UNIVERSE)에 정의된 {len(DEFAULT_UNIVERSE)}개 종목을 사용합니다."
    )
    return DEFAULT_UNIVERSE
