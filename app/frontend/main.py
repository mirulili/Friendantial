# frontend/main.py

import os

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

from urllib.parse import quote
# 백엔드 API 주소 (Docker 환경 고려)
# 로컬 실행 시: http://localhost:8000
# Docker Compose 실행 시: http://api:8000 (서비스명 사용)
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Friendantial", page_icon="🐵", layout="wide")

st.title("🐵 Friendantial: 내 손안의 AI 투자 친구")

# 사이드바: 설정
with st.sidebar:
    st.header("투자 설정")
    persona = st.selectbox("페르소나 선택", ["friend", "analyst"], index=0)
    strategy = st.selectbox("투자 전략", ["day_trader", "long_term_trader"], index=0)
    st.info(f"현재 모드: {persona.upper()} / {strategy}")

# 탭 구성
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 오늘의 추천", "📈 개별 종목 분석", "💬 종목 상담 (RAG)", "📂 추천 이력", "🔬 백테스트"]
)

# --- 탭 1: 추천 및 리포트 ---
with tab1:
    st.subheader("오늘의 추천 및 AI 리포트")
    st.header("오늘의 추천 포트폴리오")

    if st.button("추천 종목 분석 시작 🚀"):
        with st.spinner("시장 데이터를 분석하고 AI 리포트를 작성 중입니다..."):
            try:
                # 1. 요약 리포트 요청
                response = requests.get(
                    f"{API_URL}/reporting/summary?strategy={strategy}&persona={persona}",
                )
                response.raise_for_status()
                report_data = response.json()
                report_content = report_data.get("report", "")

                # AI 리포트 출력
                st.markdown("### 📝 AI 투자 리포트")
                st.markdown(report_content)

                # 2. 추천 종목 목록 요청
                reco_response = requests.get(
                    f"{API_URL}/basic_analysis/recommendations?strategy={strategy}",
                )
                reco_response.raise_for_status()
                reco_data = reco_response.json()
                candidates = reco_data.get("candidates", [])

                if candidates:
                    st.markdown("### ⭐ 추천 종목 TOP 5")
                    df = pd.DataFrame(candidates)
                    st.dataframe(
                        df[["name", "code", "score", "stars", "reason", "price"]]
                    )
            except Exception as e:
                st.error(f"서버 연결 오류: {e}")

# --- 탭 2: 개별 종목 분석 ---
with tab2:
    st.header("개별 종목 심층 분석")
    stock_code_input = st.text_input(
        "분석할 종목의 코드를 입력하세요.", "005930.KS", key="stock_analysis_input"
    )

    if st.button("분석 실행", key="run_stock_analysis"):
        if not stock_code_input:
            st.warning("종목 코드 또는 이름을 입력해주세요.")
        else:
            with st.spinner(f"{stock_code_input} 종목을 분석 중입니다..."):
                try:
                    encoded_input = quote(stock_code_input)
                    # 심층 분석 리포트 생성 API 호출
                    report_url = (
                        f"{API_URL}/reporting/stock/{encoded_input}?persona={persona}"
                    )
                    response = requests.get(report_url)
                    response.raise_for_status()
                    report_data = response.json()

                    st.subheader("📝 AI 심층 분석 리포트")
                    st.markdown(report_data.get("report", "리포트 생성에 실패했습니다."))

                    # 상세 데이터 (차트, 기술적 지표, 뉴스) 요청
                    with st.expander("상세 데이터 보기 (차트, 지표, 뉴스)"):
                        # 여러 API를 동시에 호출
                        urls = {
                            "ohlcv": f"{API_URL}/market-data/ohlcv/{encoded_input}",
                            "tech": f"{API_URL}/basic_analysis/technical-indicator/{encoded_input}",
                            "news": f"{API_URL}/basic_analysis/news-sentiment/{encoded_input}",
                        }
                        
                        # 모든 요청을 한 번에 보냅니다.
                        responses = {
                            name: requests.get(url) for name, url in urls.items()
                        }

                        # 각 응답을 처리합니다.
                        ohlcv_data = responses["ohlcv"].json() if responses["ohlcv"].status_code == 200 else {}
                        tech_data = responses["tech"].json() if responses["tech"].status_code == 200 else {}
                        news_data = responses["news"].json() if responses["news"].status_code == 200 else {}

                        # 탭으로 상세 데이터 구성
                        tab_chart, tab_tech, tab_news = st.tabs(["📈 가격 차트", "🛠️ 기술 지표", "📰 뉴스 분석"])

                        with tab_chart:
                            if ohlcv_data:
                                df_ohlcv = pd.DataFrame.from_dict(ohlcv_data, orient='index')
                                df_ohlcv.index = pd.to_datetime(df_ohlcv.index)

                                # 이동평균선 계산
                                ma5 = df_ohlcv['close'].rolling(window=5).mean()
                                ma20 = df_ohlcv['close'].rolling(window=20).mean()
                                ma60 = df_ohlcv['close'].rolling(window=60).mean()

                                # 캔들스틱 차트 생성
                                fig = go.Figure(data=[go.Candlestick(x=df_ohlcv.index,
                                                open=df_ohlcv['open'],
                                                high=df_ohlcv['high'],
                                                low=df_ohlcv['low'],
                                                close=df_ohlcv['close'],
                                                name='OHLC')])

                                # 이동평균선 트레이스 추가
                                fig.add_trace(go.Scatter(x=df_ohlcv.index, y=ma5, mode='lines', name='MA5', line=dict(color='orange', width=1)))
                                fig.add_trace(go.Scatter(x=df_ohlcv.index, y=ma20, mode='lines', name='MA20', line=dict(color='purple', width=1)))
                                fig.add_trace(go.Scatter(x=df_ohlcv.index, y=ma60, mode='lines', name='MA60', line=dict(color='cyan', width=1)))

                                fig.update_layout(
                                    title=f'{stock_code_input} 가격 및 이동평균선',
                                    xaxis_title='날짜',
                                    yaxis_title='가격',
                                    xaxis_rangeslider_visible=False,
                                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                                )
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.warning("차트 데이터를 불러오지 못했습니다.")

                        with tab_tech:
                            if tech_data:
                                st.json(tech_data)
                            else:
                                st.warning("기술적 지표 데이터를 불러오지 못했습니다.")

                        with tab_news:
                            if news_data:
                                st.text(news_data.get("summary", "요약 정보 없음"))
                                if news_data.get("details"):
                                    df_news = pd.DataFrame(news_data["details"])
                                    st.dataframe(df_news)
                            else:
                                st.warning("뉴스 데이터를 불러오지 못했습니다.")
                except Exception as e:
                    st.error(f"분석 중 오류 발생: {e}")


