"""
pending_store.py — Layer 2 Allocator Agent
In-memory registry for tool calls that are awaiting human approval.

Each entry is keyed by a unique approval_id and holds everything needed
to re-execute the tool call once an admin approves it.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory store ─────────────────────────────────────────────────────────
# { approval_id: PendingCard }

_store: dict[str, dict[str, Any]] = {}


def park(
    incident_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    trigger_reason: str,
) -> str:
    """
    Save a tool call as pending and return a unique approval_id.

    Parameters
    ----------
    incident_id    : ID of the disaster incident this belongs to.
    tool_name      : e.g. "send_meds"
    tool_args      : The raw kwargs from the Gemini function call.
    trigger_reason : Human-readable reason it was held (threshold / explicit request).
    """
    approval_id = str(uuid.uuid4())
    _store[approval_id] = {
        "approval_id":    approval_id,
        "incident_id":    incident_id,
        "tool_name":      tool_name,
        "tool_args":      tool_args,
        "trigger_reason": trigger_reason,
        "status":         "pending_approval",
        "parked_at":      datetime.now(timezone.utc).isoformat(),
    }
    logger.info(
        "Parked tool call '%s' for incident '%s' → approval_id=%s  reason: %s",
        tool_name, incident_id, approval_id, trigger_reason,
    )
    return approval_id


def retrieve(approval_id: str) -> dict[str, Any] | None:
    """Return the pending card or None if not found."""
    return _store.get(approval_id)


def mark_approved(approval_id: str) -> None:
    """Update status to approved (call before re-execution)."""
    if approval_id in _store:
        _store[approval_id]["status"] = "approved"


def mark_rejected(approval_id: str) -> None:
    """Update status to rejected."""
    if approval_id in _store:
        _store[approval_id]["status"] = "rejected"


def list_pending(incident_id: str | None = None) -> list[dict[str, Any]]:
    """
    Return all pending cards, optionally filtered by incident_id.
    Useful for admin dashboards.
    """
    cards = [c for c in _store.values() if c["status"] == "pending_approval"]
    if incident_id:
        cards = [c for c in cards if c["incident_id"] == incident_id]
    return cards