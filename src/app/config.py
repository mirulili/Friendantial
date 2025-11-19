import os
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logging_config = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "format": "[%(asctime)s] %(levelname)s %(message)s",
}

try:
    TZ = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    from datetime import timezone
    TZ = timezone(timedelta(hours=9))

MARKET = os.getenv("MARKET", "KS")
NEWS_MAX = int(os.getenv("NEWS_MAX", "3"))

# 감성 분석을 위해 미세 조정된 snunlp/KR-FinBert-SC를 사용합니다.
# SC는 Sentiment Classification을 의미합니다.
SENTIMENT_MODEL_ID = os.getenv("SENTIMENT_MODEL", "snunlp/KR-FinBert-SC")

# 공공데이터포털 API 서비스 키
DATA_GO_KR_API_KEY = os.getenv("DATA_GO_KR_API_KEY")

# 데이터베이스 접속 URL
DATABASE_URL = os.getenv("DATABASE_URL")

# Redis 접속 URL
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 데이터 캐시 디렉토리
CACHE_DIR = os.getenv("CACHE_DIR", ".cache")

# 유니버스 필터링을 위한 최소 거래대금 (단위: 원, 기본값: 10억)
UNIVERSE_MIN_TURNOVER_WON = float(os.getenv("UNIVERSE_MIN_TURNOVER_WON", "1e9"))

# 감성 분석 관련 설정값
SENTIMENT_CONFIDENCE_THRESHOLD_NEUTRAL = float(os.getenv("SENTIMENT_CONFIDENCE_THRESHOLD_NEUTRAL", "0.55"))
# KR-FinBert-SC 모델이 매우 높은 신뢰도로 예측하는 경향이 있으므로, '강력한' 호재/악재를 판단하는 기준을 더 높게 설정합니다.
# 0.9에서 0.99로 상향 조정하여, 일반 '호재'/'악재'가 나타날 구간을 확보합니다.
SENTIMENT_CONFIDENCE_THRESHOLD_STRONG = float(os.getenv("SENTIMENT_CONFIDENCE_THRESHOLD_STRONG", "0.99"))
SENTIMENT_BATCH_SIZE = int(os.getenv("SENTIMENT_BATCH_SIZE", "16"))
SENTIMENT_NEWS_WEIGHT_DECAY_RATE = float(os.getenv("SENTIMENT_NEWS_WEIGHT_DECAY_RATE", "0.2"))

# Naver API credentials
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")