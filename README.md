# Friendantial

Friendantial은 투자자가 시장을 분석할 때 참고할 수 있는 주식 추천 및 분석 리포트를 제공하는 API 서버입니다. 복잡한 금융 데이터를 AI와 LLM을 통해 분석하여, 이해하기 쉬운 자연어 리포트와 정량적인 추천 점수를 제공합니다.

## 주요 기능

### 1. 종합 점수 기반 주식 추천

* **다중 팩터 분석**: 모멘텀(단기/중기/장기), 뉴스 감성, 변동성(ATR), 상대강도지수(RSI), 거래대금 등 여러 지표를 종합하여 추천 점수를 계산합니다.
* **100점 만점 스케일**: 최종 추천 점수를 0점에서 100점 사이의 직관적인 정수 값으로 제공합니다.
* **서킷 브레이커**: 시장 상황이 좋지 않거나 주도주의 모멘텀이 약할 경우, 최고 점수를 제한하여 무리한 매수를 방지합니다.

### 2. 동적 시장 상황 분석 (Market Regime)

* 시장 대표 지수(KODEX 200 등)의 이동평균선을 분석하여 현재 시장을 상승장(BULL), 하락장(BEAR), 중립장(NEUTRAL)으로 자동 판단합니다.
* 시장 상황에 따라 점수 산정 가중치를 동적으로 조정하여 리스크를 관리합니다.

### 3. 트레이딩 전략별 맞춤 추천

* API 호출 시 strategy 파라미터를 통해 사용자의 투자 스타일에 맞는 로직으로 추천을 받을 수 있습니다.
* **Day Trader**: 단기 이동평균선 이탈, RSI 과매도 구간 반등 등 단기 시세 차익에 집중합니다.
* **Long Term**: 장기 이동평균선 지지 여부와 추세 지속성을 중요하게 평가합니다.

### 4. RAG 기반 질의응답

* **뉴스 기반 답변**: 사용자가 특정 종목에 대해 질문(예: "삼성전자 왜 떨어져?")하면, 최신 뉴스를 검색하고 벡터 DB(ChromaDB)를 활용해 근거 있는 답변을 제공합니다.
* **할루시네이션 방지**: 최신 뉴스 데이터에 기반한 답변을 생성하여 정보의 신뢰성을 높였습니다.

### 5. 과거 데이터 백테스트

* **전략 검증**: 과거 특정 시점으로 돌아가 추천 알고리즘을 실행했을 때의 결과를 시뮬레이션합니다.
* **수익률 분석**: 당시 전략의 매수/관망 판단과 이후 실제 주가 흐름을 비교하여 예상 수익률과 방어율을 제공합니다.

### 6. 자연어 리포트 생성

* 추천된 종목들의 핵심 데이터를 요약하여 친근한 말투(Friend 페르소나) 또는 전문적인 말투(Analyst 페르소나)로 리포트를 작성합니다.

## 기술 스택

* **API 프레임워크**: FastAPI
* **데이터베이스**: PostgreSQL
* **캐시/메시지 브로커**: Redis
* **AI / ML**:
    **Sentiment Analysis**: snunlp/KR-FinBert-SC
    **Embedding**: jhgan/ko-sroberta-multitask
    **Vector DB**: ChromaDB
    **LLM**: OpenAI (gpt-4-turbo), Google Gemini 등
* **데이터 소스**:
    **Market Data**: 공공데이터포털 (금융위원회 주식시세정보)
    **News**: Naver News API
* **인프라**: Docker, Docker Compose

## 시작하기

### 1. 환경 변수 설정

프로젝트 루트에 .env 파일을 생성하고 아래 내용을 채워주세요.

```bash
# API Keys
DATA_GO_KR_API_KEY=your_data_go_kr_key_decoded
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret

# LLM Provider (openai or gemini)
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key
# GEMINI_API_KEY=your_gemini_key

# Database & Redis
DATABASE_URL=postgresql://user:password@db:5432/friendantial
REDIS_URL=redis://redis:6379/0

# Settings
LOG_LEVEL=INFO
MARKET=KS
```

### 2. 실행 방법 (Makefile 사용 권장)

이 프로젝트는 Makefile을 통해 간편하게 실행할 수 있습니다.

**로컬 개발 환경 실행:**

```bash
# 의존성 설치
make install

# 서버 실행 (http://localhost:8000)
make run
```

**Docker 환경 실행:**

```bash
# 컨테이너 빌드 및 실행
make all

# 로그 확인
make logs

# 컨테이너 중지 및 삭제
make down
```

## 주요 API 엔드포인트

| 메서드 | 경로 | 설명 | 주요 파라미터 |
| :--- | :--- | :--- | :--- |
| GET | `/basic_analysis/recommendations` | 종합 점수 기반 주식 추천 | strategy (day_trader 등) |
| GET | `/reporting/summary` | 추천 결과 요약 리포트 생성 | strategy, persona |
| GET | `/reporting/stock/{stock_code}` | 개별 종목 심층 분석 리포트 | persona |
| GET | `/opinion/opinion/{stock_code}` | 종목 관련 RAG 질의응답 | question (질문 내용) |
| GET | `/backtest/simulate` | 과거 시점 전략 시뮬레이션 | target_date, codes |
| GET | `/basic_analysis/news-sentiment/{stock_name}` | 뉴스 감성 분석 결과 조회 | |
| GET | `/market-data/ohlcv/{stock_code}` | OHLCV 시세 데이터 조회 | lookback_days |
| GET | `/history/recommendations` | 과거 추천 이력 조회 | start_date, end_date |
| GET | `/health` | 서버 상태 확인 | |

> 각 엔드포인트의 상세한 파라미터와 응답 형식은 서버 실행 후 http://127.0.0.1:8000/docs 에서 확인할 수 있습니다.
