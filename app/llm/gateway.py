from app.config import get_settings
from app.llm.base import BaseLLMProvider
from app.llm.nvidia import NvidiaProvider
from app.llm.ollama import OllamaProvider
from app.llm.gemini import GeminiProvider
class LLMGateway:
    def __init__(self, provider: BaseLLMProvider): self.provider = provider
    def generate_text(self, prompt: str, **kwargs: object) -> str: return self.provider.generate_text(prompt, **kwargs)
    def generate_json(self, prompt: str, **kwargs: object) -> dict: return self.provider.generate_json(prompt, **kwargs)
    def generate_structured(self, prompt: str, schema: type, **kwargs: object): return schema.model_validate(self.generate_json(prompt, **kwargs))
    def healthcheck(self) -> dict[str, str]:
        """Prove that the configured provider can complete a real inference request."""
        answer=self.generate_text("Reply only: OK", max_tokens=32)
        return {"status":"available", "response":answer[:80]}
    @classmethod
    def from_settings(cls, provider_override: str | None = None, model_override: str | None = None) -> "LLMGateway":
        settings=get_settings(); provider=(provider_override or settings.llm_provider).lower()
        if provider=="nvidia": return cls(NvidiaProvider(api_key=settings.nvidia_api_key,base_url=settings.nvidia_base_url,model=model_override or settings.nvidia_model,timeout=settings.nvidia_timeout_seconds,debug_responses=settings.nvidia_debug_responses))
        if provider=="gemini": return cls(GeminiProvider(api_key=settings.gemini_api_key,base_url=settings.gemini_base_url,model=model_override or settings.gemini_model,timeout=settings.gemini_timeout_seconds,tokens_per_minute=settings.gemini_tokens_per_minute,requests_per_minute=settings.gemini_requests_per_minute,queue_max_wait_seconds=settings.gemini_queue_max_wait_seconds,debug_responses=settings.gemini_debug_responses))
        if provider=="ollama": return cls(OllamaProvider(base_url=settings.ollama_base_url,model=model_override or settings.ollama_model,debug_responses=settings.ollama_debug_responses))
        raise ValueError(f"Unsupported LLM provider: {provider}")
