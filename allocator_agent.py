"""
allocator_agent.py — Layer 2 Allocator Agent
============================================================
Primary entry point:  run_allocator_agent(context_packet)
Admin re-execution:   approve_and_execute(approval_id)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types as genai_types

from config import (
    APPROVAL_THRESHOLDS,
    GEMINI_MODEL,
    SYSTEM_PROMPT_TEMPLATE,
    TOOL_DECLARATIONS,
)
from inventory_store import deduct_inventory, fetch_inventory, inventory_to_markdown
import pending_store

logger = logging.getLogger(__name__)

# ── Gemini client init ───────────────────────────────────────────────────────

def _build_tools() -> list[genai_types.Tool]:
    """Convert TOOL_DECLARATIONS config into google.genai Tool objects."""
    declarations = [
        genai_types.FunctionDeclaration(
            name=decl["name"],
            description=decl["description"],
            parameters=decl["parameters"],
        )
        for decl in TOOL_DECLARATIONS
    ]
    return [genai_types.Tool(function_declarations=declarations)]


def _get_gemini_client() -> tuple[genai.Client, list[genai_types.Tool]]:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    tools  = _build_tools()
    return client, tools


# ── Tool-type resolver ───────────────────────────────────────────────────────

def _resolve_tool_type(tool_name: str) -> str:
    """Map a tool name to its HITL threshold category."""
    return {
        "send_food":         "food",
        "send_water":        "water",
        "send_meds":         "meds",
        "send_rescue_team":  "rescue_team",
        "request_human_approval": "human_approval",
    }.get(tool_name, "unknown")


def _get_quantity(tool_name: str, args: dict[str, Any]) -> int:
    """Extract the relevant numeric field for threshold comparison."""
    if tool_name == "send_rescue_team":
        return int(args.get("size", 0))
    return int(args.get("quantity", 0))


def _get_item_name(tool_name: str, args: dict[str, Any]) -> str:
    """Return the inventory item name from tool args."""
    if tool_name == "send_rescue_team":
        return args.get("location", "unknown location")
    return args.get("item", "unknown item")


# ── HITL gate ────────────────────────────────────────────────────────────────

def _hitl_gate(
    tool_name: str,
    args: dict[str, Any],
) -> tuple[bool, str]:
    """
    Decide whether a tool call needs human approval.

    Returns
    -------
    (needs_approval: bool, reason: str)
    """
    item_type = _resolve_tool_type(tool_name)

    # Agent explicitly requested human review
    if tool_name == "request_human_approval":
        return True, f"Agent requested approval: {args.get('reason', 'no reason given')}"

    # Quantity exceeds threshold
    qty = _get_quantity(tool_name, args)
    threshold = APPROVAL_THRESHOLDS.get(item_type, 0)
    if qty > threshold:
        return True, (
            f"Quantity {qty} exceeds threshold {threshold} for '{item_type}'"
        )

    return False, ""


# ── Single tool-call executor ────────────────────────────────────────────────

def _execute_tool_call(
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute a single tool call: deduct from inventory and return an allocation record.
    For send_rescue_team the 'item' is the team type resolved from args['location'].
    """
    item_type = _resolve_tool_type(tool_name)
    item_name = _get_item_name(tool_name, args)
    quantity  = _get_quantity(tool_name, args)

    # Deduct inventory (rescue teams are tracked by team name / type)
    success = deduct_inventory(item_name, quantity)
    if not success:
        logger.warning(
            "Inventory deduction failed for '%s' × %d — marking as failed.",
            item_name, quantity,
        )

    record: dict[str, Any] = {
        "type":        item_type,
        "tool_name":   tool_name,
        "item":        item_name,
        "note":        args.get("note", args.get("location", "")),
        "explanation": args.get("explanation", args.get("reason", "")),
        "status":      "executed" if success else "execution_failed",
    }

    if tool_name == "send_rescue_team":
        record["quantity"] = quantity   # teams
    else:
        record["quantity"] = quantity

    return record


# ── Build system prompt ──────────────────────────────────────────────────────

def _build_system_prompt(context_packet: dict, inventory_table: str) -> str:
    incident   = context_packet.get("incident", {})
    needs      = context_packet.get("needs_summary", "Not specified")
    map_desc   = context_packet.get("map_description", "No map data available")

    return SYSTEM_PROMPT_TEMPLATE.format(
        incident_type=incident.get("type", "unknown"),
        location=incident.get("location", "unknown"),
        severity=incident.get("severity", "unknown"),
        needs_summary=needs,
        inventory_table=inventory_table,
        map_description=map_desc,
    )


# ── Main public function ─────────────────────────────────────────────────────

