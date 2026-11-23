PRAGMA foreign_keys = ON;

CREATE TABLE customers (customer_id TEXT PRIMARY KEY NOT NULL, region TEXT NOT NULL);
CREATE TABLE products (product_id TEXT PRIMARY KEY NOT NULL, category TEXT NOT NULL);
CREATE TABLE sellers (seller_id TEXT PRIMARY KEY NOT NULL, seller_name TEXT NOT NULL);

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY NOT NULL,
    customer_id TEXT NOT NULL REFERENCES customers,
    purchased_on TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('delivered', 'canceled', 'shipped')),
    promised_on TEXT,
    delivered_on TEXT
);

CREATE TABLE order_items (
    order_id TEXT NOT NULL REFERENCES orders,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id TEXT NOT NULL REFERENCES products,
    seller_id TEXT NOT NULL REFERENCES sellers,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
    freight_cents INTEGER NOT NULL CHECK (freight_cents >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE VIEW DimCustomer AS SELECT customer_id, region FROM customers;
CREATE VIEW DimProduct AS SELECT product_id, category FROM products;
CREATE VIEW DimSeller AS SELECT seller_id, seller_name FROM sellers;

CREATE VIEW DimDate AS
WITH RECURSIVE dates(purchased_on) AS (
    SELECT MIN(purchased_on) FROM orders HAVING COUNT(*) > 0
    UNION ALL
    SELECT date(purchased_on, '+1 day')
    FROM dates WHERE purchased_on < (SELECT MAX(purchased_on) FROM orders)
)
SELECT purchased_on, substr(purchased_on, 1, 7) AS purchase_month FROM dates;

CREATE VIEW FactOrder AS
WITH item_totals AS (
    SELECT order_id, COUNT(*) AS item_lines,
           SUM(price_cents) AS merchandise_cents, SUM(freight_cents) AS freight_cents
    FROM order_items GROUP BY order_id
)
SELECT o.order_id, o.customer_id, o.purchased_on, o.status, o.promised_on, o.delivered_on,
       COALESCE(i.item_lines, 0) AS item_lines,
       COALESCE(i.merchandise_cents, 0) AS merchandise_cents,
       COALESCE(i.freight_cents, 0) AS freight_cents,
       CASE WHEN o.status = 'delivered' AND o.delivered_on IS NOT NULL AND o.promised_on IS NOT NULL
            THEN o.delivered_on <= o.promised_on END AS on_time
FROM orders o LEFT JOIN item_totals i USING (order_id);

CREATE VIEW FactOrderItem AS
SELECT i.order_id, i.line_no, i.product_id, i.seller_id, o.customer_id,
       o.purchased_on, o.status, i.price_cents, i.freight_cents
FROM order_items i JOIN orders o USING (order_id);
