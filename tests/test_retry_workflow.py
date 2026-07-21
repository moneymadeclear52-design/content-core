"""Tests for content_core.retry and content_core.workflow — no network, no keys."""

import pytest
from content_core.retry import retry, call_with_retry
from content_core.workflow import Workflow, Step


# ── retry ──────────────────────────────────────────────────────────────────────

def test_retry_succeeds_after_failures(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}

    @retry(attempts=3, exceptions=(ValueError,))
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


def test_retry_raises_original_after_exhaustion(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)

    @retry(attempts=2, exceptions=(ValueError,))
    def always_fails():
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        always_fails()


def test_retry_does_not_catch_unlisted_exceptions(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}

    @retry(attempts=3, exceptions=(ValueError,))
    def auth_error():
        calls["n"] += 1
        raise PermissionError("401")  # should NOT be retried

    with pytest.raises(PermissionError):
        auth_error()
    assert calls["n"] == 1  # failed fast, no retries


def test_call_with_retry_functional_form(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    assert call_with_retry(lambda: 42, attempts=2) == 42


# ── workflow ───────────────────────────────────────────────────────────────────

def test_workflow_happy_path():
    def a(ctx): ctx["a"] = 1
    def b(ctx): ctx["b"] = ctx["a"] + 1

    wf = Workflow("t", [Step("a", a), Step("b", b)])
    report = wf.run()
    assert report.ok
    assert [r.status for r in report.results] == ["ok", "ok"]


def test_workflow_context_flows_between_steps():
    seen = {}
    def produce(ctx): ctx["value"] = "hello"
    def consume(ctx): seen["got"] = ctx["value"]

    Workflow("t", [Step("p", produce), Step("c", consume)]).run()
    assert seen["got"] == "hello"


def test_workflow_aborts_on_required_step_failure(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    ran = []
    def fails(ctx): raise RuntimeError("boom")
    def never(ctx): ran.append("never")

    report = Workflow("t", [Step("f", fails, retries=2), Step("n", never)]).run()
    assert report.aborted
    assert report.results[0].status == "failed"
    assert report.results[0].attempts == 2
    assert ran == []  # later step never ran


def test_workflow_skips_optional_step_and_continues(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    ran = []
    def fails(ctx): raise RuntimeError("thumbnail service down")
    def after(ctx): ran.append("after")

    report = Workflow("t", [
        Step("optional", fails, on_error="skip"),
        Step("after", after),
    ]).run()
    assert report.ok
    assert report.results[0].status == "skipped"
    assert ran == ["after"]


def test_workflow_retry_then_success(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}
    def flaky(ctx):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")

    report = Workflow("t", [Step("flaky", flaky, retries=3)]).run()
    assert report.ok
    assert report.results[0].attempts == 2


def test_report_summary_renders():
    def a(ctx): pass
    report = Workflow("demo", [Step("a", a)]).run()
    s = report.summary()
    assert "demo" in s and "a" in s and "ok" in s
