# Friendantial - 주식 추천 API

**Friendantial**은 FinanceDataReader, Google News RSS, 그리고 HuggingFace Transformers를 활용하여 대한민국 주식 시장의 종목을 분석하고 추천하는 FastAPI 기반의 API 서버입니다.

주요 기능:
- **모멘텀 스코어링**: 단기, 중기, 장기 가격 모멘텀을 계산하여 종목의 추세를 평가합니다.
- **뉴스 감성 분석**: Google News에서 최신 뉴스 헤드라인을 수집하고, 다국어 감성 분석 모델을 통해 긍정/중립/부정 점수를 산출합니다.
- **종합 추천**: 모멘텀, 거래량, 뉴스 감성 점수를 종합하여 상위 종목을 추천합니다.

## 기술 스택

- **API 프레임워크**: FastAPI
- **데이터 분석**: Pandas
- **금융 데이터**: FinanceDataReader
- **뉴스 수집**: Google News RSS, Requests
- **감성 분석**: HuggingFace Transformers (`nlptown/bert-base-multilingual-uncased-sentiment`)
- **웹 서버**: Uvicorn

## 설치 및 실행

### 1. 사전 준비

- Python 3.9 이상
- Git

### 2. 프로젝트 클론 및 가상 환경 설정

```bash
git clone <your-repository-url>
cd Friendantial
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .\.venv\Scripts\activate  # Windows
```

### 3. 의존성 설치

프로젝트에 필요한 라이브러리를 설치합니다.

```bash
pip install -r requirements.txt
```

### 4. 서버 실행

Uvicorn을 사용하여 로컬에서 개발 서버를 실행합니다.

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

서버가 실행되면 브라우저에서 `http://127.0.0.1:8000/docs` 로 접속하여 API 문서를 확인할 수 있습니다.

## API 엔드포인트

- `GET /recommendations`: 주식 종목을 추천합니다.
  - **Query Parameters**:
    - `as_of` (string, optional): 기준일 (YYYY-MM-DD). 기본값: 오늘.
    - `n` (int, optional): 추천할 종목 수 (1~10). 기본값: 5.
    - `with_news` (bool, optional): 뉴스 감성 분석 포함 여부. 기본값: True.
- `GET /health`: 서버 상태를 확인합니다.