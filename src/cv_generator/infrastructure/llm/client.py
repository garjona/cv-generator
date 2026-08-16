from __future__ import annotations

import logging

from cv_generator.config import Settings


class NullLLMClient:
    def is_available(self) -> bool:
        return False

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str | None:
        return None


class OpenAILLMClient:
    def __init__(self, api_key: str, model: str, timeout_seconds: int = 45) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._logger = logging.getLogger("cv_generator")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI  # type: ignore

            self._client = OpenAI(api_key=self.api_key, timeout=self.timeout_seconds)
        return self._client

    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str | None:
        try:
            client = self._get_client()
            response = client.responses.create(
                model=self.model,
                temperature=temperature,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = getattr(response, "output_text", None)
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception as exc:
            self._logger.warning("Fallo llamada OpenAI; se aplicará fallback determinístico. %s", exc)
        return None


def build_llm_client(settings: Settings):
    if not settings.enable_llm or not settings.openai_api_key:
        return NullLLMClient()
    return OpenAILLMClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
    )
