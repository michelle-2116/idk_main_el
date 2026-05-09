"""
inventory_store.py — Layer 2 Allocator Agent
All Supabase inventory reads and writes are isolated here.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from supabase import create_client, Client

logger = logging.getLogger(__name__)

# ── Supabase client (lazy singleton) ────────────────────────────────────────

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


# ── Public interface ────────────────────────────────────────────────────────

def fetch_inventory() -> list[dict[str, Any]]:
    """
    Return all rows from the inventory table, ordered by item_type then item_name.
    Each row: {id, item_type, item_name, available_quantity, location, updated_at}
    """
    client = _get_client()
    response = (
        client.table("inventory")
        .select("id, item_type, item_name, available_quantity, location")
        .order("item_type")
        .order("item_name")
        .execute()
    )
    rows: list[dict] = response.data or []
    logger.debug("Fetched %d inventory rows from Supabase", len(rows))
    return rows


def deduct_inventory(item_name: str, quantity: int) -> bool:
    """
    Atomically deduct `quantity` from the row whose item_name matches.
    Returns True on success, False if item not found or insufficient stock.

    Uses a Postgres RPC function for atomicity — see migrations/003_rpc_deduct.sql.
    Falls back to a read-modify-write if the RPC is unavailable (dev mode).
    """
    client = _get_client()

    try:
        result = client.rpc(
            "deduct_inventory_quantity",
            {"p_item_name": item_name, "p_quantity": quantity},
        ).execute()

        # The RPC returns True/False via a boolean column named "success"
        if result.data and isinstance(result.data, list):
            return bool(result.data[0].get("success", False))
        return False

    except Exception as rpc_err:
        logger.warning(
            "RPC deduct_inventory_quantity failed (%s), falling back to "
            "read-modify-write.", rpc_err
        )
        return _deduct_fallback(client, item_name, quantity)


def _deduct_fallback(client: Client, item_name: str, quantity: int) -> bool:
    """
    Non-atomic fallback: read current quantity, verify sufficiency, update.
    Acceptable for single-writer dev/test environments.
    """
    rows = (
        client.table("inventory")
        .select("id, available_quantity")
        .eq("item_name", item_name)
        .execute()
        .data
    )

    if not rows:
        logger.error("Inventory item not found: '%s'", item_name)
        return False

    row = rows[0]
    current: int = row["available_quantity"]

    if current < quantity:
        logger.error(
            "Insufficient inventory for '%s': have %d, need %d",
            item_name, current, quantity,
        )
        return False

    client.table("inventory").update(
        {"available_quantity": current - quantity}
    ).eq("id", row["id"]).execute()

    logger.info("Deducted %d of '%s' (remaining: %d)", quantity, item_name, current - quantity)
    return True


# ── Inventory → markdown table ──────────────────────────────────────────────

def inventory_to_markdown(rows: list[dict[str, Any]]) -> str:
    """
    Convert inventory rows to a clean markdown table suitable for LLM context.

    | Type        | Item                    | Available | Location               |
    |-------------|-------------------------|-----------|------------------------|
    | food        | dry ration packets      | 8000      | Central Warehouse, ... |
    """
    if not rows:
        return "_No inventory data available._"

    header = "| Type | Item | Available | Location |"
    divider = "|------|------|-----------|----------|"
    lines = [header, divider]

    for row in rows:
        lines.append(
            f"| {row['item_type']} "
            f"| {row['item_name']} "
            f"| {row['available_quantity']} "
            f"| {row['location']} |"
        )

    return "\n".join(lines)