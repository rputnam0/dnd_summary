from __future__ import annotations

from google import genai
from google.genai import types

from dnd_summary.config import settings


class LLMClient:
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError("Missing Gemini API key (set DND_GEMINI_API_KEY).")
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def generate_json(self, prompt: str, *, system: str | None = None) -> str:
        response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                system_instruction=[system] if system else None,
            ),
        )
        return response.text or ""

    def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="text/plain",
                system_instruction=[system] if system else None,
            ),
        )
        return response.text or ""

    def generate_json_schema(
        self,
        prompt: str,
        *,
        schema: types.Schema,
        system: str | None = None,
    ) -> str:
        response = self._client.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                system_instruction=[system] if system else None,
            ),
        )
        return response.text or ""
