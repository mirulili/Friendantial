from typing import List, Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from .. import db_models
from .. import models

router = APIRouter(
    prefix="/history",
    tags=["history"],
)

@router.get("/recommendations", response_model=List[models.RecommendationRunHistoryItem])
def get_recommendation_history(
    db: Session = Depends(get_db),
    start_date: Optional[date] = Query(None, description="조회 시작일 (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="조회 종료일 (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(10, ge=1, le=100, description="반환할 최대 항목 수"),
):
    """
    데이터베이스에 저장된 과거 추천 이력을 조회합니다.
    """
    query = db.query(db_models.RecommendationRun).options(
        joinedload(db_models.RecommendationRun.stocks)
    )

    if start_date:
        query = query.filter(db_models.RecommendationRun.as_of >= start_date)
    if end_date:
        query = query.filter(db_models.RecommendationRun.as_of <= end_date)

    runs = query.order_by(db_models.RecommendationRun.as_of.desc(), db_models.RecommendationRun.id.desc()).offset(skip).limit(limit).all()
    return runs