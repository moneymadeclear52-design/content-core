"""Phase 5 tests: scorers, plugin registry, prompt registry, approvals,
eval/experiment. Isolated SQLite DB; scripted fake LLM; no keys, no network."""

import importlib
import pytest


# ── plugin registry ────────────────────────────────────────────────────────────

def _other_fn(o, c):
    return None


def test_registry_register_get_list():
    from content_core import registry
    registry._reset_for_tests()

    @registry.register_scorer("demo")
    def _d(o, c): return o
    assert registry.get_scorer("demo") is _d
    assert "demo" in registry.list_scorers()
    with pytest.raises(ValueError):
        registry.register_scorer("demo")(_other_fn)  # duplicate different fn
    with pytest.raises(KeyError):
        registry.get_scorer("nope")


# ── rule-based scorers ─────────────────────────────────────────────────────────

def test_rule_scorers():
    # reimport to restore built-ins after the reset above
    import content_core.eval.scorers as sc
    importlib.reload(sc)
    from content_core.registry import get_scorer

    assert get_scorer("non_empty")("hi", {}).passed
    assert not get_scorer("non_empty")("  ", {}).passed

    s = get_scorer("length_bounds")("one two three", {"min_words": 2, "max_words": 5})
    assert s.passed and s.value == 1.0

    s = get_scorer("contains_all")("has foo and bar", {"required": ["foo", "bar"]})
    assert s.value == 1.0
    s = get_scorer("contains_all")("only foo", {"required": ["foo", "bar"]})
    assert s.value == 0.5 and not s.passed

    assert get_scorer("excludes_all")("clean text", {"forbidden": ["xxx"]}).passed
    assert not get_scorer("excludes_all")("has xxx", {"forbidden": ["xxx"]}).passed


def test_llm_judge_parses_and_degrades():
    import content_core.eval.scorers as sc
    importlib.reload(sc)

    class GoodLLM:
        def generate(self, prompt, **kw): return '{"score": 0.9, "reason": "great"}'
    j = sc.LLMJudge(llm=GoodLLM())
    s = j.score("output", {"task": "t"})
    assert s.value == 0.9 and s.passed

    class BadLLM:
        def generate(self, prompt, **kw): return "not json at all"
    s2 = sc.LLMJudge(llm=BadLLM()).score("o", {"task": "t"})
    assert s2.value == 0.5 and not s2.passed  # graceful neutral


def test_run_scorers_and_aggregate():
    import content_core.eval.scorers as sc
    importlib.reload(sc)
    scores = sc.run_scorers("hello world", [
        {"scorer": "non_empty"},
        {"scorer": "length_bounds", "min_words": 1, "max_words": 5},
    ])
    assert len(scores) == 2
    assert sc.aggregate(scores) == 1.0


# ── prompt registry (DB) ───────────────────────────────────────────────────────

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/p5.db")
    import content_core.db as db
    import content_core.db.models_phase5  # noqa: F401
    db.init_db()
    return db


def test_prompt_registry_versioning(isolated_db):
    from content_core.eval.registry import PromptRegistry
    reg = PromptRegistry()
    v1 = reg.save("script.hook", "Write about {topic}", author="me")
    assert v1.version == 1
    # identical save → no new version
    v1b = reg.save("script.hook", "Write about {topic}")
    assert v1b.version == 1
    # changed text → new version
    v2 = reg.save("script.hook", "Write a HOOK about {topic}")
    assert v2.version == 2
    assert reg.versions("script.hook") == [1, 2]
    assert reg.get("script.hook").version == 2                 # latest
    assert reg.get("script.hook", version=1).text == "Write about {topic}"
    assert reg.get("script.hook").render(topic="X") == "Write a HOOK about X"


# ── approvals (HITL) ───────────────────────────────────────────────────────────

def test_auto_or_queue_and_decide(isolated_db):
    from content_core.approvals import auto_or_queue, pending, decide

    # high score auto-approves, nothing queued
    assert auto_or_queue(workflow="w", item_ref="a", summary="s", score=0.9, threshold=0.75) == "approved"
    assert pending() == []

    # low score queues
    assert auto_or_queue(workflow="w", item_ref="b", summary="s", score=0.4, threshold=0.75) == "pending"
    q = pending()
    assert len(q) == 1 and q[0]["item_ref"] == "b"

    # decide
    status = decide(q[0]["id"], approved=True, note="looks fine")
    assert status == "approved"
    assert pending() == []


# ── eval + experiment (scripted LLM) ───────────────────────────────────────────

def test_evaluate_persists_report(isolated_db):
    from content_core.eval.runner import evaluate

    class FakeLLM:
        def generate(self, prompt, **kw): return "a solid three word line here"

    report = evaluate(
        "Topic: {topic}",
        cases=[{"id": "c1", "inputs": {"topic": "money"}}],
        criteria=[{"scorer": "non_empty"},
                  {"scorer": "length_bounds", "min_words": 3, "max_words": 20}],
        llm=FakeLLM(), model="fake",
    )
    assert report.mean_score == 1.0
    assert report.pass_rate == 1.0
    assert report.run_id is not None  # persisted


def test_experiment_picks_winner(isolated_db):
    from content_core.eval.runner import experiment, Variant

    class LenLLM:
        # returns the template back so longer templates score higher on length
        def generate(self, prompt, **kw): return prompt

    result = experiment(
        variants=[Variant("short", "hi {t}"), Variant("long", "hello there dear {t} indeed")],
        inputs={"t": "x"},
        criteria=[{"scorer": "length_bounds", "min_words": 4, "max_words": 100}],
        llm=LenLLM(),
    )
    assert result.winner == "long"
    assert result.scores["long"] >= result.scores["short"]
