-- ============================================================
-- Seed Data — realistic disaster relief inventory
-- ============================================================

INSERT INTO inventory (item_type, item_name, available_quantity, location) VALUES

-- FOOD
('food', 'dry ration packets',        8000,  'Central Warehouse, Delhi'),
('food', 'ready-to-eat meals',        4500,  'Regional Hub, Lucknow'),
('food', 'high-energy biscuits',      12000, 'Central Warehouse, Delhi'),
('food', 'baby food packs',           2000,  'Medical Depot, Patna'),

-- WATER
('water', 'water pouches (500ml)',    50000, 'Central Warehouse, Delhi'),
('water', 'water purification tabs',  30000, 'Regional Hub, Lucknow'),
('water', 'bottled water (1L)',       15000, 'Regional Hub, Lucknow'),

-- MEDS
('meds', 'ORS kits',                  1200,  'Medical Depot, Patna'),
('meds', 'first aid kits',            800,   'Medical Depot, Patna'),
('meds', 'trauma kits',               300,   'Central Warehouse, Delhi'),
('meds', 'anti-cholera tablets',      5000,  'Medical Depot, Patna'),

-- RESCUE TEAMS
('rescue_team', 'NDRF team',          8,     'NDRF HQ, Noida'),
('rescue_team', 'State rescue team',  12,    'State HQ, Lucknow'),
('rescue_team', 'Boat rescue unit',   6,     'River Authority, Patna');