def run_allocator_agent(context_packet: dict) -> dict[str, Any]:
    """
    Layer 2 main entry point.

    Parameters
    ----------
    context_packet : dict
        Supplied by Layer 1 after news_verified() fires. Expected shape:
        {
            "incident_id": str,
            "incident": {"type": str, "location": str, "severity": str},
            "needs_summary": str,
            "map_description": str,
        }

    Returns
    -------
    dict  — allocation result payload for Layer 3.
        {
            "incident_id": str,
            "allocations": [ { type, item, quantity, note, explanation, status }, ... ]
        }

    Side-effects
    ------------
    - Reads inventory from Supabase.
    - Immediately deducts inventory for executed allocations.
    - Parks pending allocations in pending_store (in-memory).
    """
    incident_id: str = context_packet.get("incident_id", "unknown")
    logger.info("=== Allocator Agent START  incident_id=%s ===", incident_id)

    # ── 1. Read inventory ────────────────────────────────────────────────────
    inventory_rows  = fetch_inventory()
    inventory_table = inventory_to_markdown(inventory_rows)
    logger.debug("Inventory markdown:\n%s", inventory_table)

    # ── 2. Build prompt ──────────────────────────────────────────────────────
    system_prompt = _build_system_prompt(context_packet, inventory_table)
    user_message  = (
        f"Incident ID: {incident_id}\n"
        f"Please allocate the required resources now."
    )

    # ── 3. Single Gemini call ────────────────────────────────────────────────
    client, tools = _get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=system_prompt + "\n\n" + user_message,
        config=genai_types.GenerateContentConfig(
            tools=tools,
            tool_config=genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(mode="ANY")
            ),
        ),
    )
    logger.info("Gemini responded with %d candidate(s)", len(response.candidates))

    # ── 4. Parse all tool calls from the single response ────────────────────
    function_calls: list[tuple[str, dict]] = []
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.function_call:
                fc   = part.function_call
                name = fc.name
                args = dict(fc.args)   # proto MapComposite → plain dict
                function_calls.append((name, args))
                logger.info("Tool call received: %s(%s)", name, json.dumps(args, default=str))

    if not function_calls:
        logger.warning("Gemini returned no tool calls for incident %s", incident_id)

    # ── 5. HITL gate + execution ─────────────────────────────────────────────
    allocations: list[dict[str, Any]] = []

    for tool_name, args in function_calls:
        needs_approval, reason = _hitl_gate(tool_name, args)

        if needs_approval:
            approval_id = pending_store.park(
                incident_id=incident_id,
                tool_name=tool_name,
                tool_args=args,
                trigger_reason=reason,
            )
            item_type = _resolve_tool_type(tool_name)

            allocations.append({
                "type":        item_type,
                "tool_name":   tool_name,
                "item":        _get_item_name(tool_name, args),
                "quantity":    _get_quantity(tool_name, args),
                "note":        args.get("note", args.get("reason", "")),
                "explanation": args.get("explanation", args.get("reason", "")),
                "status":      "pending_approval",
                "approval_id": approval_id,
            })
        else:
            result = _execute_tool_call(tool_name, args)
            allocations.append(result)

    output = {
        "incident_id": incident_id,
        "allocations": allocations,
    }

    executed = sum(1 for a in allocations if a["status"] == "executed")
    pending  = sum(1 for a in allocations if a["status"] == "pending_approval")
    logger.info(
        "=== Allocator Agent DONE  executed=%d  pending=%d ===",
        executed, pending,
    )

    return output


# ── Admin approval re-execution ──────────────────────────────────────────────

def approve_and_execute(approval_id: str) -> dict[str, Any] | None:
    """
    Called by an admin (or admin API endpoint) when a pending card is approved.

    1. Retrieves the parked tool call from pending_store.
    2. Executes it (deducts inventory).
    3. Returns a single-allocation payload for Layer 3.

    Returns None if approval_id is not found or already processed.
    """
    card = pending_store.retrieve(approval_id)
    if not card:
        logger.error("approve_and_execute: approval_id '%s' not found", approval_id)
        return None

    if card["status"] != "pending_approval":
        logger.warning(
            "approve_and_execute: card '%s' already has status '%s'",
            approval_id, card["status"],
        )
        return None

    pending_store.mark_approved(approval_id)

    tool_name = card["tool_name"]
    args      = card["tool_args"]

    result = _execute_tool_call(tool_name, args)
    result["approval_id"] = approval_id

    logger.info(
        "Admin-approved execution complete for approval_id=%s  status=%s",
        approval_id, result["status"],
    )

    return {
        "incident_id": card["incident_id"],
        "allocations": [result],
    }