# --- 탭 3: RAG 질의응답 ---
with tab3:
    st.header("종목 무엇이든 물어보세요")
    st.caption("최신 뉴스를 기반으로 근거 있는 답변을 제공합니다.")

    # 사용자 입력
    stock_code = st.text_input("종목 코드 (예: 005930.KS)", "005930.KS")
    question = st.text_input("질문 내용", "요즘 삼성전자 왜 이렇게 떨어져?")

    if st.button("질문하기"):
        if not stock_code or not question:
            st.warning("종목 코드와 질문을 모두 입력해주세요.")
        else:
            with st.spinner("최신 뉴스를 검색하고 답변을 생성 중입니다..."):
                try:
                    # RAG API 호출
                    response = requests.get(
                        f"{API_URL}/opinion/{stock_code}",
                        params={
                            "question": question,
                            "persona": persona,
                        },
                    )

                    if response.status_code == 200:
                        result = response.json()
                        answer = result.get("answer", "")
                        context_docs = result.get("context_used", [])

                        # 답변 출력 (채팅 스타일)
                        with st.chat_message("assistant", avatar="🐵"):
                            st.markdown(answer)

                        # 참고 문헌(뉴스) 표시
                        with st.expander("📚 참고한 뉴스 기사 보기"):
                            for doc in context_docs:
                                st.write(f"- {doc}")
                    else:
                        st.error("답변 생성에 실패했습니다.")
                except Exception as e:
                    st.error(f"오류 발생: {e}")

# --- 탭 4: 추천 이력 ---
with tab4:
    st.header("과거 추천 이력 조회")
    if st.button("이력 조회"):
        with st.spinner("과거 추천 기록을 불러오는 중입니다..."):
            try:
                response = requests.get(f"{API_URL}/history/recommendations?limit=50")
                response.raise_for_status()
                history_data = response.json()

                if not history_data:
                    st.warning("저장된 추천 이력이 없습니다.")
                else:
                    for run in history_data:
                        st.subheader(f"🗓️ 추천일: {run['as_of']}")
                        if run["stocks"]:
                            df = pd.DataFrame(run["stocks"])
                            st.dataframe(
                                df[
                                    [
                                        "name",
                                        "code",
                                        "score",
                                        "reason",
                                        "momentum",
                                    ]
                                ]
                            )
                        else:
                            st.text("추천된 종목이 없습니다.")
                        st.divider()
            except Exception as e:
                st.error(f"이력 조회 중 오류 발생: {e}")

# --- 탭 5: 백테스트 ---
with tab5:
    st.header("투자 전략 시뮬레이션 (백테스트)")
    st.caption("선택한 전략이 과거에 어땠을지 확인해봅니다.")

    target_date = st.date_input("백테스트 기준일")
    backtest_strategy = st.selectbox(
        "백테스트 전략", ["day_trader", "long_term"], index=0
    )

    if st.button("백테스트 실행"):
        with st.spinner(f"{target_date} 기준으로 백테스트를 실행합니다..."):
            try:
                response = requests.get(
                    f"{API_URL}/backtest/simulate",
                    params={
                        "target_date": target_date.strftime("%Y-%m-%d"),
                        "strategy": backtest_strategy,
                    },
                )
                response.raise_for_status()
                result_data = response.json()
                backtest_results = result_data.get("backtest_result", [])

                if not backtest_results:
                    st.warning("백테스트 결과가 없습니다. 추천된 종목이 없었을 수 있습니다.")
                else:
                    st.subheader("📈 백테스트 결과")
                    df = pd.DataFrame(backtest_results)
                    st.dataframe(df)
            except Exception as e:
                st.error(f"백테스트 중 오류 발생: {e}")
