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

SENTIMENT_MODEL_ID = os.getenv("SENTIMENT_MODEL", "sangrimlee/bert-base-multilingual-cased-nsmc")