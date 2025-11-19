from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import date, datetime

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

class NewsSentimentDetail(BaseModel):
    title: str
    label: str
    confidence: float

class NewsSentiment(BaseModel):
    summary: str
    stars: int
    details: List[NewsSentimentDetail]

class RecoItem(BaseModel):
    code: str
    name: str
    score: float
    weight: float
    reason: str
    momentum: Dict[str, float]
    news_sentiment: Optional[NewsSentiment] = None

class RecoResponse(BaseModel):
    as_of: str
    candidates: List[RecoItem]

# --- History API를 위한 모델 ---

class RecommendedStockHistoryItem(BaseModel):
    code: str
    name: str
    score: float
    weight: float
    reason: Optional[str] = None

    class Config:
        from_attributes = True

class RecommendationRunHistoryItem(BaseModel):
    id: int
    as_of: date
    created_at: datetime
    stocks: List[RecommendedStockHistoryItem]

    class Config:
        from_attributes = True