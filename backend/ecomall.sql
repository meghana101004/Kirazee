SELECT
    DATE(base.transaction_date) AS `Sale Date`,
    base.transaction_date AS `Date & Time`,
    base.order_id AS `Order ID`,

    items.item_id AS `Item ID`,
    items.item_name AS `Item Name`,
    items.qty AS `Quantity`,
    items.price AS `Unit Price`,

    CONCAT(ROUND(items.gst,0),'%') AS `GST %`,

    base.token_number AS `Token Number`,
    base.order_type AS `Order Type`,
    base.business_id AS `Business ID`,
    base.platform AS `Platform`,
    base.payment_method AS `Payment Method`,
    base.category AS `Category`,

    base.total_amount AS `Total Order Amount`,
    base.gst_amount AS `GST Amount`,

    base.payment_status AS `Payment Status`,
    base.customer_mobile AS `Customer Mobile`,
    base.service_type AS `Service Type`

FROM
(

/* ---------- ONLINE ORDERS ---------- */

SELECT
    o.order_id,
    o.created_at AS transaction_date,
    o.token_num AS token_number,
    o.order_type COLLATE utf8mb4_general_ci AS order_type,
    o.business_id COLLATE utf8mb4_general_ci AS business_id,
    'ONLINE' COLLATE utf8mb4_general_ci AS platform,
    'ONLINE' COLLATE utf8mb4_general_ci AS payment_method,
    'ONLINE ORDER' COLLATE utf8mb4_general_ci AS category,
    o.final_amount AS total_amount,
    o.status COLLATE utf8mb4_general_ci AS payment_status,
    r.mobileNumber COLLATE utf8mb4_general_ci AS customer_mobile,
    o.order_type COLLATE utf8mb4_general_ci AS service_type,

    (
        SELECT SUM(gst_amount)
        FROM order_items oi2
        WHERE oi2.order_id = o.order_id
    ) AS gst_amount

FROM orders o
LEFT JOIN registrations r
    ON r.user_id = o.user_id

WHERE 
    o.business_id = 'KIR1489320251101174639'
    AND o.status NOT IN ('cancelled','rejected')

UNION ALL


/* ---------- COUNTER ORDERS ---------- */

SELECT
    bco.order_id,
    bco.created_at AS transaction_date,
    bco.token_number,
    bco.order_type COLLATE utf8mb4_general_ci,
    bco.business_id COLLATE utf8mb4_general_ci,
    'COUNTER' COLLATE utf8mb4_general_ci,
    bco.payment_method COLLATE utf8mb4_general_ci,
    'POS ORDER' COLLATE utf8mb4_general_ci,
    bco.total_amount,
    bco.status COLLATE utf8mb4_general_ci,
    bco.customer_mobile COLLATE utf8mb4_general_ci,
    bco.service_mode COLLATE utf8mb4_general_ci,
    bco.gst_total

FROM business_counter_orders bco

WHERE 
    bco.business_id = 'KIR1489320251101174639'
    AND bco.status NOT IN ('cancelled')

) base


JOIN
(

/* ---------- ONLINE ITEMS ---------- */

SELECT
    oi.order_id,
    oi.item_id,
    oi.item_name_snapshot COLLATE utf8mb4_general_ci AS item_name,
    oi.quantity AS qty,
    oi.unit_price_snapshot AS price,

    ROUND((oi.gst_amount / (oi.total_price - oi.gst_amount)) * 100) AS gst

FROM order_items oi


UNION ALL


/* ---------- COUNTER ITEMS ---------- */

SELECT
    bci.order_id,
    bci.id AS item_id,
    bci.item_name COLLATE utf8mb4_general_ci,
    bci.quantity,
    bci.unit_price,

    ROUND((bci.gst / (bci.line_total - bci.gst)) * 100)

FROM business_counter_items bci

) items

ON items.order_id = base.order_id

ORDER BY base.transaction_date DESC;