"""
config.py — Layer 2 Allocator Agent
Centralised constants, thresholds, and tool schemas.
"""

import os

# ── HITL gate thresholds ────────────────────────────────────────────────────
APPROVAL_THRESHOLDS: dict[str, int] = {
    "food":        int(os.getenv("APPROVAL_THRESHOLD_FOOD",         5000)),
    "water":       int(os.getenv("APPROVAL_THRESHOLD_WATER",       10000)),
    "meds":        int(os.getenv("APPROVAL_THRESHOLD_MEDS",          500)),
    "rescue_team": int(os.getenv("APPROVAL_THRESHOLD_RESCUE_TEAM",     5)),
}

# ── Gemini model ────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-flash-latest"

# ── Tool declarations for Gemini function-calling ───────────────────────────
TOOL_DECLARATIONS = [
    {
        "name": "send_food",
        "description": (
            "Allocate food supplies to a disaster-affected area. "
            "Use this when people need food relief."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quantity":    {"type": "integer",  "description": "Number of units to send"},
                "item":        {"type": "string",   "description": "Name of the food item (must match inventory)"},
                "note":        {"type": "string",   "description": "Routing / logistics note (road closures, access constraints)"},
                "explanation": {"type": "string",   "description": "Why this allocation is required"},
            },
            "required": ["quantity", "item", "note", "explanation"],
        },
    },
    {
        "name": "send_water",
        "description": (
            "Allocate water or water-purification supplies. "
            "Use for drinking water shortages or contamination."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quantity":    {"type": "integer",  "description": "Number of units (pouches / litres / tablets)"},
                "item":        {"type": "string",   "description": "Name of the water item (must match inventory)"},
                "note":        {"type": "string",   "description": "Routing / logistics note"},
                "explanation": {"type": "string",   "description": "Why this allocation is required"},
            },
            "required": ["quantity", "item", "note", "explanation"],
        },
    },
    {
        "name": "send_meds",
        "description": (
            "Allocate medical supplies or medicine kits. "
            "Use for injury treatment, disease prevention, or public-health response."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quantity":    {"type": "integer",  "description": "Number of kits / units"},
                "item":        {"type": "string",   "description": "Name of the medical item (must match inventory)"},
                "note":        {"type": "string",   "description": "Routing / logistics note"},
                "explanation": {"type": "string",   "description": "Why this allocation is required"},
            },
            "required": ["quantity", "item", "note", "explanation"],
        },
    },
    {
        "name": "send_rescue_team",
        "description": (
            "Deploy a rescue team to a location. "
            "Use for search-and-rescue, evacuation, or structural assessment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "size":        {"type": "integer",  "description": "Number of teams to deploy"},
                "location":    {"type": "string",   "description": "Destination location for the team"},
                "note":        {"type": "string",   "description": "Routing / logistics note"},
                "explanation": {"type": "string",   "description": "Why this deployment is required"},
            },
            "required": ["size", "location", "note", "explanation"],
        },
    },
    {
        "name": "request_human_approval",
        "description": (
            "Flag an allocation for human review before it is executed. "
            "Call this when you are uncertain, when quantities are unusually large, "
            "or when the situation has ambiguities that a human should resolve."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item":   {"type": "string", "description": "The resource or action requiring approval"},
                "reason": {"type": "string", "description": "Why human approval is needed"},
            },
            "required": ["item", "reason"],
        },
    },
]

# ── System prompt template ───────────────────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """\
You are a disaster resource allocator for a {incident_type} incident in {location} \
(severity: {severity}).

You have these verified needs:
{needs_summary}

Current inventory:
{inventory_table}

Map context:
{map_description}

Instructions:
- Use the provided tools to allocate resources. Issue ALL allocation tool calls in a \
single response.
- For each allocation specify exact quantity and item name exactly as it appears in the \
inventory table.
- Add routing notes (road closures, helicopter-only zones, etc.).
- Add a clear explanation of why each allocation is needed.
- DO NOT over-allocate beyond the available inventory shown above.
- If you are uncertain about any allocation, or if a quantity seems unusually large, \
call request_human_approval instead of sending automatically.
"""