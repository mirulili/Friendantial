import logging
from typing import List
from contextlib import asynccontextmanager
import math
from urllib.parse import quote_plus, urlparse, parse_qs
import re
import xml.etree.ElementTree as ET

import httpx
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

from .config import (
    NEWS_MAX,
    SENTIMENT_MODEL_ID,
    SENTIMENT_CONFIDENCE_THRESHOLD_NEUTRAL,
    SENTIMENT_CONFIDENCE_THRESHOLD_STRONG,
    SENTIMENT_BATCH_SIZE,
    SENTIMENT_NEWS_WEIGHT_DECAY_RATE,
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
)

# 네이버 뉴스 검색 결과에서 link URL의 'oid' 쿼리 파라미터는 언론사를 나타냅니다.
# 주요 언론사의 oid를 매핑하여 발행처를 식별하는 데 사용합니다.
NAVER_NEWS_OIDS = dict(
    (
        ("001", "연합뉴스"), ("003", "뉴시스"), ("005", "국민일보"), ("008", "머니투데이"),
        ("011", "서울경제"), ("014", "파이낸셜뉴스"), ("015", "한국경제"), ("016", "헤럴드경제"),
        ("018", "이데일리"), ("020", "동아일보"), ("021", "문화일보"), ("022", "세계일보"),
        ("023", "조선일보"), ("025", "중앙일보"), ("028", "한겨레"), ("030", "전자신문"),
        ("031", "아이뉴스24"), ("032", "경향신문"), ("055", "SBS"), ("056", "KBS"),
        ("057", "MBN"), ("081", "서울신문"), ("082", "한국일보"), ("214", "MBC"),
        ("277", "아시아경제"), ("374", "SBS Biz"), ("421", "뉴스1"), ("422", "YTN"),
        ("448", "TV조선"), ("449", "채널A"),
    )
)

@asynccontextmanager
async def sentiment_lifespan(app):
    """FastAPI lifespan 이벤트 핸들러: 모델 로딩 및 정리"""
    logging.info("Sentiment pipeline 초기화를 시작합니다...")
    app.state.sentiment_pipe = None
    try:
        tok = AutoTokenizer.from_pretrained(SENTIMENT_MODEL_ID)
        mdl = AutoModelForSequenceClassification.from_pretrained(SENTIMENT_MODEL_ID, use_safetensors=True)
        
        app.state.sentiment_pipe = pipeline("sentiment-analysis", model=mdl, tokenizer=tok, device=-1)
        logging.info("Sentiment pipeline 준비 완료: %s", SENTIMENT_MODEL_ID)
    except Exception as e:
        logging.error("Sentiment pipeline 초기화 실패: %s", e)
    
    yield

    logging.info("Sentiment pipeline을 정리합니다.")
    app.state.sentiment_pipe = None

