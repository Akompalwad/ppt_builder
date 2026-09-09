"""Local Ollama provider using its OpenAI-compatible API."""
from __future__ import annotations

import json
import logging
import httpx

from app.llm.base import BaseLLMProvider
from app.llm.nvidia import _extract_json_object


class OllamaProviderError(RuntimeError):
    pass


logger=logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    def __init__(self, *, base_url: str, model: str, timeout: float = 180, debug_responses: bool = False):
        if not model:
            raise OllamaProviderError("OLLAMA_MODEL is not configured")
        self.base_url, self.model, self.timeout, self.debug_responses=base_url.rstrip("/"), model, timeout, debug_responses

    def generate_text(self, prompt: str, **kwargs: object) -> str:
        payload={
            "model":kwargs.get("model") or self.model,
            "messages":[{"role":"user","content":prompt}],
            "stream":False,
            "format":"json" if kwargs.get("response_format") else None,
            "think":False,
            "options":{"temperature":kwargs.get("temperature", .15),"num_predict":kwargs.get("max_tokens", 2500)},
        }
        if payload["format"] is None:
            payload.pop("format")
        try:
            # Ollama's native endpoint supports both JSON format enforcement
            # and disabling thinking for Qwen-family models.
            native_base=self.base_url.removesuffix("/v1")
            response=httpx.post(f"{native_base}/api/chat", json=payload, timeout=self.timeout)
            if self.debug_responses and response.is_error:
                logger.warning("Ollama request failed model=%s status=%s response=%r", payload["model"], response.status_code, response.text[:5000])
            response.raise_for_status()
            result=response.json(); message=result.get("message") or {}; content=message.get("content") or ""
            if self.debug_responses:
                logger.info("Ollama response model=%s done_reason=%s content=%r", result.get("model", payload["model"]), result.get("done_reason"), content[:5000])
            return content
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise OllamaProviderError("Local Ollama generation request failed.") from exc

    def generate_json(self, prompt: str, **kwargs: object) -> dict:
        raw=self.generate_text(
            prompt+"\nReturn one complete JSON object only. Do not include analysis or Markdown.",
            response_format={"type":"json_object"}, **kwargs,
        )
        try:
            return _extract_json_object(raw)
        except json.JSONDecodeError as exc:
            if self.debug_responses:
                logger.warning("Ollama JSON parse failed model=%s raw_content=%r", self.model, raw[:5000])
            raise OllamaProviderError("Local Ollama returned invalid JSON.") from exc
