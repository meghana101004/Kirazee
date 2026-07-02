# Business App API Documentation

- Base path: `/kirazee/business/`
- Purpose: Business onboarding and owner operations: create/edit business, payment and refunds, menu and product inventory (restaurant and retail), BOM (ingredients), coupons, delivery/points configuration, and order analytics.
- Key models/tables:
  - Business domain: `kirazee_app.Business (businesses)`, `kirazee_app.BusinessMapping (business_mapping)`, `kirazee_app.BusinessFinancial (business_financials)`, `kirazee_app.Registration (registrations)`
  - Menu/products: `business.MenuItems (menuItems)`, `business.productItems (GroceryItems)`
  - BOM: `business.BOM (bill_of_materials)`, `business.BillOfMaterialsLog (bill_of_materials_log)`
  - Payments: `business.BusinessPayment (business_payments)`
  - Coupons (from consumer app): `consumer.Coupons (coupons)`, `consumer.CouponRules (coupon_rules)`, `consumer.CouponRedemptions (coupon_redemptions)`
  - Delivery/points (from consumer app): `consumer.DeliveryCharges (delivery_charges)`, `consumer.PointsConfiguration (points_configuration)`

## Endpoints

### Business Setup
- GET `/fetch-types/` → `fetchbusinessesTypes`
  - Purpose: List active business types.
  - DB: `business_types`.
  - Response 200: `[{ code, type, categories }]`

- GET `/business-features/` → `fetchbusinessFeatures`
  - Purpose: List active business features.
  - DB: `business_features`.
  - Response 200: `[{ feature_id, details }]`

- GET|POST|PUT `/create` → `CreateBusinessAPIView`
  - Purpose: Create, fetch, or update a business in sections.
  - Methods and parameters (multiple ways):
    - GET: query `userID`. Returns existing/draft business for user + completion status and financials.
    - POST: query `userID` and `section` in {"1","2","3"}
      - Section 1 body: base details of `Business` (supports file uploads `logo`, `banner`).
      - Section 2 body: address/location fields of `Business`.
      - Section 3 body: `BusinessFinancial` payload; will auto-fill Razorpay keys from settings if missing.
    - PUT: query `userID` and `section` to update specific section; body fields like POST.
  - Responses (examples):
    - 201/200 success with `business_id` and section data.
    - 400/403/404 with `{ error: string }`.
  - DB: `businesses`, `business_financials`, `business_mapping`, `registrations`.

- GET `/parse-address/` → `parse_address_from_maps`
  - Purpose: Parse a Google Maps URL into address parts.
  - Body: `{ maps_url: string }`
  - Response 200: `{ address, city, state, pincode, country, latitude, longitude, formatted_address }`

### Payments (Onboarding)
- GET `/payment-gateway/` → `payment_gateway`
  - Purpose: Render payment page for business creation.
  - Query: `userID`, `amount`, `business_id`.
  - Response: HTML page.

- POST `/save-payment-data/` → `save_payment_data`
  - Purpose: Store payment outcome with optional Razorpay verification.
  - Body: `{ transaction_id, amount, status, business_id, user_id, payment_method?, upi_id? }`
  - Responses: 200 `{ status: 'success', payment: {...} }`, 400/500 errors.
  - DB: `business_payments`, updates `businesses.paymentstatus` on success.

- POST `/process-refund/` → `process_refund`
  - Purpose: Initiate refund via Razorpay and email customer.
  - Body: `{ transaction_id, amount }`
  - Responses: 200 `{ message, refund_id }` or errors.
  - DB: updates `business_payments` (refund fields).

### Onboarding (Owner)
- GET `/onboarding/progress/<int:user_id>/` → `get_user_progress`
  - Purpose: Get latest onboarding progress for a user.
  - Response 200: `{ success, data: { user_id, current_step, completed_steps, total_steps, application_id, status, last_updated, step_data } }`

- POST `/onboarding/initialize` → `initialize_application`
  - Body: `{ user_id, resume_existing?=true }`
  - Response 201|200: `{ success, data: { application_id, current_step, redirect_to_step, message } }`

- POST `/onboarding/step1/save` → `step1_save`
  - Body: `{ application_id, user_id, auto_save?=false, business_name, business_type, address, registration_number, store_description }`
  - Response 200: `{ success, data: { step_completed, next_step, application_id, validation_errors, saved_at } }`