async def fetch_news_titles(client: httpx.AsyncClient, query: str, limit: int = NEWS_MAX) -> List[str]:
    if limit <= 0:
        return []
    
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        logging.error("Naver API credentials(NAVER_CLIENT_ID, NAVER_CLIENT_SECRET) are not set.")
        return []

    # "두산"과 같은 종목명만으로 검색하면 야구 등 관련 없는 뉴스가 포함될 수 있습니다.
    # "증권", "경제"와 같은 키워드를 추가하여 금융/경제 관련 뉴스의 우선순위를 높입니다.
    search_query = f"{query} 증권 경제"
    encoded_query = quote_plus(search_query)
    url = f"https://openapi.naver.com/v1/search/news.xml?query={encoded_query}&display={limit}&start=1&sort=sim"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    try:
        r = await client.get(url, headers=headers, timeout=6.0)
        if r.status_code != 200 or not r.text:
            return []
        titles: List[str] = []
        root = ET.fromstring(r.text)
        for item in root.findall("./channel/item"):
            publisher = "출처 미상"
            # 1. 네이버 뉴스 링크(oid 포함)를 우선적으로 파싱합니다.
            link_node = item.find("link")
            if link_node is not None and link_node.text:
                try:
                    parsed_url = urlparse(link_node.text)
                    if parsed_url.hostname and "news.naver.com" in parsed_url.hostname:
                        query_params = parse_qs(parsed_url.query)
                        oid = query_params.get('oid', [None])[0]
                        if oid:
                            publisher = NAVER_NEWS_OIDS.get(oid, f"OID:{oid}")
                except Exception:
                    pass # 파싱 실패 시 다음 단계로 넘어갑니다.
            
            # 2. 네이버 뉴스 링크에서 언론사를 찾지 못한 경우, 원문 링크의 도메인을 사용합니다.
            if publisher == "출처 미상":
                original_link_node = item.find("originallink")
                if original_link_node is not None and original_link_node.text:
                    try:
                        hostname = urlparse(original_link_node.text).hostname
                        if hostname:
                            # 'www.google.com' -> 'google', 'm.hankooki.com' -> 'hankooki'
                            publisher = re.sub(r'^(www|m)\.|\.(com|co\.kr|kr|net|org)$', '', hostname).strip()
                            publisher = publisher or "출처 미상" # 정제 후 빈 문자열이 되면 '출처 미상'으로
                    except Exception:
                        pass

            tnode = item.find("title")
            if tnode is not None and tnode.text and (t := tnode.text.strip()):
                # 뉴스 제목에서 <b>, &lt;b&gt; 같은 HTML 태그와 특수문자를 제거합니다.
                clean_title = re.sub(r'<[/]?b>|&[a-z]+;', '', t).strip()
                titles.append(f"[{publisher}] {clean_title}")
                if len(titles) >= limit:
                    break
        return titles
    except Exception as e:
        logging.warning(f"뉴스 수집 실패 (종목: {query}): {e}")
        return []

def _stars_from_prediction(label: str, confidence: float, id2label: dict) -> tuple[int, str, int]:
    """모델 예측 결과를 바탕으로 별점(1-5), 표시용 레이블, 감성 값(-1,0,1)을 반환합니다."""
    if confidence < SENTIMENT_CONFIDENCE_THRESHOLD_NEUTRAL:
        return 3, "중립", 0

    is_strong = confidence >= SENTIMENT_CONFIDENCE_THRESHOLD_STRONG
    
    try:
        # 'LABEL_2'와 같은 형식을 처리하기 위해 숫자 인덱스를 추출합니다.
        label_index = int(label.split('_')[-1])
    except ValueError:
        # 'positive'와 같은 문자열 레이블인 경우, 레이블 자체를 사용합니다.
        label_index = label
    semantic_label = id2label.get(label_index, str(label)).lower()

    # KR-FinBERT: 2=긍정, 1=중립, 0=부정
    positive_labels = ["2", "positive"]
    negative_labels = ["0", "negative"]

    if semantic_label in positive_labels:
        stars = 5 if is_strong else 4
        display_label = "강력한 호재" if is_strong else "호재"
        return stars, display_label, 1
    if semantic_label in negative_labels:
        stars = 1 if is_strong else 2
        display_label = "강력한 악재" if is_strong else "악재"
        return stars, display_label, -1

    # '1', 'neutral' 또는 예상치 못한 레이블은 모두 중립으로 처리
    return 3, "중립", 0

def analyze_news_sentiment(pipe: pipeline, headlines: List[str]) -> dict:
    if not headlines:
        return {"enabled": False, "summary": "no headlines", "details": [], "score": 0.0}
    if not pipe:
        return {"enabled": False, "summary": "model not available", "details": [], "score": 0.0}

    details = []
    score_acc = 0.0
    id2label = pipe.model.config.id2label
    preds = pipe(headlines, batch_size=SENTIMENT_BATCH_SIZE, truncation=True, max_length=512)

    for i, (title, pred) in enumerate(zip(headlines, preds)):
        label = pred.get("label", "neutral")
        confidence = float(pred.get("score", 0.0))
        
        stars, display_label, sentiment_value = _stars_from_prediction(label, confidence, id2label)

        weight = math.exp(-SENTIMENT_NEWS_WEIGHT_DECAY_RATE * i)
        score_acc += sentiment_value * weight
        
        details.append({"title": title, "label": display_label, "confidence": round(confidence, 3)})

    final_score = score_acc
    summary = f"최근 뉴스 {len(details)}건 분석 완료"
    return {"enabled": True, "summary": summary, "details": details, "score": final_score}