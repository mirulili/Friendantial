from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class FeatureConf(BaseModel):
    mom_short: int = 5
    mom_med: int = 20
    mom_long: int = 60
    min_turnover_won: float = 5e9

class StockScore(BaseModel):
    code: str
    name: str
    score: float
    reason: str
    momentum: Dict[str, float]
    news_sentiment_score: Optional[float] = None

class RecoItem(BaseModel):
    code: str
    name: str
    score: float
    weight: float
    reason: str
    momentum: Dict[str, float]
    news_sentiment: Optional[Dict[str, Any]] = None

class RecoResponse(BaseModel):
    as_of: str
    candidates: List[RecoItem]