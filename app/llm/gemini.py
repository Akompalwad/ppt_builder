"""Google Gemini API provider with structured-output and usage-aware throttling."""
from __future__ import annotations

import json
import logging
import httpx

from app.llm.base import BaseLLMProvider
from app.llm.nvidia import _extract_json_object
from app.llm.rate_limit import estimate_request_tokens, shared_rate_gate

logger=logging.getLogger(__name__)


class GeminiProviderError(RuntimeError):
    pass


class GeminiProvider(BaseLLMProvider):
    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float, tokens_per_minute: int, requests_per_minute: int, queue_max_wait_seconds: float, debug_responses: bool=False):
        if not api_key:
            raise GeminiProviderError("GEMINI_API_KEY is not configured")
        self.api_key=api_key; self.base_url=base_url.rstrip("/"); self.model=model
        self.timeout=timeout; self.debug_responses=debug_responses
        self.gate=shared_rate_gate(f"gemini:{model}",tokens_per_minute=tokens_per_minute,requests_per_minute=requests_per_minute,max_wait_seconds=queue_max_wait_seconds)

    def generate_text(self, prompt: str, **kwargs: object) -> str:
        max_tokens=int(kwargs.get("max_tokens",800))
        payload={
            "contents":[{"parts":[{"text":prompt}]}],
            "generationConfig":{
                "temperature":kwargs.get("temperature",.1),
                "maxOutputTokens":max_tokens,
                "thinkingConfig":{"thinkingLevel":"minimal"},
            },
        }
        if kwargs.get("response_format"):
            payload["generationConfig"]["responseMimeType"]="application/json"
        reservation=self.gate.reserve(estimate_request_tokens(prompt,max_tokens))
        actual_tokens=0
        try:
            response=httpx.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                headers={"x-goog-api-key":self.api_key,"Content-Type":"application/json"},
                json=payload, timeout=self.timeout,
            )
            response.raise_for_status(); result=response.json()
            actual_tokens=int(result.get("usageMetadata",{}).get("totalTokenCount",0))
            parts=result["candidates"][0]["content"]["parts"]
            content="".join(str(part.get("text", "")) for part in parts if not part.get("thought"))
            if not content.strip():
                raise GeminiProviderError("Gemini returned no final answer after its thinking segment.")
            if self.debug_responses:
                logger.info("Gemini response model=%s finish_reason=%s tokens=%s content=%r",self.model,result["candidates"][0].get("finishReason"),actual_tokens,content[:5000])
            return content
        except httpx.HTTPStatusError as exc:
            if self.debug_responses:
                logger.warning("Gemini request failed model=%s status=%s response=%r",self.model,exc.response.status_code,exc.response.text[:1000])
            raise GeminiProviderError(f"Gemini returned HTTP {exc.response.status_code}.") from exc
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            if isinstance(exc, GeminiProviderError):
                raise
            raise GeminiProviderError("Gemini generation request could not be completed.") from exc
        finally:
            self.gate.settle(reservation,actual_tokens)

    def generate_json(self, prompt: str, **kwargs: object) -> dict:
        raw=self.generate_text(prompt+"\nReturn one complete JSON object only. Do not include analysis or Markdown.",response_format={"type":"json_object"},**kwargs)
        try:
            payload=json.loads(raw)
            if isinstance(payload,list) and len(payload)==1 and isinstance(payload[0],dict):
                return payload[0]
            if isinstance(payload,dict):
                return payload
        except json.JSONDecodeError:
            pass
        try:
            return _extract_json_object(raw)
        except json.JSONDecodeError as exc:
            raise GeminiProviderError("Gemini returned invalid JSON.") from exc
