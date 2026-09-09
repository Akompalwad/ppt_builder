"""NVIDIA NIM provider using its OpenAI-compatible chat completions API."""
from __future__ import annotations
import json, logging, re, time
import httpx
from app.llm.base import BaseLLMProvider

class NVIDIAProviderError(RuntimeError): pass
logger=logging.getLogger(__name__)


def _extract_json_object(raw: str) -> dict:
    """Recover a complete JSON object when a reasoning model adds prose/tags.

    Some NVIDIA-hosted models emit a short reasoning preamble despite JSON mode.
    We only accept a balanced, independently parseable top-level object; no
    partial JSON is silently repaired into a slide specification.
    """
    cleaned=re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    # Nemotron occasionally emits a duplicated opening object marker after a
    # JSON-only retry. It can be compact (`{{"title"...}`) or split over
    # lines (`{\n{\n"title"...}`). Remove only that exact prefix; arbitrary
    # malformed JSON is still rejected below.
    if re.match(r'^\{\s*\{\s*"', cleaned):
        cleaned=re.sub(r'^\{\s*', '', cleaned, count=1)
    try:
        payload=json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    candidates: list[tuple[int, dict]]=[]
    for start, character in enumerate(cleaned):
        if character != "{":
            continue
        depth=0; in_string=False; escaped=False
        for end in range(start, len(cleaned)):
            current=cleaned[end]
            if in_string:
                if escaped: escaped=False
                elif current == "\\": escaped=True
                elif current == '"': in_string=False
                continue
            if current == '"': in_string=True
            elif current == "{": depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    try:
                        payload=json.loads(cleaned[start:end+1])
                        if isinstance(payload, dict): candidates.append((end-start, payload))
                    except json.JSONDecodeError:
                        pass
                    break
    if candidates:
        return max(candidates, key=lambda candidate: candidate[0])[1]
    raise json.JSONDecodeError("No complete JSON object in NVIDIA response", cleaned, 0)

class NvidiaProvider(BaseLLMProvider):
    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float = 120, retries: int = 3, debug_responses: bool = False):
        if not api_key: raise NVIDIAProviderError("NVIDIA_API_KEY is not configured")
        self.api_key, self.base_url, self.model = api_key, base_url.rstrip("/"), model
        self.timeout, self.retries, self.debug_responses = timeout, retries, debug_responses
    def generate_text(self, prompt: str, **kwargs: object) -> str:
        payload={"model":kwargs.get("model") or self.model,"messages":[{"role":"user","content":prompt}],"temperature":kwargs.get("temperature",.25),"max_tokens":kwargs.get("max_tokens",2500)}
        if response_format:=kwargs.get("response_format"):
            payload["response_format"]=response_format
        headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"}
        for attempt in range(self.retries+1):
            try:
                response=httpx.post(f"{self.base_url}/chat/completions",json=payload,headers=headers,timeout=self.timeout); response.raise_for_status()
                result=response.json(); choice=result["choices"][0]; message=choice["message"]
                content=message.get("content") or ""
                if self.debug_responses:
                    logger.info(
                        "NVIDIA response model=%s finish_reason=%s content=%r",
                        result.get("model", payload["model"]), choice.get("finish_reason"), content[:5000],
                    )
                return content
            except httpx.TimeoutException as exc:
                if attempt==self.retries: raise NVIDIAProviderError("NVIDIA request timed out; try again or use a smaller deck.") from exc
                time.sleep(2**attempt)
            except httpx.HTTPStatusError as exc:
                if self.debug_responses:
                    logger.warning(
                        "NVIDIA request failed model=%s status=%s response=%r",
                        payload["model"], exc.response.status_code, exc.response.text[:1000],
                    )
                retryable=exc.response.status_code in {429, 502, 503, 504}
                if attempt==self.retries or not retryable:
                    raise NVIDIAProviderError(f"NVIDIA returned HTTP {exc.response.status_code} for model {payload['model']}.") from exc
                retry_after=exc.response.headers.get("Retry-After")
                delay=min(30, float(retry_after)) if retry_after and retry_after.isdigit() else 2**attempt
                logger.warning("NVIDIA returned HTTP %s; retrying in %ss (%s/%s)", exc.response.status_code, delay, attempt+1, self.retries)
                time.sleep(delay)
            except (httpx.RequestError, KeyError, ValueError) as exc:
                if attempt==self.retries: raise NVIDIAProviderError("NVIDIA generation request could not be completed.") from exc
                time.sleep(2**attempt)
        raise AssertionError("unreachable")
    def generate_json(self, prompt: str, **kwargs: object) -> dict:
        instruction=(
            prompt
            + "\nReturn one complete JSON object only. Do not include analysis, XML, Markdown fences, or explanatory text."
        )
        # A single retry is worthwhile for structured generation: it avoids
        # throwing away a deck merely because a reasoning preamble leaked.
        for attempt in range(2):
            raw=self.generate_text(
                instruction,
                response_format={"type":"json_object"},
                temperature=0 if attempt else kwargs.get("temperature", .25),
                **{key:value for key,value in kwargs.items() if key != "temperature"},
            )
            try:
                return _extract_json_object(raw)
            except json.JSONDecodeError as exc:
                if self.debug_responses:
                    logger.warning(
                        "NVIDIA JSON parse failed attempt=%s model=%s raw_content=%r",
                        attempt+1, self.model, raw[:5000],
                    )
                if attempt:
                    raise NVIDIAProviderError("NVIDIA returned incomplete JSON after a retry.") from exc
        raise AssertionError("unreachable")
