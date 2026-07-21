"""
content_core.registry
=====================
A minimal registry for pluggable components (scorers, publishers, etc.).

This is deliberately NOT a full plugin framework (no entry-point discovery,
no lifecycle, no sandboxing) — see docs/adr/0008. It is a ~60-line decorator
registry that formalizes how the components we already add get looked up by
name, so eval criteria and providers are configuration, not hardcoded imports.

Usage:
    from content_core.registry import register_scorer, get_scorer, list_scorers

    @register_scorer("length")
    def length_scorer(output, ctx): ...

    scorer = get_scorer("length")
    names = list_scorers()
"""

from __future__ import annotations

from typing import Callable, Dict, TypeVar

T = TypeVar("T", bound=Callable)

_REGISTRIES: Dict[str, Dict[str, Callable]] = {
    "scorer": {},
    "publisher": {},
    "provider": {},
}


def _make_register(kind: str):
    def register(name: str):
        def deco(fn: T) -> T:
            existing = _REGISTRIES[kind].get(name)
            if existing is not None and getattr(existing, "__qualname__", None) != getattr(fn, "__qualname__", None):
                raise ValueError(f"{kind} '{name}' is already registered")
            _REGISTRIES[kind][name] = fn
            return fn
        return deco
    return register


def _make_get(kind: str):
    def get(name: str) -> Callable:
        try:
            return _REGISTRIES[kind][name]
        except KeyError:
            raise KeyError(
                f"No {kind} named '{name}'. Registered: {sorted(_REGISTRIES[kind])}"
            )
    return get


def _make_list(kind: str):
    def lst() -> list[str]:
        return sorted(_REGISTRIES[kind])
    return lst


register_scorer = _make_register("scorer")
get_scorer = _make_get("scorer")
list_scorers = _make_list("scorer")

register_publisher = _make_register("publisher")
get_publisher = _make_get("publisher")
list_publishers = _make_list("publisher")

register_provider = _make_register("provider")
get_provider = _make_get("provider")
list_providers = _make_list("provider")


def _reset_for_tests() -> None:
    """Clear all registries — test helper only."""
    for r in _REGISTRIES.values():
        r.clear()
