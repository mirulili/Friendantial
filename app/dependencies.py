import httpx
from fastapi import Request


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """
    FastAPI의 애플리케이션 상태(app.state)에서 관리되는 httpx.AsyncClient를 주입합니다.
    """
    return request.app.state.http_client
