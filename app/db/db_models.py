# app/db/db_models.py

from sqlalchemy import JSON, Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"

    id = Column(Integer, primary_key=True, index=True)
    as_of = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # RecommendedStock
    stocks = relationship("RecommendedStock", back_populates="run")


class RecommendedStock(Base):
    __tablename__ = "recommended_stocks"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("recommendation_runs.id"), nullable=False)

    code = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    weight = Column(Float, nullable=False)
    reason = Column(String)

    # 복잡한 데이터를 JSON으로 저장
    momentum = Column(JSON)
    news_sentiment = Column(JSON)

    # RecommendationRun
    run = relationship("RecommendationRun", back_populates="stocks")
