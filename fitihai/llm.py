"""Thin wrapper over the Anthropic SDK (and optional Gemini OCR).

The pipeline depends only on the `LegalModel` protocol, so tests can swap in a
fake and a different provider can be added without touching the pipeline.
"""

from __future__ import annotations

import base64
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel

from .config import Settings
from .prompts import ANALYZE_SYSTEM, ANSWER_SYSTEM, OCR_SYSTEM, ROUTER_SYSTEM
from .schemas import Answer, DocumentAnalysis, Route

T = TypeVar("T", bound=BaseModel)

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
PDF_TYPE = "application/pdf"


class ModelRefusal(RuntimeError):
    pass


class LegalModel(Protocol):
    def route(self, message: str, history: list[dict]) -> Route: ...
    def answer(self, user_content: str, history: list[dict]) -> Answer: ...
    def analyze(self, user_content: str) -> DocumentAnalysis: ...
    def transcribe(self, data: bytes, media_type: str) -> str: ...


class ClaudeLegalModel:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None):
        self.s = settings
        self.client = client or anthropic.Anthropic(max_retries=3)
        self._gemini = None

    # ---- helpers --------------------------------------------------------------
    def _parse(self, *, model: str, system: str, messages: list[dict], schema: type[T],
               max_tokens: int, effort: str | None = None, thinking: bool = False) -> T:
        kwargs: dict = {}
        if effort:
            kwargs["output_config"] = {"effort": effort}
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        response = self.client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_format=schema,
            **kwargs,
        )
        if response.stop_reason == "refusal":
            raise ModelRefusal("the model declined this request")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise RuntimeError(f"incomplete model output (stop_reason={response.stop_reason})")
        return response.parsed_output

    # ---- LegalModel ---------------------------------------------------------------
    def route(self, message: str, history: list[dict]) -> Route:
        context = ""
        if history:
            recent = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in history[-4:])
            context = f"<conversation_so_far>\n{recent}\n</conversation_so_far>\n\n"
        return self._parse(
            model=self.s.fast_model,
            system=ROUTER_SYSTEM,
            messages=[{"role": "user", "content": f"{context}<message>\n{message}\n</message>"}],
            schema=Route,
            max_tokens=1024,
        )

    def answer(self, user_content: str, history: list[dict]) -> Answer:
        messages = [*history, {"role": "user", "content": user_content}]
        return self._parse(
            model=self.s.reasoning_model,
            system=ANSWER_SYSTEM,
            messages=messages,
            schema=Answer,
            max_tokens=16000,
            effort="medium",
            thinking=True,
        )

    def analyze(self, user_content: str) -> DocumentAnalysis:
        return self._parse(
            model=self.s.reasoning_model,
            system=ANALYZE_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
            schema=DocumentAnalysis,
            max_tokens=16000,
            effort="high",
            thinking=True,
        )

    def transcribe(self, data: bytes, media_type: str) -> str:
        if self.s.ocr_provider == "gemini":
            return self._transcribe_gemini(data, media_type)
        b64 = base64.standard_b64encode(data).decode("ascii")
        if media_type == PDF_TYPE:
            block = {"type": "document", "source": {"type": "base64", "media_type": PDF_TYPE, "data": b64}}
        elif media_type in IMAGE_TYPES:
            block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}
        else:
            raise ValueError(f"unsupported file type: {media_type}")
        response = self.client.messages.create(
            model=self.s.ocr_model,
            max_tokens=16000,
            system=OCR_SYSTEM,
            messages=[{"role": "user", "content": [block, {"type": "text", "text": "Transcribe this document."}]}],
        )
        if response.stop_reason == "refusal":
            raise ModelRefusal("the model declined to transcribe this document")
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def _transcribe_gemini(self, data: bytes, media_type: str) -> str:
        """Optional Gemini OCR path, for A/B-testing Ethiopic OCR quality."""
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("FITIH_OCR_PROVIDER=gemini requires `pip install google-genai`") from exc
        if self._gemini is None:
            self._gemini = genai.Client()  # reads GEMINI_API_KEY
        result = self._gemini.models.generate_content(
            model=self.s.gemini_ocr_model,
            contents=[types.Part.from_bytes(data=data, mime_type=media_type), OCR_SYSTEM],
        )
        return (result.text or "").strip()
