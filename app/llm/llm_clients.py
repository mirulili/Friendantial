# app/llm/llm_clients.py

from abc import ABC, abstractmethod
from typing import Dict, List

import google.generativeai as genai
import openai


class AbstractLLMClient(ABC):
    """
    LLM 클라이언트의 추상 기본 클래스입니다.
    모든 구체적인 LLM 클라이언트는 이 인터페이스를 구현해야 합니다.
    """

    @abstractmethod
    async def generate_chat_completion(
        self, messages: List[Dict[str, str]], model: str
    ) -> str:
        """
        주어진 메시지를 사용하여 LLM으로부터 채팅 응답을 생성합니다.
        """
        pass

    async def close(self):
        pass


class OpenAIChatClient(AbstractLLMClient):
    """
    OpenAI API를 사용하는 LLM 클라이언트 구현체입니다.
    """

    def __init__(self, api_key: str):
        self._client = openai.AsyncClient(api_key=api_key)

    async def generate_chat_completion(
        self, messages: List[Dict[str, str]], model: str
    ) -> str:
        chat_completion = await self._client.chat.completions.create(
            messages=messages,
            model=model,
        )
        return chat_completion.choices[0].message.content

    async def close(self):
        await self._client.close()


class GeminiChatClient(AbstractLLMClient):
    """
    Google Gemini API를 사용하는 LLM 클라이언트 구현체입니다.
    """

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self._model = None

    async def generate_chat_completion(
        self, messages: List[Dict[str, str]], model: str
    ) -> str:
        # Gemini: model 객체 먼저 생성
        if self._model is None or self._model.model_name != model:
            self._model = genai.GenerativeModel(model)

        # OpenAI의 'system' 역할을 Gemini 형식에 맞게 변환
        # 간단히 첫 메시지를 시스템 프롬프트로 간주
        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        response = await self._model.generate_content_async(prompt)
        return response.text

    async def close(self):
        pass
