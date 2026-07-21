"""
content_core.llm.provider
==========================
A single, provider-agnostic interface for text generation across Claude,
OpenAI, and Gemini. Pipelines call `generate(...)` and never touch a vendor
SDK directly, so switching or falling back between providers is a config change
rather than a code change.

Usage:
    from content_core.llm import LLMProvider

    llm = LLMProvider(provider="claude")            # or "openai" / "gemini"
    text = llm.generate("Write a hook about the DB Cooper case.",
                        model="claude-sonnet-4-6", max_tokens=500)

Configuration is read from the environment (see .env.example):
    ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY
    LLM_PROVIDER          default provider if none passed ("claude")
    LLM_DEFAULT_MODEL     default model if none passed
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Sensible per-provider default models. Override via LLM_DEFAULT_MODEL or the
# `model=` argument on generate().
_DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-pro",
}


class LLMError(RuntimeError):
    """Raised when a generation call fails after all retries."""


@dataclass
class LLMResponse:
    """Normalized response so callers don't parse vendor-specific shapes."""
    text: str
    model: str
    provider: str
    raw: object = None  # the underlying SDK response, if a caller needs it


class LLMProvider:
    """
    Provider-agnostic text generation with built-in retry/backoff.

    The vendor SDK is imported lazily so a repo that only uses Claude doesn't
    need openai / google-generativeai installed.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        *,
        api_key: Optional[str] = None,
        max_retries: int = 3,
        backoff_base: float = 1.5,
    ):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "claude")).lower()
        if self.provider not in _DEFAULT_MODELS:
            raise ValueError(
                f"Unknown provider '{self.provider}'. "
                f"Expected one of: {', '.join(_DEFAULT_MODELS)}"
            )
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._api_key = api_key
        self._client = None  # lazily created

    # ── public API ────────────────────────────────────────────────────────────
    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        """Generate text and return the string. Raises LLMError on failure."""
        resp = self.generate_full(
            prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
        )
        return resp.text

    def generate_full(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """Generate and return a normalized LLMResponse (text + metadata)."""
        model = model or os.getenv("LLM_DEFAULT_MODEL") or _DEFAULT_MODELS[self.provider]
        last_err: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                text, raw = self._dispatch(prompt, model, max_tokens, temperature, system)
                return LLMResponse(text=text, model=model, provider=self.provider, raw=raw)
            except Exception as e:  # noqa: BLE001 — we re-raise as LLMError below
                last_err = e
                wait = self.backoff_base ** attempt
                logger.warning(
                    "LLM call failed (attempt %d/%d, provider=%s, model=%s): %s. "
                    "Retrying in %.1fs.",
                    attempt, self.max_retries, self.provider, model, e, wait,
                )
                if attempt < self.max_retries:
                    time.sleep(wait)

        raise LLMError(
            f"{self.provider}:{model} failed after {self.max_retries} attempts: {last_err}"
        ) from last_err

    # ── provider dispatch ──────────────────────────────────────────────────────
    def _dispatch(self, prompt, model, max_tokens, temperature, system):
        if self.provider == "claude":
            return self._claude(prompt, model, max_tokens, temperature, system)
        if self.provider == "openai":
            return self._openai(prompt, model, max_tokens, temperature, system)
        if self.provider == "gemini":
            return self._gemini(prompt, model, max_tokens, temperature, system)
        raise ValueError(f"Unhandled provider: {self.provider}")

    def _claude(self, prompt, model, max_tokens, temperature, system):
        if self._client is None:
            import anthropic
            key = self._api_key or os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise LLMError("ANTHROPIC_API_KEY not set")
            self._client = anthropic.Anthropic(api_key=key)
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        resp = self._client.messages.create(**kwargs)
        return resp.content[0].text, resp

    def _openai(self, prompt, model, max_tokens, temperature, system):
        if self._client is None:
            from openai import OpenAI
            key = self._api_key or os.getenv("OPENAI_API_KEY")
            if not key:
                raise LLMError("OPENAI_API_KEY not set")
            self._client = OpenAI(api_key=key)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages,
        )
        return resp.choices[0].message.content, resp

    def _gemini(self, prompt, model, max_tokens, temperature, system):
        if self._client is None:
            import google.generativeai as genai
            key = self._api_key or os.getenv("GEMINI_API_KEY")
            if not key:
                raise LLMError("GEMINI_API_KEY not set")
            genai.configure(api_key=key)
            self._client = genai
        gen_model = self._client.GenerativeModel(
            model_name=model,
            system_instruction=system if system else None,
        )
        resp = gen_model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        return resp.text, resp
