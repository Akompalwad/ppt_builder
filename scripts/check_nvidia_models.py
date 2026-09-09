#!/usr/bin/env python3
"""Probe NVIDIA models that are relevant to SlideWeaver with minimal token use.

Requires NVIDIA_API_KEY in the environment. This tests account routing/access,
not qualitative model performance. Each probe asks for at most 32 tokens.
"""
from __future__ import annotations
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODELS = [
    "nvidia/nemotron-3.5-lightning-30b-a3b",  # verified baseline
    "moonshotai/kimi-k2.6",                    # strong long-form planning
    "google/gemma-4-31b-it",                   # efficient general instruction
    "openai/gpt-oss-120b",                     # strong general reasoning
    "nvidia/nemotron-3-super-120b-a12b",       # quality-first NVIDIA option
    "deepseek-ai/deepseek-v4-flash-0731",      # latency-oriented option
]
URL = "https://integrate.api.nvidia.com/v1/chat/completions"

def probe(model: str, api_key: str) -> tuple[str, str]:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Reply only: OK"}], "max_tokens": 32}).encode()
    request = Request(URL, data=body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=45) as response:
            data = json.loads(response.read())
        message = data["choices"][0]["message"].get("content", "").replace("\n", " ")[:72]
        return "AVAILABLE", message or "responded (possibly reasoning-only)"
    except HTTPError as error:
        detail = error.read().decode("utf-8", "replace").replace("\n", " ")[:120]
        # Capacity outages say nothing about account entitlement. Keep them
        # distinct from 404/410 model-access failures.
        state="TRANSIENT" if error.code in {429, 502, 503, 504} else "UNAVAILABLE"
        return state, f"HTTP {error.code}: {detail}"
    except (URLError, TimeoutError, KeyError, ValueError) as error:
        return "TRANSIENT", str(error)[:140]

def main() -> int:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("NVIDIA_API_KEY is not set. Run: set -a; source .env; set +a")
        return 2
    print("Probing candidate models (one 32-token request each):\n")
    for model in MODELS:
        state, detail = probe(model, api_key)
        print(f"{state:<11} {model}\n  {detail}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
