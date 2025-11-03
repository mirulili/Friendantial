import logging
from typing import List
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx
from transformers import XLMRobertaTokenizer, AutoModelForSequenceClassification, pipeline

from .config import NEWS_MAX, SENTIMENT_MODEL_ID

_sentiment_pipe = None

def get_sentiment_pipeline():
    global _sentiment_pipe
    if _sentiment_pipe is not None:
        return _sentiment_pipe
    try:
        # AutoTokenizer 대신 XLM-RoBERTa 전용 토크나이저를 명시적으로 사용합니다.
        # 이렇게 하면 불필요한 자동 변환 시도를 건너뛰어 호환성 문제를 해결할 수 있습니다.
        tok = XLMRobertaTokenizer.from_pretrained(SENTIMENT_MODEL_ID)
        # use_safetensors=True를 통해 보안에 안전한 safetensors 형식으로 모델을 로드합니다.
        # 이는 torch.load 관련 보안 취약점 경고를 해결합니다.
        mdl = AutoModelForSequenceClassification.from_pretrained(SENTIMENT_MODEL_ID, use_safetensors=True)
        _sentiment_pipe = pipeline("sentiment-analysis", model=mdl, tokenizer=tok, device=-1)
        logging.info("Sentiment pipeline ready: %s", SENTIMENT_MODEL_ID)
        return _sentiment_pipe
    except Exception as e:
        logging.warning("Sentiment pipeline init failed: %s", e)
        _sentiment_pipe = None
        return None

async def fetch_news_titles(client: httpx.AsyncClient, query: str, limit: int = NEWS_MAX) -> List[str]:
    if limit <= 0:
        return []
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        r = await client.get(url, timeout=6.0)
        if r.status_code != 200 or not r.text:
            return []
        titles: List[str] = []
        root = ET.fromstring(r.text)
        for item in root.findall("./channel/item"):
            tnode = item.find("title")
            if tnode is not None and tnode.text and (t := tnode.text.strip()):
                titles.append(t)
                if len(titles) >= limit:
                    break
        return titles
    except Exception as e:
        logging.warning("news fetch failed for %s: %s", query, e)
        return []

def _stars_from_prediction(label: str, confidence: float) -> tuple[int, str]:
    """모델 예측 결과를 바탕으로 별점(1-5)과 표시용 레이블을 반환합니다."""
    if confidence < 0.65:
        return 3, "중립"

    is_strong = confidence >= 0.9
    str_label = str(label).lower()

    # '1' 또는 'positive'는 긍정으로 처리
    if str_label == "1" or str_label == "positive":
        return (5, "강력한 호재") if is_strong else (4, "호재")
    
    # '0' 또는 'negative'는 부정으로 처리
    if str_label == "0" or str_label == "negative":
        return (1, "강력한 악재") if is_strong else (2, "악재")

    # 'neutral' 레이블 또는 예상치 못한 레이블은 모두 중립으로 처리
    return 3, "중립"

def analyze_news_sentiment(headlines: List[str]) -> dict:
    if not headlines:
        return {"enabled": False, "summary": "no headlines", "details": [], "score": 0.0}
    pipe = get_sentiment_pipeline()
    if pipe is None:
        return {"enabled": False, "summary": "model not available", "details": [], "score": 0.0}

    preds = pipe(headlines, batch_size=16, truncation=True)
    details = []
    score_acc = 0.0
    for title, pred in zip(headlines[:len(preds)], preds):
        label = pred.get("label", "neutral")
        confidence = float(pred.get("score", 0.0))
        
        stars, display_label = _stars_from_prediction(label, confidence)
        
        sentiment_value = 0
        if stars > 3:
            sentiment_value = 1
        elif stars < 3:
            sentiment_value = -1

        weight = 1.0 - (len(details) * 0.2)
        score_acc += sentiment_value * weight
        details.append({
            "title": title, 
            "label": display_label, 
            "stars": stars, 
            "confidence": round(confidence, 3), 
            "sentiment_value": sentiment_value
        })

    final_score = score_acc / len(details) if details else 0.0
    summary = f"최근 뉴스 {len(details)}건 분석 완료"
    return {"enabled": True, "summary": summary, "details": details, "score": final_score}