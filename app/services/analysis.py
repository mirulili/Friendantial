import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
import redis.asyncio as redis
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import MARKET, NEWS_MAX, TZ
from app.core.market_analysis import determine_market_regime
from app.core.presentation import (calculate_stock_stars,
                                   generate_friendly_reason,
                                   generate_ma_comment, scale_to_100)
from app.core.scoring import calculate_z_scores, compute_features, score_stock
from app.db.db_models import RecommendationRun, RecommendedStock
from app.schemas.enums import StrategyEnum
from app.schemas.models import FeatureConf, RecoItem, RecoResponse, StockScore
from app.services.market_data import (_fetch_stock_info, fetch_ohlcv,
                                      get_stock_name_from_code)
from app.services.sentiment import analyze_news_sentiment, fetch_news_titles
from app.services.universe import get_universe


class AnalysisService:
    """주식 분석 관련 비즈니스 로직을 처리하는 서비스입니다."""

    def __init__(
        self,
        sentiment_pipe: Any,
        http_client: httpx.AsyncClient,
        db: Session,
        redis_conn: redis.Redis,
    ):

        self.sentiment_pipe = sentiment_pipe
        self.http_client = http_client
        self.db = db
        self.redis_conn = redis_conn

    async def get_recommendations(
        self,
        n: int = 5,
        with_news: bool = True,
        strategy: StrategyEnum = StrategyEnum.DAY_TRADER,
        save_to_db: bool = True,
    ) -> RecoResponse:
        """전략에 따른 종목 추천을 실행합니다."""

        return await self._run_analysis_workflow(
            n=n,
            with_news=with_news,
            strategy=strategy,
            save_to_db=save_to_db,
        )

    async def run_backtest_recommendations(
        self,
        strategy: StrategyEnum,
        as_of: str,
        universe_codes: Optional[List[str]] = None,
    ) -> RecoResponse:
        """과거 시점 기준으로 종목 추천을 실행하는 백테스트용 메서드입니다."""

        return await self._run_analysis_workflow(
            strategy=strategy,
            as_of=as_of,
            with_news=False,  # 백테스트에서 뉴스 분석 제외
            save_to_db=False,  # 백테스트 결과 DB에 저장 안 함
            universe_codes=universe_codes,
        )

    async def _run_analysis_workflow(
        self,
        as_of: Optional[str] = None,
        n: int = 5,
        with_news: bool = True,
        strategy: StrategyEnum = StrategyEnum.DAY_TRADER,
        save_to_db: bool = True,
        universe_codes: Optional[list[str]] = None,
    ) -> RecoResponse:
        """주식 분석 및 추천을 위한 핵심 워크플로우를 실행합니다."""

        if as_of is None:
            as_of = datetime.now(TZ).date().isoformat()

        # 1. 분석 대상 종목 선정 및 데이터 수집

        if universe_codes:
            temp_universe = [(code, None) for code in universe_codes]
            codes, _ = zip(*temp_universe)
            code_to_name_map = {code: code for code in codes}

        else:
            universe = await get_universe(
                self.http_client,
                self.redis_conn,
                "KOSPI" if MARKET.upper() == "KS" else "KOSDAQ",
            )

            if not universe:
                raise HTTPException(
                    status_code=503, detail="종목 유니버스를 가져올 수 없습니다."
                )

            codes, names_list = zip(*universe)
            code_to_name_map = dict(zip(codes, names_list))

        data = await fetch_ohlcv(
            self.http_client,
            self.redis_conn,
            list(codes),
            end_date=as_of,
            lookback_days=120,
        )

        conf = FeatureConf()

        # 2. 시장 상황 분석
        market_regime = await determine_market_regime(
            self.http_client, self.redis_conn, as_of
        )

        # 3. 피쳐 계산 및 모멘텀 통계 산출
        features_map = {}
        mom_values = {
            f"mom{p}": [] for p in [conf.mom_short, conf.mom_med, conf.mom_long]
        }

        for code in codes:
            df = data.get(code)
            if df is not None and not df.empty and len(df) >= conf.mom_long + 2:
                features_map[code] = self._compute_stock_features(df, conf)
                prev = features_map[code].iloc[-2]
                for k in mom_values.keys():
                    mom_values[k].append(float(prev.get(k, 0.0)))
        mom_stats = {
            key: (pd.Series(vals).mean(), pd.Series(vals).std())
            for key, vals in mom_values.items()
        }

        # 4. 1차 스코어링 (Z-Score 기반)
        pre_scored_stocks = []
        for code, feat in features_map.items():
            prev = feat.iloc[-2]
            z_scores = calculate_z_scores(prev, mom_stats)
            stock_score = score_stock(
                code,
                code_to_name_map.get(code, code),
                feat,
                z_scores,
                0.0,
                0.0,
                conf,
                market_regime,
                strategy,
            )
            if stock_score:
                pre_scored_stocks.append(stock_score)

        if not pre_scored_stocks:
            raise HTTPException(status_code=503, detail="채점 가능한 종목이 없습니다.")

        pre_scored_stocks.sort(key=lambda x: x.score, reverse=True)
        pre_selected_codes = [s.code for s in pre_scored_stocks[:20]]

        # 5. 뉴스 감성 분석
        news_data_map = {}
        if with_news:
            all_titles = []
            batch_size = 5

            for i in range(0, len(pre_selected_codes), batch_size):
                batch_codes = pre_selected_codes[i : i + batch_size]
                tasks = [
                    fetch_news_titles(
                        self.http_client,
                        code_to_name_map.get(code) or code,
                        limit=NEWS_MAX,
                    )
                    for code in batch_codes
                ]

                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                all_titles.extend(batch_results)

                await asyncio.sleep(0.5)  # API 호출 간 지연

            for code, titles in zip(pre_selected_codes, all_titles):

                if isinstance(titles, list) and titles:
                    news_data_map[code] = await asyncio.to_thread(
                        analyze_news_sentiment, self.sentiment_pipe, titles
                    )
                else:
                    news_data_map[code] = {
                        "score": 0.0,
                        "summary": "뉴스 없음",
                        "details": [],
                    }

        # 6. 2차 스코어링: 뉴스 감성 점수와 변동성을 추가로 반영
        raw_scored_stocks = self._perform_final_scoring(
            pre_selected_codes,
            features_map,
            news_data_map,
            mom_stats,
            code_to_name_map,
            conf,
            market_regime,
            strategy,
        )

        # 7. 최종 결과 생성
        response = self._prepare_response(
            raw_scored_stocks, n, market_regime, with_news, news_data_map, as_of
        )

        # 8. 데이터베이스에 결과 저장
        if save_to_db:
            self._save_recommendation_to_db(as_of, response.candidates)
        return response

    def _perform_final_scoring(
        self,
        codes: list[str],
        features_map: dict,
        news_data_map: dict,
        mom_stats: dict,
        code_to_name_map: dict,
        conf: FeatureConf,
        market_regime: str,
        strategy: StrategyEnum,
    ) -> list[StockScore]:
        """뉴스 감성 점수와 변동성을 반영하여 최종 점수를 계산합니다."""

        news_scores = [news_data_map.get(c, {}).get("score", 0.0) for c in codes]
        vol_scores = [
            float(features_map[c]["ret1"].rolling(20).std().iloc[-2]) for c in codes
        ]
        news_mean, news_std = (
            pd.Series(news_scores).mean(),
            pd.Series(news_scores).std(),
        )
        vol_mean, vol_std = pd.Series(vol_scores).mean(), pd.Series(vol_scores).std()
        raw_scored_stocks = []

        for code in codes:
            feat = features_map[code]
            n_score = news_data_map.get(code, {}).get("score", 0.0)
            n_z = (n_score - news_mean) / news_std if news_std > 0 else 0.0
            v_val = float(feat["ret1"].rolling(20).std().iloc[-2])
            v_z = (v_val - vol_mean) / vol_std if vol_std > 0 else 0.0
            prev = feat.iloc[-2]
            z_scores = calculate_z_scores(prev, mom_stats)
            s = score_stock(
                code,
                code_to_name_map.get(code, code),
                feat,
                z_scores,
                n_z,
                v_z,
                conf,
                market_regime,
                strategy,
            )

            if s:
                raw_scored_stocks.append(s)

        return raw_scored_stocks

    def _prepare_response(
        self,
        raw_scored_stocks: list[StockScore],
        n: int,
        market_regime: str,
        with_news: bool,
        news_data_map: dict,
        as_of: str,
    ) -> RecoResponse:
        """최종 추천 결과를 RecoResponse 객체로 포맷팅합니다."""

        if not raw_scored_stocks:
            return RecoResponse(as_of=as_of, candidates=[])

        all_raw_scores = [s.score for s in raw_scored_stocks]
        min_raw, max_raw = min(all_raw_scores), max(all_raw_scores)
        scored = []

        for s in raw_scored_stocks:
            final_score = scale_to_100(s.score, min_raw, max_raw, market_regime)
            friendly_reason = generate_friendly_reason(s)
            temp_item = RecoItem(
                code=s.code,
                name=s.name,
                score=final_score,
                stars=0,
                weight=0.0,
                price=s.price,
                reason=friendly_reason,
                momentum=s.momentum,
                news_sentiment=news_data_map.get(s.code) if with_news else None,
            )
            temp_item.stars = calculate_stock_stars(temp_item, market_regime)
            scored.append(temp_item)

        scored.sort(key=lambda x: x.score, reverse=True)
        top = scored[:n]

        for item in top:
            item.weight = 1.0 / len(top)

        return RecoResponse(as_of=as_of, candidates=top)

    def _save_recommendation_to_db(self, as_of: str, items: list[RecoItem]):
        """추천 결과를 데이터베이스에 저장합니다."""

        try:
            run = RecommendationRun(as_of=datetime.strptime(as_of, "%Y-%m-%d").date())
            self.db.add(run)
            self.db.flush()

            for item in items:
                stock = RecommendedStock(
                    run_id=run.id,
                    code=item.code,
                    name=item.name,
                    score=item.score,
                    weight=item.weight,
                    reason=item.reason,
                    momentum=item.momentum,
                    news_sentiment=(
                        item.news_sentiment.model_dump()
                        if item.news_sentiment
                        and hasattr(item.news_sentiment, "model_dump")
                        else None
                    ),
                )
                self.db.add(stock)
            self.db.commit()

        except Exception as e:
            logging.error(f"DB 저장 실패: {e}")
            self.db.rollback()

    def _compute_stock_features(
        self, df: pd.DataFrame, conf: FeatureConf
    ) -> pd.DataFrame:
        """주식 데이터프레임에 기술적 지표를 계산하여 추가합니다."""
        return compute_features(df, conf)

    async def get_detailed_stock_analysis(
        self, stock_identifier: str
    ) -> Dict[str, Any]:
        """개별 종목의 기술적 분석과 뉴스 감성 분석 결과를 통합하여 반환합니다."""

        # 입력값이 코드 형식인지(.KS 또는 .KQ로 끝나는지) 확인
        is_code_format = stock_identifier.endswith((".KS", ".KQ"))

        stock_code = stock_identifier if is_code_format else None
        market_info = None
        stock_name = None
        tech_analysis = None

        # 1. 기술적 분석 (입력값이 코드 형식일 때만 수행)
        if stock_code:
            conf = FeatureConf()
            data = await fetch_ohlcv(
                self.http_client, self.redis_conn, [stock_code], lookback_days=120
            )
            # 추가: 종목의 최신 시장 정보를 가져옵니다.
            market_info = await _fetch_stock_info(
                self.http_client, self.redis_conn, stock_code
            )
            df = data.get(stock_code)

            if df is None or len(df) < conf.mom_long + 2:
                # 데이터가 부족하면 기술적 분석은 건너뜁니다.
                logging.warning(f"'{stock_code}'에 대한 기술적 분석 데이터 부족")
            else:
                features_df = self._compute_stock_features(df, conf)
                latest_features = features_df.iloc[-2]
                price = latest_features.get("close", 0)
                ma5 = latest_features.get("ma5", 0)
                ma20 = latest_features.get("ma20", 0)
                ma60 = latest_features.get("ma60", 0)
                ma_comment = generate_ma_comment(price, ma5, ma20, ma60)

                tech_analysis = {
                    "price": int(price),  # 종가
                    "ma5": round(ma5, 2),
                    "ma20": round(ma20, 2),
                    "ma60": round(ma60, 2),
                    "volatility": round(latest_features.get("ret1", 0), 4),
                    "close": int(price),
                    "rsi": round(latest_features.get("rsi", 50.0), 2),
                    "avg_vol20": round(latest_features.get("avg_vol20", 0), 2),
                    "atr_ratio": round(latest_features.get("atr_ratio", 0), 4),
                    "summary": ma_comment,
                }
        else:
            # 입력값이 종목명인 경우
            stock_name = stock_identifier

        # 2. 뉴스 감성 분석
        # 종목명이 아직 결정되지 않았다면(코드로 입력받았다면) 조회합니다.
        if not stock_name and stock_code:
            stock_name = await get_stock_name_from_code(
                self.redis_conn, self.http_client, stock_code
            )

        # 최종적으로 종목명이 있어야 뉴스 검색이 가능합니다.
        if not stock_name:
            raise ValueError(
                f"'{stock_identifier}'에 해당하는 종목명을 찾을 수 없습니다."
            )

        titles = await fetch_news_titles(self.http_client, stock_name, limit=NEWS_MAX)

        if not titles:
            news_analysis = {
                "summary": "뉴스를 찾을 수 없습니다.",
                "details": [],
            }
        else:
            news_analysis = await asyncio.to_thread(
                analyze_news_sentiment, self.sentiment_pipe, titles
            )

        return {
            "stock_code": stock_code,  # 코드 입력 시에만 값이 있음
            "stock_name": stock_name,
            "market_info": market_info,
            "technical_analysis": tech_analysis,
            "news_analysis": news_analysis,
        }
