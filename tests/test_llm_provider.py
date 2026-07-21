"""
Unit tests for LLMProvider.

These mock the vendor SDK so they run without any API key or network — they
test the abstraction's *logic* (provider selection, retry, normalization),
which is exactly what should be tested.
"""

import pytest
from content_core.llm import LLMProvider, LLMError


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        LLMProvider(provider="not-a-provider")


def test_default_provider_is_claude(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert LLMProvider().provider == "claude"


def test_env_provider_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert LLMProvider().provider == "openai"


def test_generate_returns_text(monkeypatch):
    """A successful claude call returns the normalized text."""
    llm = LLMProvider(provider="claude", api_key="test-key")

    class _Block:
        text = "hello world"

    class _Resp:
        content = [_Block()]

    class _Messages:
        def create(self, **kwargs):
            return _Resp()

    class _FakeClient:
        messages = _Messages()

    # Inject a fake client so no real SDK/network is used
    llm._client = _FakeClient()

    out = llm.generate("hi", model="claude-sonnet-4-6", max_tokens=10)
    assert out == "hello world"


def test_retry_then_failure(monkeypatch):
    """After max_retries failures, LLMError is raised."""
    llm = LLMProvider(provider="claude", api_key="test-key", max_retries=2, backoff_base=1.0)

    class _Messages:
        def create(self, **kwargs):
            raise RuntimeError("boom")

    class _FakeClient:
        messages = _Messages()

    llm._client = _FakeClient()

    # speed up: no real sleeping
    monkeypatch.setattr("time.sleep", lambda *_: None)

    with pytest.raises(LLMError):
        llm.generate("hi", model="claude-sonnet-4-6")
