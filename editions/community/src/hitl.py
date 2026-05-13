"""
Human-in-the-loop (HITL) review queue.

Provides a structured approval workflow for AI-generated supply chain findings.
Any workflow run, scenario result, or reasoning-pack output can be submitted for
human review before being acted on.

Review lifecycle
----------------
pending → approved  (reviewer accepts)
pending → rejected  (reviewer rejects with reason)
pending → needs_revision  (reviewer sends back with feedback)
needs_revision → pending  (resubmitted after correction)

Persistence
-----------
Reviews are stored in data/hitl_reviews.json.  In production this would be
backed by a database and event bus; the file store is intentional for the
current deployment tier.

Usage::

    from src.hitl import HITLQueue, ReviewRequest, ReviewDecision

    queue = HITLQueue()
    item = queue.submit(ReviewRequest(
        source_type="workflow_run",
        source_id="abc-123",
        title="Weekly Risk Summary – 2024-Q4",
        content="...full synthesis text...",
        submitted_by="agent:weekly_risk_summary",
    ))
    # Later…
    updated = queue.decide(item.review_id, ReviewDecision(
        decision="approved",
        reviewer="analyst@acme.com",
        comment="Looks correct, proceeding to distribution.",
    ))
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_REVIEW_STORE = Path("data/hitl_reviews.json")

VALID_DECISIONS = {"approved", "rejected", "needs_revision"}
VALID_STATUSES = {"pending", "approved", "rejected", "needs_revision"}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ReviewRequest:
    """Submit an item for human review."""
    source_type: str          # workflow_run | scenario | reasoning_pack | custom
    source_id: str            # ID of the originating object
    title: str                # short human-readable label
    content: str              # full text of the item to review
    submitted_by: str         # agent name or user ID
    priority: str = "normal"  # low | normal | high | urgent
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ReviewDecision:
    """A reviewer's decision on a pending item."""
    decision: str             # approved | rejected | needs_revision
    reviewer: str             # reviewer identity
    comment: str = ""
    correction: Optional[str] = None  # revised content when needs_revision


@dataclass
class ReviewItem:
    """A single item in the review queue."""
    review_id: str
    source_type: str
    source_id: str
    title: str
    content: str
    submitted_by: str
    priority: str
    tags: list[str]
    metadata: dict
    status: str               # pending | approved | rejected | needs_revision
    submitted_at: str
    decided_at: Optional[str] = None
    reviewer: Optional[str] = None
    comment: str = ""
    correction: Optional[str] = None
    history: list[dict] = field(default_factory=list)


# ── Queue ────────────────────────────────────────────────────────────────────