- GET `/onboarding/step1/<str:application_id>/` → `step1_get`
  - Purpose: Fetch saved Step 1 data.
  - Response 200: `{ success, data: { ...step1 fields..., last_updated } }`

- POST `/onboarding/step2/upload` → `step2_upload`
  - Form-Data (multipart): `application_id`, `document_type`, `file`
  - Response 201: `{ success, data: { document_id, document_type, file_name, file_size, upload_url, uploaded_at } }`

- GET `/onboarding/step2/<str:application_id>/documents` → `step2_get_documents`
  - Purpose: List uploaded documents and missing required ones.
  - Response 200: `{ success, data: { documents, required_documents, missing_documents, all_uploaded } }`

- POST `/onboarding/step2/complete` → `step2_complete`
  - Body: `{ application_id, user_id }`
  - Response 200: `{ success, data: { step_completed: true, next_step: 3 } }`

- POST `/onboarding/step3/save` → `step3_save`
  - Body: `{ application_id, user_id, working_hours, payment_modes, delivery_preferences }`
  - Response 200: `{ success, data: { step_completed, application_submitted, application_id, submission_date, estimated_review_time } }`

- POST `/onboarding/submit` → `submit_application`
  - Body: `{ application_id, user_id }`
  - Response 200: `{ success, data: { application_id, status: 'submitted', submitted_at, reference_number, estimated_review_time, next_steps } }`

- GET `/onboarding/status/<str:application_id>/` → `get_application_status`
  - Purpose: Track review progress after submission.
  - Response 200: `{ success, data: { application_id, status, submitted_at, last_updated, review_progress, admin_comments, rejection_reasons, approval_details } }`

- POST `/onboarding/auto-save` → `autosave`
  - Body: `{ application_id, user_id, step: 1|2|3, form_data: {} }`
  - Response 200: `{ success, message, timestamp }`

- POST `/onboarding/heartbeat` → `heartbeat`
  - Body: `{ application_id, user_id, current_step }`
  - Response 200: `{ success, message }`

- GET `/onboarding/config/business-types` → `onboarding_config_business_types`
  - Purpose: Get type-specific requirements to drive onboarding UI.
  - Response 200: `{ success, data: { business_types: [{ type, label, required_documents, registration_patterns, additional_fields }] } }`

### Onboarding (Admin Review)
- GET `/onboarding/admin/business-applications/pending` → `admin_list_pending`
  - Query: `page?=1`, `limit?<=100`, `category?`, `search?`
  - Response 200: `{ success, data: { applications: [...], pagination: { current_page, total_pages, total_items, items_per_page }, statistics } }`

- GET `/onboarding/admin/business-applications/<str:application_id>/details` → `admin_application_details`
  - Purpose: Detailed view including documents and timeline.
  - Response 200: `{ success, data: { application_id, business_info, owner_info, documents, operational_details, submission_timeline } }`

- POST `/onboarding/admin/business-applications/<str:application_id>/review` → `admin_review_application`
  - Body: `{ action: 'approve'|'reject'|'request_changes', admin_id?, comments?, rejection_reasons?:[], required_changes?:[], business_id_assignment? }`
  - Response 200: on approve `{ success, data: { application_id, new_status: 'approved', business_id, reviewed_at, reviewed_by, notifications_sent } }`; otherwise `{ success, data: { application_id, new_status, reviewed_at, reviewed_by } }`

### My Businesses (Hierarchy)
- GET `/user-businesses/` → `get_user_businesses`
  - Purpose: List businesses owned by a user, including sublevel branches when master.
  - Query: `user_id`.
  - DB: `business_mapping`, `businesses` (master/sub businesses), optionally `coupon_redemptions` during analytics.

### Menu & Product Items (Owner)
- POST `/add-menu-items` → `CreateMenuItemsAPIView`
  - Purpose: Create a restaurant menu item.
  - Query: `userID`, `business_id`.
  - Body: `MenuItemsSerializer` fields; supports `item_image` upload; auto-computes GST charges.
  - DB: `menuItems`.

- PUT|PATCH|DELETE `/menu-items-management/<int:item_id>/` → `MenuItemsManagementAPIView`
  - Purpose: Update or delete a menu item; supports image recompress.
  - Query: `userID`, `business_id`.
  - DB: `menuItems`.

- POST `/add-bom-items` → `addBOMItems`
  - Purpose: Add an ingredient (BOM) for a menu item; logs to BOM log.
  - Query: `business_id`, `product_id`, `user_id?`
  - DB: `bill_of_materials`, `bill_of_materials_log`.

