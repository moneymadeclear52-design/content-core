"""
content_core.eval.registry
==========================
A versioned prompt registry backed by the platform database.

Prompts are templates identified by name; each save creates a new immutable
version (content-hashed, so re-saving identical text is a no-op). Eval and
experiment runs reference a specific version, making regressions traceable to
a prompt change.

Usage:
    from content_core.eval.registry import PromptRegistry

    reg = PromptRegistry()
    v = reg.save("script.hook", "Write a hook about {topic}...", author="me")
    tmpl = reg.get("script.hook")               # latest
    tmpl = reg.get("script.hook", version=2)    # specific
    rendered = tmpl.render(topic="DB Cooper")
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class PromptTemplate:
    name: str
    version: int
    text: str
    content_hash: str

    def render(self, **kwargs) -> str:
        """Simple str.format rendering. Missing keys raise KeyError by design."""
        return self.text.format(**kwargs)


class PromptRegistry:
    def __init__(self):
        from ..db import init_db
        init_db()

    def save(self, name: str, text: str, author: Optional[str] = None) -> PromptTemplate:
        """Create a new version unless identical to the current latest."""
        from ..db import get_session
        from ..db.models_phase5 import Prompt, PromptVersion
        h = _hash(text)
        with get_session() as s:
            prompt = s.query(Prompt).filter_by(name=name).one_or_none()
            if prompt is None:
                prompt = Prompt(name=name)
                s.add(prompt)
                s.flush()
            latest = (
                s.query(PromptVersion)
                 .filter_by(prompt_id=prompt.id)
                 .order_by(PromptVersion.version.desc())
                 .first()
            )
            if latest and latest.content_hash == h:
                return PromptTemplate(name, latest.version, latest.text, h)
            next_v = (latest.version + 1) if latest else 1
            pv = PromptVersion(prompt_id=prompt.id, version=next_v, text=text,
                               content_hash=h, author=author)
            s.add(pv)
            s.flush()
            return PromptTemplate(name, next_v, text, h)

    def get(self, name: str, version: Optional[int] = None) -> PromptTemplate:
        from ..db import get_session
        from ..db.models_phase5 import Prompt, PromptVersion
        with get_session() as s:
            prompt = s.query(Prompt).filter_by(name=name).one_or_none()
            if prompt is None:
                raise KeyError(f"No prompt named '{name}'")
            q = s.query(PromptVersion).filter_by(prompt_id=prompt.id)
            pv = (q.filter_by(version=version).one_or_none() if version
                  else q.order_by(PromptVersion.version.desc()).first())
            if pv is None:
                raise KeyError(f"Prompt '{name}' has no version {version}")
            return PromptTemplate(name, pv.version, pv.text, pv.content_hash)

    def versions(self, name: str) -> list[int]:
        from ..db import get_session
        from ..db.models_phase5 import Prompt, PromptVersion
        with get_session() as s:
            prompt = s.query(Prompt).filter_by(name=name).one_or_none()
            if prompt is None:
                return []
            rows = (s.query(PromptVersion.version)
                     .filter_by(prompt_id=prompt.id)
                     .order_by(PromptVersion.version).all())
            return [r[0] for r in rows]

    def list_prompts(self) -> list[str]:
        from ..db import get_session
        from ..db.models_phase5 import Prompt
        with get_session() as s:
            return [p.name for p in s.query(Prompt).order_by(Prompt.name).all()]
