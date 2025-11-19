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

#### 1. 소스 코드 복제

```bash
git clone <your-repository-url>
cd Friendantial
```

#### 2. 가상 환경 생성 및 활성화

프로젝트 루트 디렉토리에서 다음 명령어를 실행하여 파이썬 가상 환경을 만들고 활성화합니다.

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate  # macOS/Linux

# Windows (Command Prompt 또는 PowerShell)
.\.venv\Scripts\activate
```

#### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

#### 4. 환경 변수 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 아래 내용을 참고하여 API 키, 데이터베이스 URL 등을 설정합니다. 이 파일은 `python-dotenv` 라이브러리에 의해 자동으로 로드됩니다.

```.env
# .env 파일 예시

# 분석할 시장 (KS: 코스피, KQ: 코스닥)
MARKET="KS"

# 공공데이터포털 주식 시세 API 키 (필수)
DATA_GO_KR_API_KEY="YOUR_DATA_GO_KR_API_KEY"

# 추천 이력 저장을 위한 데이터베이스 URL (예: SQLite)
DATABASE_URL="sqlite:////../Friendancial/friendancial.db"

# 데이터 캐싱을 위한 Redis URL
REDIS_URL="redis://localhost:6379/0"

# 사용할 감성 분석 모델 ID (snunlp/KR-FinBert-SC는 감성분석용으로 미세조정된 모델입니다)
SENTIMENT_MODEL="snunlp/KR-FinBert-SC"

# 유니버스 필터링을 위한 최소 거래대금 (단위: 원, 예: 10억)
UNIVERSE_MIN_TURNOVER_WON=1e9
```

#### 5. 서버 실행

`src` 디렉토리로 이동한 후 Uvicorn을 사용하여 서버를 실행합니다.

```bash
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

### 이력 조회 (History)
- `GET /history/recommendations`: 데이터베이스에 저장된 과거 추천 이력을 조회합니다.

### 서버 상태
- `GET /health`: 서버의 현재 상태와 시간을 확인합니다.

> 각 엔드포인트의 상세한 파라미터와 응답 형식은 서버 실행 후 `http://127.0.0.1:8000/docs`에서 확인하세요.

## API 사용 예시 (cURL)

서버가 실행 중일 때, 다음 `cURL` 명령어를 사용하여 API를 테스트할 수 있습니다.

### 상위 3개 종목 추천받기 (뉴스 분석 포함)

```bash
curl -X GET "http://127.0.0.1:8000/recommendations?n=3"
```

### 특정 종목의 뉴스 감성 분석하기 (예: SK하이닉스)

```bash
curl -X GET "http://127.0.0.1:8000/analysis/news-sentiment/SK하이닉스"
```

### 특정 종목의 시세 데이터 조회하기 (예: 005930.KS, 최근 30일)

```bash
curl -X GET "http://127.0.0.1:8000/market-data/ohlcv/005930.KS?lookback_days=30"
```