import os
import re
import logging
from typing import List, Tuple
from fastapi import Request, HTTPException

from .market_data import get_universe_from_market_data
ENV_TICKERS = [t.strip() for t in os.getenv("TICKERS", "").split(",") if t.strip()]

DEFAULT_UNIVERSE: List[Tuple[str, str]] = [
    ("005930.KS", "삼성전자"),
    ("000660.KS", "SK하이닉스"),
    ("006400.KS", "삼성SDI"),
    ("051910.KS", "LG화학"),
    ("005380.KS", "현대차"),
    ("000270.KS", "기아"),
    ("012330.KS", "현대모비스"),
    ("035420.KS", "네이버"),
    ("035720.KS", "카카오"),
    ("068270.KS", "셀트리온"),
    ("207940.KS", "삼성바이오로직스"),
    ("055550.KS", "신한지주"),
    ("105560.KS", "KB금융"),
    ("028260.KS", "삼성물산"),
    ("096770.KS", "SK이노베이션"),
    ("000810.KS", "삼성화재"),
    ("066570.KS", "LG전자"),
    ("003550.KS", "LG"),
    ("034730.KS", "SK"),
    ("051900.KS", "LG생활건강"),
]

def parse_env_universe() -> List[Tuple[str, str]]:
    if not ENV_TICKERS:
        return [] # 환경 변수가 없으면 빈 리스트 반환
    return [(sym, re.sub(r"\.[A-Z]{2}$", "", sym)) for sym in ENV_TICKERS]

async def get_universe(request: Request, market_code: str) -> List[Tuple[str, str]]:
    # 1. 환경 변수에 TICKERS가 지정되어 있으면 최우선으로 사용합니다.
    env_uni = parse_env_universe()
    if env_uni:
        logging.info(f"환경변수 TICKERS에 설정된 {len(env_uni)}개 종목을 유니버스로 사용합니다.")
        return env_uni

    # 2. 환경 변수가 없으면, 공공데이터 API를 사용하여 유니버스를 구성합니다.
    try:
        universe = await get_universe_from_market_data(request, market_code)
        if universe:
            return universe
    except Exception as e:
        logging.warning(f"공공데이터 API를 통한 유니버스 생성 실패: {e}. 기본 유니버스를 사용합니다.")
    
    # 3. API 호출 실패 시, 미리 정의된 기본 유니버스를 사용합니다.
    logging.info(f"기본 유니버스(DEFAULT_UNIVERSE)에 정의된 {len(DEFAULT_UNIVERSE)}개 종목을 사용합니다.")
    return DEFAULT_UNIVERSE