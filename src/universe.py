import os
import re
from typing import List, Tuple
from fastapi import HTTPException

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
        return DEFAULT_UNIVERSE
    return [(sym, re.sub(r"\.[A-Z]{2}$", "", sym)) for sym in ENV_TICKERS]

def get_universe(market_code: str) -> List[Tuple[str, str]]:
    uni = parse_env_universe()
    if not uni:
        raise HTTPException(status_code=503, detail="No tickers provided and no default universe available.")
    return uni[:200]