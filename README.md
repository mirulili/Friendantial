# Friendantial - 주식 분석 및 추천 API

**Friendantial**은 FinanceDataReader, Google News RSS, 그리고 HuggingFace Transformers를 활용하여 대한민국 주식 시장의 종목을 분석하고 추천하는 FastAPI 기반의 API 서버입니다.

### 주요 기능
- **모멘텀 스코어링**: 단기, 중기, 장기 가격 모멘텀을 계산하여 종목의 추세를 평가합니다.
- **뉴스 감성 분석**: Google News에서 최신 뉴스 헤드라인을 수집하고, 다국어 감성 분석 모델을 통해 긍정/중립/부정 점수를 산출합니다.
- **종합 추천**: 모멘텀, 거래량, 뉴스 감성 점수를 종합하여 상위 종목을 추천합니다.

## 기술 스택

*   **API 프레임워크**: FastAPI
*   **데이터 분석**: Pandas
*   **금융 데이터**: FinanceDataReader
*   **뉴스 수집**: Google News RSS, httpx
*   **감성 분석**: HuggingFace Transformers (`cardiffnlp/twitter-xlm-roberta-base-sentiment`)
*   **웹 서버**: Uvicorn
*   **컨테이너**: Docker, Docker Compose

## 설치 및 실행

### 1. 사전 준비

*   Python 3.10 이상
*   Docker 및 Docker Compose

### 2. Docker를 이용한 실행 (권장)

프로젝트 루트 디렉토리에서 다음 명령어를 실행하세요. `Makefile`을 사용하여 더 간편하게 관리할 수 있습니다.

```bash
# Docker 이미지 빌드 및 서비스 시작
make up

# 실행 중인 서비스 로그 확인
make logs

# 서비스 중지 및 컨테이너/네트워크 삭제
make down
```

### 3. 로컬 환경에서 직접 실행

```bash
git clone <your-repository-url>
cd Friendantial
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .\.venv\Scripts\activate    # Windows

# 의존성 설치
pip install -r requirements.txt

# 서버 실행 (src 디렉토리에서 실행)
cd src
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API 엔드포인트

### 종합 추천 (Orchestrator)
- `GET /recommendations`: 여러 분석 지표를 종합하여 상위 N개 주식 종목을 추천합니다.

### 분석 도구 (Analysis Tools)
- `GET /analysis/news-sentiment/{stock_name}`: 특정 종목의 최신 뉴스 헤드라인을 수집하고 감성 분석을 수행합니다.
- `GET /analysis/technical-indicator/{stock_code}`: 특정 종목의 모멘텀 등 기술적 지표를 계산합니다.

### 데이터 조회 (Data Tools)
- `GET /market-data/ohlcv/{stock_code}`: 특정 종목의 시세(OHLCV) 데이터를 조회합니다.

### 리포팅 (Reporting Tools)
- `POST /reporting/summary`: 추천 결과를 입력받아 사람이 읽기 좋은 형태의 요약 보고서를 생성합니다.

### 서버 상태
- `GET /health`: 서버의 현재 상태와 시간을 확인합니다.

> 각 엔드포인트의 상세한 파라미터와 응답 형식은 서버 실행 후 `http://127.0.0.1:8000/docs`에서 확인하세요.