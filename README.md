# content-core

Shared core library for the AI content-automation pipelines
(CrimeScopeAI, RapidReelz, Money Made Clear, RapidReelz Stories).

It consolidates logic that was previously copy-pasted across four repositories
into a single, versioned, testable package — eliminating ~1,500 lines of
duplication and giving every pipeline one source of truth for LLM access,
perspective retrieval, and originality injection.

## What's inside

| Module | Purpose |
|--------|---------|
| `content_core.llm.LLMProvider` | Provider-agnostic text generation over Claude / OpenAI / Gemini, with retry + backoff. |
| `content_core.notion_connect` | Notion "Perspective Bank" access (retrieval, logging, bulk import). |
| `content_core.originality_injector` | Rewrites AI scripts using retrieved perspectives + channel frameworks; scores originality. |

## Install (editable, from a sibling pipeline repo)

```bash
pip install -e ../content-core
```

Then in any pipeline:

```python
from content_core import LLMProvider, inject_originality

llm = LLMProvider(provider="claude")
hook = llm.generate("Write a 1-line hook about the DB Cooper case.",
                    model="claude-sonnet-4-6", max_tokens=60)
```

## Configuration

All secrets are read from the environment (never hardcoded). Copy
`.env.example` to `.env` in your pipeline repo and fill in:

```
ANTHROPIC_API_KEY=...
NOTION_TOKEN=...
# optional
OPENAI_API_KEY=...
GEMINI_API_KEY=...
LLM_PROVIDER=claude
LLM_DEFAULT_MODEL=claude-sonnet-4-6
```

## The LLM abstraction

`LLMProvider` exists so pipelines never call a vendor SDK directly. Switching
providers — or falling back from one to another — becomes a config change:

```python
LLMProvider(provider="claude")   # default
LLMProvider(provider="openai")
LLMProvider(provider="gemini")
```

- **Lazy SDK import** — a repo that only uses Claude doesn't need `openai` or
  `google-generativeai` installed.
- **Built-in retry/backoff** — transient API failures are retried before raising
  a single, normalized `LLMError`.
- **Normalized responses** — callers get plain text (or an `LLMResponse` with
  metadata), not vendor-specific object shapes.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

Tests mock the vendor SDKs, so they run with no API keys and no network.

## Design notes

- **Single source of truth** — the four pipelines previously each carried their
  own copy of `notion_connect.py` and `originality_injector.py`. Any bugfix had
  to be made four times. Now it's made once here.
- **Crash-safe by default** — the originality injector degrades gracefully if
  Notion is unreachable, returning the original script rather than failing the
  whole pipeline run.
