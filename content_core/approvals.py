"""
content_core.approvals
======================
Human-in-the-loop approval gate for the workflow engine.

Even for a single operator, gating auto-generated content before it publishes
is a real safeguard (not ceremony): a Workflow step can request approval,
which persists a `pending` row and stops the item from proceeding until a
human approves or rejects it via the API/dashboard.

Policy helper: auto_or_queue() auto-approves when a quality score clears a
threshold, and queues for human review otherwise — so the human only sees the
borderline cases.

Usage in a workflow step:
    from content_core.approvals import auto_or_queue
    decision = auto_or_queue(workflow="rapidreelz", item_ref=job_id,
                             summary=title, score=originality_score,
                             threshold=0.75)
    if decision == "pending":
        return   # stop here; item awaits human review
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def request_approval(*, workflow: str, item_ref: str,
                     summary: Optional[str] = None,
                     score: Optional[float] = None) -> int:
    """Create a pending approval; returns its id."""
    from .db import get_session, init_db
    from .db.models_phase5 import Approval
    init_db()
    with get_session() as s:
        a = Approval(workflow=workflow, item_ref=item_ref, summary=summary,
                     score=score, status="pending")
        s.add(a)
        s.flush()
        return a.id


def decide(approval_id: int, *, approved: bool, note: Optional[str] = None) -> str:
    from .db import get_session
    from .db.models_phase5 import Approval
    with get_session() as s:
        a = s.get(Approval, approval_id)
        if a is None:
            raise KeyError(f"No approval {approval_id}")
        a.status = "approved" if approved else "rejected"
        a.decided_at = datetime.now(timezone.utc)
        a.note = note
        return a.status


def pending(limit: int = 50) -> list[dict]:
    from .db import get_session, init_db
    from .db.models_phase5 import Approval
    init_db()
    with get_session() as s:
        rows = (s.query(Approval).filter_by(status="pending")
                 .order_by(Approval.at.desc()).limit(limit).all())
        return [
            {"id": a.id, "workflow": a.workflow, "item_ref": a.item_ref,
             "summary": a.summary, "score": a.score, "at": a.at.isoformat()}
            for a in rows
        ]


def auto_or_queue(*, workflow: str, item_ref: str, summary: Optional[str],
                  score: Optional[float], threshold: float = 0.75) -> str:
    """
    Auto-approve when score >= threshold; otherwise queue a pending approval.
    Returns "approved" or "pending".
    """
    if score is not None and score >= threshold:
        return "approved"
    request_approval(workflow=workflow, item_ref=item_ref, summary=summary, score=score)
    return "pending"