- PUT|PATCH|DELETE `/bom-items-management/` → `BOMItemsManagementAPIView`
  - Purpose: Update/soft-delete a BOM item with audit logging.
  - Query: `user_id`, `business_id`, `bom_id`.
  - DB: `bill_of_materials`, `bill_of_materials_log`.

- POST `/add-product-items` → `addProductItems` (serializer `productItemsSerializer` via views usage)
  - Purpose: Create a retail product item under GroceryItems table.
  - Query: `userID`, `business_id`.
  - DB: `GroceryItems`.

- PUT `/product-items-management/<int:item_id>/` → `updateProductItems`
  - Purpose: Update a retail product item.
  - Query: `userID`, `business_id`.
  - DB: `GroceryItems`.

- GET `/menu-details/<int:item_id>/` → `menuDetailView`
- GET `/product-details/<int:item_id>/` → `productDetailView`
  - Purpose: Public item detail pages.

### Coupons (Owner)
- POST `/coupons/create/` → `create_coupon`
  - Body: `{ user_id, business_id, coupon_code, discount_type, discount_value, valid_from, valid_to, ... rules?: [] }`
  - DB: `coupons`, `coupon_rules`.

- POST `/coupons/business/<str:business_id>/` → `list_business_coupons`
  - Body: `{ user_id, filters? }` where filters support `status`, `business_type`, `date_from`, `date_to`.
  - DB: `business_mapping`, `businesses`, `coupons`, `coupon_rules`, optional `coupon_redemptions`.

- PUT `/coupons/<str:coupon_id>/update/` → `update_coupon`
- DELETE `/coupons/<str:coupon_id>/delete/` → `delete_coupon`
- POST `/coupons/<str:coupon_id>/add-rule/` → `add_coupon_rule`
- GET `/coupons/analytics/` → `coupon_analytics`
  - Purpose: Manage coupon lifecycle; analytics aggregates redemptions.
  - DB: `coupons`, `coupon_rules`, `coupon_redemptions`.

### Delivery & Points Configuration (Owner)
- POST `/delivery/configure/` → `configure_delivery_charges`
- GET `/delivery/configuration/` → `get_delivery_configuration`
  - Body/Query: `{ user_id, business_id? }` (auto-derive from mapping if absent)
  - DB: `delivery_charges`.

### Categories & Mapping (Owner)
- GET `/categories/universal/` → `list_universal_categories`
  - Purpose: List universal categories for selection by business owners.
  - Query: `search?`, `parent_category_id?`, `limit?=100`, `offset?=0`
  - DB: `universal_Categories`

- POST `/categories/mapping/` → `add_category_mapping`
  - Purpose: Create/Upsert mapping(s) between a business and universal categories.
  - Query: `userID` (required), `business_id` (required)
  - Body: `{ category_id, is_active? }` or `{ category_ids: [], is_active? }`
  - Access: Requires ownership via `BusinessMapping`.
  - DB: `category_mapping`, `universal_Categories`, `businesses`

- PUT|PATCH `/categories/mapping/<int:mapping_id>/` → `update_category_mapping`
  - Purpose: Update a mapping (toggle `is_active`).
  - Query: `userID`, `business_id`
  - Body: `{ is_active: 0|1 }`

- DELETE `/categories/mapping/<int:mapping_id>/delete/` → `delete_category_mapping`
  - Purpose: Remove a mapping.
  - Query: `userID`, `business_id`

- GET `/categories/selected/` → `selected_categories_for_business`
  - Purpose: List chosen categories for a business.
  - Query: `business_id` (required), `only_active?=true`
  - DB: `category_mapping` JOIN `universal_Categories`

## Common Error Responses
- 400: `{ error: string }` when missing/invalid parameters
- 403: `{ error: string }` for authorization
- 404: `{ error: string }` when resource not found
- 500: `{ error: string }` unexpected errors
## Cross-App Models/Serializers Involved
- From `kirazee_app/serializers.py`: business section serializers for `Business` and `BusinessFinancial`
- From `consumer/serializers.py`: `DeliveryChargesSerializer`, `PointsConfigurationSerializer`, `Coupon*` serializers

## Notes
- Image uploads are recompressed (JPEG quality ~75%) for `logo`, `banner`, and `item_image`.
- `CreateBusinessAPIView` handles partial updates per section and ensures mappings.
- Currency assumed `INR`.
