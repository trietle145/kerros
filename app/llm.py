"""The one LLM call (owner: A, backend). Provider and model come from .env (LLM_PROVIDER,
LLM_MODEL, LLM_API_KEY), so the model can be swapped without touching callers.
Every caller (plain answers, then-vs-now answers) goes through complete().
"""
from functools import lru_cache

from scripts.common import env


class RefusedError(RuntimeError):
    """The model declined to answer (stop_reason "refusal")."""


@lru_cache(maxsize=1)
def _client():
    e = env()
    if e.get("LLM_PROVIDER", "anthropic") != "anthropic":
        raise NotImplementedError("only LLM_PROVIDER=anthropic is wired up")   # ponytail: add when needed
    import anthropic
    return anthropic.Anthropic(api_key=e["LLM_API_KEY"]), e.get("LLM_MODEL", "claude-opus-5-5")


def complete(system, user, effort="low", max_tokens=4000):
    """One model call -> the answer text. Server-side fallback: if the model declines, the API
    retries the same request on Claude Opus 4.8 within the same call."""
    client, model = _client()
    response = client.beta.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-06-01"], fallbacks=[{"model": "claude-opus-4-8"}],
        messages=[{"role": "user", "content": user}])
    if response.stop_reason == "refusal":
        raise RefusedError("the model declined to answer this question")
    return "".join(b.text for b in response.content if b.type == "text")
