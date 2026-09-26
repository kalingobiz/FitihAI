"""Google Gemini implementation of the LegalModel interface.

Uses the google-genai SDK. Reads GEMINI_API_KEY (or GOOGLE_API_KEY).

Free-tier note: on the Gemini API free tier, Google may use prompts and
responses to improve its products. That is fine for development and for public
law text, but before real users send personal documents, switch the project to
a paid (billing-enabled) tier or to FITIH_LLM_PROVIDER=claude.
"""

from __future__ import annotations

from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from .config import Settings
from .llm import IMAGE_TYPES, PDF_TYPE, ModelRefusal
from .prompts import ANALYZE_SYSTEM, ANSWER_SYSTEM, OCR_SYSTEM, ROUTER_SYSTEM
from .schemas import Answer, DocumentAnalysis, Route

T = TypeVar("T", bound=BaseModel)

# Retry rate limits (free tier) and transient server errors.
RETRY = types.HttpRetryOptions(attempts=4, initial_delay=2.0, max_delay=30.0,
                               http_status_codes=[429, 500, 502, 503, 504])

# Legal questions routinely mention violence, crime and abuse. Only block
# content Google rates as high-probability harm, so victims can still ask.
SAFETY = [
    types.SafetySetting(category=c, threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH)
    for c in (
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    )
]

_BLOCKED_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def to_contents(history: list[dict], user_text: str) -> list[types.Content]:
    """Convert our {'role': 'user'|'assistant'} history to Gemini contents."""
    contents = [
        types.Content(role="model" if m["role"] == "assistant" else "user",
                      parts=[types.Part.from_text(text=m["content"])])
        for m in history
    ]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
    return contents


def _finish_reason(response) -> str:
    try:
        reason = response.candidates[0].finish_reason
        return getattr(reason, "name", str(reason or ""))
    except (IndexError, TypeError, AttributeError):
        return ""


class GeminiLegalModel:
    def __init__(self, settings: Settings, client: genai.Client | None = None):
        self.s = settings
        self._client = client

    @property
    def client(self) -> genai.Client:
        # Created on first use, so the app (admin console, health) runs before a key is configured.
        if self._client is None:
            self._client = genai.Client(http_options=types.HttpOptions(retry_options=RETRY))
        return self._client

    def _generate(self, *, model: str, system: str, contents, schema: type[T] | None,
                  max_tokens: int):
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            safety_settings=SAFETY,
            **({"response_mime_type": "application/json", "response_schema": schema} if schema else {}),
        )
        response = self.client.models.generate_content(model=model, contents=contents, config=config)
        feedback = getattr(response, "prompt_feedback", None)
        if feedback is not None and getattr(feedback, "block_reason", None):
            raise ModelRefusal(f"blocked by Gemini: {feedback.block_reason}")
        reason = _finish_reason(response)
        if reason in _BLOCKED_REASONS:
            raise ModelRefusal(f"blocked by Gemini: {reason}")
        if reason == "MAX_TOKENS":
            raise RuntimeError("incomplete model output (MAX_TOKENS)")
        return response

    def _parse(self, *, schema: type[T], **kwargs) -> T:
        response = self._generate(schema=schema, **kwargs)
        parsed = response.parsed
        if isinstance(parsed, schema):
            return parsed
        if isinstance(parsed, dict):
            return schema.model_validate(parsed)
        # Fall back to the raw JSON text if the SDK could not parse it.
        return schema.model_validate_json(response.text or "")

    # ---- LegalModel ------------------------------------------------------------
    def route(self, message: str, history: list[dict]) -> Route:
        context = ""
        if history:
            recent = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in history[-4:])
            context = f"<conversation_so_far>\n{recent}\n</conversation_so_far>\n\n"
        return self._parse(
            model=self.s.gemini_fast_model, system=ROUTER_SYSTEM, schema=Route, max_tokens=2048,
            contents=to_contents([], f"{context}<message>\n{message}\n</message>"),
        )

    def answer(self, user_content: str, history: list[dict]) -> Answer:
        return self._parse(
            model=self.s.gemini_reasoning_model, system=ANSWER_SYSTEM, schema=Answer, max_tokens=16000,
            contents=to_contents(history, user_content),
        )

    def analyze(self, user_content: str) -> DocumentAnalysis:
        return self._parse(
            model=self.s.gemini_reasoning_model, system=ANALYZE_SYSTEM, schema=DocumentAnalysis,
            max_tokens=24000, contents=to_contents([], user_content),
        )

    def transcribe(self, data: bytes, media_type: str) -> str:
        if media_type not in IMAGE_TYPES | {PDF_TYPE}:
            raise ValueError(f"unsupported file type: {media_type}")
        response = self._generate(
            model=self.s.gemini_ocr_model, system=OCR_SYSTEM, schema=None, max_tokens=16000,
            contents=[types.Part.from_bytes(data=data, mime_type=media_type), "Transcribe this document."],
        )
        return (response.text or "").strip()
