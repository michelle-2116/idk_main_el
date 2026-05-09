-- ============================================================
-- Layer 2 — Allocator Agent: Inventory Table
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS inventory (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_type     VARCHAR(50)   NOT NULL CHECK (item_type IN ('food', 'water', 'meds', 'rescue_team')),
    item_name     VARCHAR(200)  NOT NULL,
    available_quantity INT       NOT NULL CHECK (available_quantity >= 0),
    location      VARCHAR(200)  NOT NULL,
    updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Index for fast lookups by type
CREATE INDEX IF NOT EXISTS idx_inventory_item_type ON inventory (item_type);

-- Trigger: keep updated_at current on every row update
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_inventory_updated_at
    BEFORE UPDATE ON inventory
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();