class HITLQueue:
    """Persistent human-in-the-loop review queue."""

    # ── write operations ──────────────────────────────────────────────────

    def submit(self, request: ReviewRequest) -> ReviewItem:
        """Submit an item for review. Returns the new ReviewItem."""
        if request.priority not in ("low", "normal", "high", "urgent"):
            raise ValueError(f"Invalid priority '{request.priority}'")

        item = ReviewItem(
            review_id=str(uuid.uuid4()),
            source_type=request.source_type,
            source_id=request.source_id,
            title=request.title,
            content=request.content,
            submitted_by=request.submitted_by,
            priority=request.priority,
            tags=request.tags,
            metadata=request.metadata,
            status="pending",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            history=[
                {
                    "event": "submitted",
                    "by": request.submitted_by,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )
        data = _load_reviews()
        data[item.review_id] = _serialise(item)
        _save_reviews(data)
        return item

    def decide(self, review_id: str, decision: ReviewDecision) -> ReviewItem:
        """Record a reviewer's decision. Returns the updated ReviewItem."""
        if decision.decision not in VALID_DECISIONS:
            raise ValueError(
                f"Invalid decision '{decision.decision}'. Must be one of {VALID_DECISIONS}"
            )

        data = _load_reviews()
        record = data.get(review_id)
        if not record:
            raise KeyError(f"Review '{review_id}' not found")

        if record["status"] not in ("pending", "needs_revision"):
            raise ValueError(
                f"Cannot decide on review in status '{record['status']}'. "
                "Only 'pending' or 'needs_revision' items can be decided."
            )

        now = datetime.now(timezone.utc).isoformat()
        record["status"] = decision.decision
        record["decided_at"] = now
        record["reviewer"] = decision.reviewer
        record["comment"] = decision.comment
        record["correction"] = decision.correction
        record["history"].append(
            {
                "event": decision.decision,
                "by": decision.reviewer,
                "comment": decision.comment,
                "at": now,
            }
        )
        data[review_id] = record
        _save_reviews(data)
        return _deserialise(record)

    def resubmit(self, review_id: str, revised_content: str, submitted_by: str) -> ReviewItem:
        """Resubmit a needs_revision item with corrected content."""
        data = _load_reviews()
        record = data.get(review_id)
        if not record:
            raise KeyError(f"Review '{review_id}' not found")
        if record["status"] != "needs_revision":
            raise ValueError(
                f"Can only resubmit items in 'needs_revision' status, "
                f"current status: '{record['status']}'"
            )
        now = datetime.now(timezone.utc).isoformat()
        record["content"] = revised_content
        record["status"] = "pending"
        record["decided_at"] = None
        record["history"].append(
            {"event": "resubmitted", "by": submitted_by, "at": now}
        )
        data[review_id] = record
        _save_reviews(data)
        return _deserialise(record)

    def capture_feedback(self, review_id: str, feedback: str, by: str) -> ReviewItem:
        """Append free-form feedback to any review item for model correction workflows."""
        data = _load_reviews()
        record = data.get(review_id)
        if not record:
            raise KeyError(f"Review '{review_id}' not found")
        now = datetime.now(timezone.utc).isoformat()
        record.setdefault("history", []).append(
            {"event": "feedback", "by": by, "feedback": feedback, "at": now}
        )
        data[review_id] = record
        _save_reviews(data)
        return _deserialise(record)

    # ── read operations ───────────────────────────────────────────────────

    def get(self, review_id: str) -> Optional[ReviewItem]:
        data = _load_reviews()
        record = data.get(review_id)
        return _deserialise(record) if record else None

    def list_items(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[ReviewItem]:
        if status and status not in VALID_STATUSES:
            raise ValueError(f"Invalid status filter '{status}'")
        data = _load_reviews()
        items = [_deserialise(r) for r in data.values()]
        if status:
            items = [i for i in items if i.status == status]
        if priority:
            items = [i for i in items if i.priority == priority]
        if source_type:
            items = [i for i in items if i.source_type == source_type]
        items.sort(
            key=lambda i: (_priority_order(i.priority), i.submitted_at),
            reverse=False,
        )
        return items[:limit]

    def queue_stats(self) -> dict:
        """Return counts by status and priority for dashboards."""
        data = _load_reviews()
        stats: dict = {"by_status": {}, "by_priority": {}, "total": len(data)}
        for record in data.values():
            s = record.get("status", "unknown")
            p = record.get("priority", "normal")
            stats["by_status"][s] = stats["by_status"].get(s, 0) + 1
            stats["by_priority"][p] = stats["by_priority"].get(p, 0) + 1
        return stats


# ── helpers ───────────────────────────────────────────────────────────────────

def _priority_order(p: str) -> int:
    return {"urgent": 0, "high": 1, "normal": 2, "low": 3}.get(p, 2)


def _load_reviews() -> dict:
    if _REVIEW_STORE.exists():
        try:
            return json.loads(_REVIEW_STORE.read_text())
        except Exception:
            return {}
    return {}


def _save_reviews(data: dict) -> None:
    _REVIEW_STORE.parent.mkdir(parents=True, exist_ok=True)
    _REVIEW_STORE.write_text(json.dumps(data, indent=2))


def _serialise(item: ReviewItem) -> dict:
    return {
        "review_id": item.review_id,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "title": item.title,
        "content": item.content,
        "submitted_by": item.submitted_by,
        "priority": item.priority,
        "tags": item.tags,
        "metadata": item.metadata,
        "status": item.status,
        "submitted_at": item.submitted_at,
        "decided_at": item.decided_at,
        "reviewer": item.reviewer,
        "comment": item.comment,
        "correction": item.correction,
        "history": item.history,
    }


def _deserialise(record: dict) -> ReviewItem:
    return ReviewItem(
        review_id=record["review_id"],
        source_type=record["source_type"],
        source_id=record["source_id"],
        title=record["title"],
        content=record["content"],
        submitted_by=record["submitted_by"],
        priority=record.get("priority", "normal"),
        tags=record.get("tags", []),
        metadata=record.get("metadata", {}),
        status=record["status"],
        submitted_at=record["submitted_at"],
        decided_at=record.get("decided_at"),
        reviewer=record.get("reviewer"),
        comment=record.get("comment", ""),
        correction=record.get("correction"),
        history=record.get("history", []),
    )
