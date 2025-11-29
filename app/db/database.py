# app/db/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from ..config import DATABASE_URL

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in the environment variables.")

# 데이터베이스 엔진 생성
engine = create_engine(DATABASE_URL)

# 세션 생성기
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모든 모델 클래스가 상속할 기본 클래스
Base = declarative_base()


# API 라우터에서 사용할 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
