# app/llm/prompt_builder.py

from typing import Any

from jinja2 import Environment


def build_prompt(jinja_env: Environment, template_name: str, **kwargs: Any) -> str:
    """
    Jinja2 템플릿을 사용하여 프롬프트를 생성합니다.
    데이터 포매팅(XML 구조 등)은 템플릿 내부에서 처리합니다.
    """
    template = jinja_env.get_template(template_name)
    return template.render(**kwargs)
