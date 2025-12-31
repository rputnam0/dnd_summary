from __future__ import annotations

import random
import time

from google import genai
from google.genai import errors, types

from dnd_summary.config import settings


class LLMClient:
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError("Missing Gemini API key (set DND_GEMINI_API_KEY).")
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def _is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, errors.ServerError):
            return True
        if isinstance(exc, errors.ClientError):
            status = getattr(exc, "status", None)
            return status in {408, 429}
        return False

    def _call_with_retry(self, fn):
        delay = settings.llm_retry_min_seconds
        for attempt in range(1, settings.llm_max_retries + 1):
            try:
                return fn()
            except Exception as exc:
                if attempt >= settings.llm_max_retries or not self._is_retryable(exc):
                    raise
                jitter = random.uniform(0, delay)
                time.sleep(min(delay + jitter, settings.llm_retry_max_seconds))
                delay = min(delay * settings.llm_retry_backoff, settings.llm_retry_max_seconds)

    def generate_json(self, prompt: str, *, system: str | None = None) -> str:
        def _call():
            response = self._client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    system_instruction=[system] if system else None,
                ),
            )
            return response.text or ""

        return self._call_with_retry(_call)

    def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        def _call():
            response = self._client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="text/plain",
                    system_instruction=[system] if system else None,
                ),
            )
            return response.text or ""

        return self._call_with_retry(_call)

    def generate_json_schema(
        self,
        prompt: str,
        *,
        schema: types.Schema,
        system: str | None = None,
    ) -> str:
        def _call():
            response = self._client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    system_instruction=[system] if system else None,
                ),
            )
            return response.text or ""

        return self._call_with_retry(_call)
