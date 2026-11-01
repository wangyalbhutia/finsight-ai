from app.core.config import settings
import httpx

class LLMAdapter:
    """Provider-independent adapter. If no API key, deterministic fallback explains tool outputs."""
    def __init__(self):
        self.api_key = settings.llm_api_key
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model
    @property
    def available(self):
        return bool(self.api_key)
    def complete(self, prompt: str, fallback: str) -> str:
        if not self.available:
            return fallback
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json={"model": self.model, "messages":[{"role":"user","content":prompt}]}, timeout=15)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception:
            return fallback

llm = LLMAdapter()
