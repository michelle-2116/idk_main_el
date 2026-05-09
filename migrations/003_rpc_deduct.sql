-- ============================================================
-- Layer 2 — Allocator Agent: Atomic deduction RPC
-- ============================================================
-- Called by inventory_store.deduct_inventory() for safe,
-- race-condition-free quantity deduction.

CREATE OR REPLACE FUNCTION deduct_inventory_quantity(
    p_item_name  TEXT,
    p_quantity   INT
)
RETURNS TABLE (success BOOLEAN)
LANGUAGE plpgsql
AS $$
DECLARE
    v_id                UUID;
    v_available         INT;
BEGIN
    -- Lock the row for the duration of this transaction
    SELECT id, available_quantity
    INTO   v_id, v_available
    FROM   inventory
    WHERE  item_name = p_item_name
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE;
        RETURN;
    END IF;

    IF v_available < p_quantity THEN
        RETURN QUERY SELECT FALSE;
        RETURN;
    END IF;

    UPDATE inventory
    SET    available_quantity = available_quantity - p_quantity
    WHERE  id = v_id;

    RETURN QUERY SELECT TRUE;
END;
$$;