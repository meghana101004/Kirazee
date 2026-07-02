SET @sno := 0;

SELECT 
    @sno := @sno + 1 AS `S.no`,
    DATE(base.transaction_date) AS `Sale Date`,
    base.transaction_date AS `Date & Time`,
    base.order_id AS `Order ID`,

    items.item_id AS `Item ID`,
    items.item_name AS `Item Name`,
    items.qty AS `Quantity`,
    ROUND(items.price, 2) AS `Unit Price`,

    base.token_number AS `Token Number`,
    base.order_type AS `Order Type`,
    base.business_id AS `Business ID`,
    base.platform AS `Platform`,
    base.payment_method AS `Payment Method`,
    base.category AS `Category`,

    ROUND(base.total_amount, 2) AS `Total Order Amount`,

    ROUND(COALESCE(cat.gst_rate, 0), 2) AS `GST %`,

    ROUND(
        CASE 
            WHEN base.platform = 'App'
                THEN COALESCE(items.gst_amount, 0)
            ELSE base.gst_amount
        END, 2
    ) AS `GST Amount`,

    base.payment_status AS `Payment Status`,
    base.customer_mobile AS `Customer Mobile`,
    base.service_type AS `Service Type`

FROM (

    /* ================= POS ================= */
    SELECT 
        bco.created_at AS transaction_date,

        CAST(bco.order_id AS CHAR) COLLATE utf8mb4_unicode_ci AS order_id,

        (
            SELECT JSON_ARRAYAGG(
                JSON_OBJECT(
                    'item_id', COALESCE(bci.product_id, bci.menu_item_id),
                    'item_name', bci.item_name,
                    'qty', bci.quantity,
                    'price', bci.unit_price,
                    'gst_amount', 0
                )
            )
            FROM business_counter_items bci
            WHERE bci.order_id = bco.order_id
        ) AS item_json,

        CAST(bco.token_number AS CHAR) COLLATE utf8mb4_unicode_ci AS token_number,

        bco.order_type COLLATE utf8mb4_unicode_ci AS order_type,
        bco.business_id COLLATE utf8mb4_unicode_ci AS business_id,

        'POS' COLLATE utf8mb4_unicode_ci AS platform,
        bco.payment_method COLLATE utf8mb4_unicode_ci AS payment_method,
        'Counter' COLLATE utf8mb4_unicode_ci AS category,

        bco.total_amount AS total_amount,
        bco.gst_total AS gst_amount,

        bco.status COLLATE utf8mb4_unicode_ci AS payment_status,
        bco.customer_mobile COLLATE utf8mb4_unicode_ci AS customer_mobile,
        bco.service_mode COLLATE utf8mb4_unicode_ci AS service_type

    FROM business_counter_orders bco
    WHERE bco.business_id = 'KIR1478820251021185505'


    UNION ALL


    /* ================= APP ================= */
    SELECT 
        o.created_at AS transaction_date,

        o.order_number COLLATE utf8mb4_unicode_ci AS order_id,

        (
            SELECT JSON_ARRAYAGG(
                JSON_OBJECT(
                    'item_id', COALESCE(oi.product_item_id, oi.menu_item_id),
                    'item_name', oi.item_name_snapshot,
                    'qty', oi.quantity,
                    'price', oi.unit_price_snapshot,
                    'gst_amount', oi.gst_amount
                )
            )
            FROM order_items oi
            WHERE oi.order_id = o.order_id
        ) AS item_json,

        CAST(o.token_num AS CHAR) COLLATE utf8mb4_unicode_ci AS token_number,

        o.order_type COLLATE utf8mb4_unicode_ci AS order_type,
        o.business_id COLLATE utf8mb4_unicode_ci AS business_id,

        'App' COLLATE utf8mb4_unicode_ci AS platform,

        COALESCE(p.payment_method, 'Online') COLLATE utf8mb4_unicode_ci AS payment_method,

        'Grocery' COLLATE utf8mb4_unicode_ci AS category,

        o.final_amount AS total_amount,
        0 AS gst_amount,

        o.status COLLATE utf8mb4_unicode_ci AS payment_status,
        '' COLLATE utf8mb4_unicode_ci AS customer_mobile,
        'Delivery' COLLATE utf8mb4_unicode_ci AS service_type

    FROM orders o

    LEFT JOIN (
        SELECT order_id, MAX(id) AS max_id
        FROM payments
        WHERE status = 'success'
        GROUP BY order_id
    ) p1 ON p1.order_id = o.order_id

    LEFT JOIN payments p ON p.id = p1.max_id

    WHERE o.business_id = 'KIR1478820251021185505'

) AS base


/* Expand JSON */
JOIN JSON_TABLE(
    base.item_json,
    '$[*]' COLUMNS (
        item_id BIGINT PATH '$.item_id',
        item_name VARCHAR(255) PATH '$.item_name',
        qty INT PATH '$.qty',
        price DECIMAL(10,2) PATH '$.price',
        gst_amount DECIMAL(10,2) PATH '$.gst_amount'
    )
) AS items


LEFT JOIN Groceries_Products gp
    ON gp.product_id = items.item_id

LEFT JOIN Groceries_Categories cat
    ON cat.category_id = gp.category_id
    AND cat.business_id = base.business_id


ORDER BY base.transaction_date DESC;
