# Friendantial

Friendantial is an API server that provides stock recommendation and analysis reports for investors to reference when analyzing the market. By analyzing complex financial data through AI and LLMs, it offers easy-to-understand natural language reports and quantitative recommendation scores.

## Key Features

### 1. Comprehensive Score-Based Stock Recommendation

* **Multi-Factor Analysis**: Calculates recommendation scores by integrating various indicators such as momentum (short/mid/long-term), news sentiment, volatility (ATR), Relative Strength Index (RSI), and trading volume.
* **100-Point Scale**: Provides final recommendation scores as intuitive integer values between 0 and 100.
* **Circuit Breaker**: Prevents reckless buying by limiting the maximum score when market conditions are poor or lead stock momentum is weak.

### 2. Dynamic Market Regime Analysis

* Automatically determines the current market state as **BULL**, **BEAR**, or **NEUTRAL** by analyzing the moving averages of major market indices (e.g., KODEX 200).
* Manages risk by dynamically adjusting score calculation weights based on market conditions.

### 3. Customized Recommendations by Trading Strategy

* Users can receive recommendations tailored to their investment style using the `strategy` parameter during API calls.
* **Day Trader**: Focuses on short-term profit-taking, such as breakouts from short-term moving averages or rebounds from RSI oversold zones.
* **Long Term**: Emphasizes support levels of long-term moving averages and trend continuity.

### 4. RAG-Based Q&A

* **News-Based Answers**: When a user asks about a specific stock (e.g., "Why is Samsung Electronics falling?"), it searches for the latest news and provides evidence-based answers using a Vector DB (ChromaDB).
* **Hallucination Prevention**: Enhances information reliability by generating answers based on the most recent news data.

### 5. Historical Data Backtesting

* **Strategy Verification**: Simulates the results of the recommendation algorithm as if it were run at a specific point in the past.
* **Yield Analysis**: Provides expected returns and defense rates by comparing the buy/wait decisions of the strategy at that time with the actual subsequent price trends.

### 6. Natural Language Report Generation

* Summarizes key data for recommended stocks and generates reports in a friendly tone (**Friend persona**) or a professional tone (**Analyst persona**).

## Tech Stack

* **API Framework**: FastAPI
* **Database**: PostgreSQL
* **Cache/Message Broker**: Redis
* **AI / ML**:
    * **Sentiment Analysis**: snunlp/KR-FinBert-SC
    * **Embedding**: jhgan/ko-sroberta-multitask
    * **Vector DB**: ChromaDB
    * **LLM**: OpenAI (gpt-4-turbo), Google Gemini, etc.
* **Data Sources**:
    * **Market Data**: Public Data Portal (Financial Services Commission stock price information)
    * **News**: Naver News API
* **Infrastructure**: Docker, Docker Compose
* **Frontend**: Streamlit (Python-based web interface)

## Getting Started

### 1. Environment Variable Configuration

Create a `.env` file in the project root and fill in the required details.

### 2. How to Run (Makefile Recommended)

This project can be easily executed via the Makefile.

**Running in Local Development Environment:**

```bash
# Install dependencies (Backend + Frontend)
make install-all

# Run Backend server (http://localhost:8000)
make run

# Run Frontend (http://localhost:8501)
make run-frontend
```

**Running in Docker Environment:**

```bash
# Build and run containers (Backend + Frontend + DB + Redis)
make all

# Check logs
make logs

# Stop and remove containers
make down
```

> **Note**: When running in a Docker environment, the frontend can be accessed at `http://localhost:8501`.

## Key API Endpoints

| Method | Path | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| GET | `/basic_analysis/recommendations` | Stock recommendations based on total scores | strategy (e.g., day_trader) |
| GET | `/reporting/summary` | Generate summary reports of recommendations | strategy, persona |
| GET | `/reporting/stock/{stock_code}` | In-depth analysis report for individual stocks | persona |
| GET | `/opinion/opinion/{stock_code}` | RAG-based Q&A regarding a stock | question |
| GET | `/backtest/simulate` | Strategy simulation for a past date | target_date, codes |
| GET | `/basic_analysis/news-sentiment/{stock_identifier}` | Retrieve news sentiment analysis results | stock_identifier (name/code) |
| GET | `/basic_analysis/technical-indicator/{stock_code}` | Retrieve technical indicators | |
| GET | `/market-data/ohlcv/{stock_code}` | Retrieve OHLCV price data | lookback_days |
| GET | `/history/recommendations` | Retrieve past recommendation history | start_date, end_date |
| GET | `/health` | Check server status | |

> Detailed parameters and response formats for each endpoint can be found at <http://127.0.0.1:8000/docs> after running the server.

