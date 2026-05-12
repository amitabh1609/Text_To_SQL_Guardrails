-- Text-to-SQL Guardrails: Supply Chain Schema
-- PostgreSQL 15

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id     SERIAL PRIMARY KEY,
    supplier_name   VARCHAR(120) NOT NULL,
    country         VARCHAR(60),
    rating          NUMERIC(3,1) CHECK (rating >= 1.0 AND rating <= 5.0),
    is_active       BOOLEAN DEFAULT TRUE,
    onboarded_at    DATE
);

CREATE TABLE IF NOT EXISTS products (
    product_id      SERIAL PRIMARY KEY,
    sku             VARCHAR(40) UNIQUE NOT NULL,
    product_name    VARCHAR(200) NOT NULL,
    category        VARCHAR(80),
    unit_cost       NUMERIC(12,2),
    reorder_level   INTEGER,
    is_discontinued BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id    SERIAL PRIMARY KEY,
    warehouse_name  VARCHAR(100) NOT NULL,
    city            VARCHAR(80),
    country         VARCHAR(60),
    capacity_units  INTEGER
);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id    SERIAL PRIMARY KEY,
    product_id      INTEGER REFERENCES products(product_id),
    warehouse_id    INTEGER REFERENCES warehouses(warehouse_id),
    quantity_on_hand INTEGER NOT NULL DEFAULT 0,
    last_updated    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id               SERIAL PRIMARY KEY,
    supplier_id         INTEGER REFERENCES suppliers(supplier_id),
    product_id          INTEGER REFERENCES products(product_id),
    warehouse_id        INTEGER REFERENCES warehouses(warehouse_id),
    quantity_ordered    INTEGER NOT NULL,
    unit_price          NUMERIC(12,2),
    order_date          DATE,
    expected_delivery   DATE,
    actual_delivery     DATE,
    status              VARCHAR(30) CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id     SERIAL PRIMARY KEY,
    po_id           INTEGER REFERENCES purchase_orders(po_id),
    shipped_at      TIMESTAMP,
    delivered_at    TIMESTAMP,
    carrier         VARCHAR(80),
    tracking_number VARCHAR(80)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_product  ON purchase_orders(product_id);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_status   ON purchase_orders(status);
CREATE INDEX IF NOT EXISTS idx_purchase_orders_order_date ON purchase_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_inventory_product        ON inventory(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_warehouse      ON inventory(warehouse_id);
CREATE INDEX IF NOT EXISTS idx_shipments_po             ON shipments(po_id);
CREATE INDEX IF NOT EXISTS idx_suppliers_active         ON suppliers(is_active);
CREATE INDEX IF NOT EXISTS idx_products_category        ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_discontinued    ON products(is_discontinued);
