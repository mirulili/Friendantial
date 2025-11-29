from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_http_client, get_redis_connection
from app.main import app

client = TestClient(app)


class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("Error", request=None, response=self)


@pytest.fixture
def mock_http_client():
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_redis():
    mock = AsyncMock()
    # 기본적으로 None을 반환하도록 get을 모의(Mock) (캐시 미스)
    mock.get.return_value = None
    # 아무 작업도 하지 않도록 set을 모의(Mock)
    mock.set.return_value = True
    return mock


def test_lookup_stock_info(mock_http_client, mock_redis):
    # 의존성 재정의
    app.dependency_overrides[get_http_client] = lambda: mock_http_client
    app.dependency_overrides[get_redis_connection] = lambda: mock_redis

    mock_item = {
        "srtnCd": "005930",
        "itmsNm": "Samsung Electronics",
        "mrktCtg": "KOSPI",
        "clpr": "70000",
        "fltRt": "1.5",
        "basDt": "20231027",
        "trPrc": "10000000000",  # 필요한 경우 유니버스 필터링을 위한 거래 대금 추가
    }

    mock_response_data = {
        "response": {"body": {"items": {"item": [mock_item]}, "totalCount": 1}}
    }

    # 비동기 get 메서드의 반환 값을 MockResponse로 설정
    mock_http_client.get.return_value = MockResponse(mock_response_data)

    response = client.get("/market-data/lookup/005930.KS")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "005930.KS"
    assert data["name"] == "Samsung Electronics"
    assert data["market"] == "KOSPI"

    # 재정의 정리
    app.dependency_overrides = {}


def test_lookup_stock_info_not_found(mock_http_client, mock_redis):
    app.dependency_overrides[get_http_client] = lambda: mock_http_client
    app.dependency_overrides[get_redis_connection] = lambda: mock_redis

    # 빈 응답 모의(Mock)
    mock_response_data = {
        "response": {"body": {"items": {"item": []}, "totalCount": 0}}
    }

    mock_http_client.get.return_value = MockResponse(mock_response_data)

    response = client.get("/market-data/lookup/999999.KS")

    # 주식 정보를 찾을 수 없는 경우 404를 반환
    assert response.status_code == 404

    app.dependency_overrides = {}
