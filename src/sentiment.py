import re
import logging
from typing import List
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

from .config import NEWS_MAX, SENTIMENT_MODEL_ID

_sentiment_pipe = None

def get_sentiment_pipeline():
    global _sentiment_pipe
    if _sentiment_pipe is not None:
        return _sentiment_pipe
    try:
        tok = AutoTokenizer.from_pretrained(SENTIMENT_MODEL_ID)
        mdl = AutoModelForSequenceClassification.from_pretrained(SENTIMENT_MODEL_ID)
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
    if confidence < 0.65:
        return 3, "중립"
    if label == "positive":
        return (5, "강력한 호재") if confidence >= 0.9 else (4, "호재")
    else:  # "negative"
        return (1, "강력한 악재") if confidence >= 0.9 else (2, "악재")

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