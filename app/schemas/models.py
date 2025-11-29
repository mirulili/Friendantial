# app/schemas/models.py

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


# --- 공통 모델 ---
class StockBase(BaseModel):
    code: str
    name: str


class FeatureConf(BaseModel):
    mom_short: int = 5
    mom_med: int = 20
    mom_long: int = 60
    min_turnover_won: float = 5e9


class StockScore(StockBase):
    score: float
    reason: str
    momentum: Dict[str, float]
    news_sentiment_score: Optional[float] = None
    price: float = 0.0  # 분석 시점의 종가 (전일종가)


class NewsSentimentDetail(BaseModel):
    title: str
    label: str
    confidence: float


class NewsSentiment(BaseModel):
    summary: str
    details: List[NewsSentimentDetail]


# 추천 로직에서 반환
class RecoItem(StockBase):
    score: float  # 0~100점 사이의 점수
    stars: int  # 종목의 최종 추천 별점
    weight: float
    price: float = 0.0  # 가격
    reason: str
    momentum: Dict[str, float]
    news_sentiment: Optional[NewsSentiment] = None


class RecoResponse(BaseModel):
    as_of: str
    candidates: List[RecoItem]


# --- History API를 위한 모델 ---
class RecommendedStockHistoryItem(StockBase):
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
