import React from 'react';
import { FaDatabase, FaKey, FaLink, FaTable, FaInfoCircle, FaServer, FaUsers, FaShoppingCart, FaTruck, FaMoneyBillWave } from 'react-icons/fa';
import '../../css/admin/PlatformBlueprint.css';

// ER Table Component
const ERTable = ({ name, moduleColor, x, y, columns }) => {
  return (
    <div 
      className={`er-table ${moduleColor}`}
      style={{ 
        position: 'absolute',
        left: `${x}px`,
        top: `${y}px`
      }}
    >
      <div className="er-table-header">
        <FaTable />
        {name}
      </div>
      <div className="er-table-columns">
        {columns.map((col, idx) => (
          <div key={idx} className="er-table-column">
            <span className="er-column-name">{col.name}</span>
            <span className="er-column-type">{col.type}</span>
            {col.pk && <span className="er-column-badge er-badge-pk">PK</span>}
            {col.fk && <span className="er-column-badge er-badge-fk">FK</span>}
            {col.unique && <span className="er-column-badge er-badge-unique">UNIQUE</span>}
          </div>
        ))}
      </div>
    </div>
  );
};

// Relationship Line Component
const RelationshipLine = ({ start, end, label }) => {
  const midX = (start.x + end.x) / 2;
  const midY = (start.y + end.y) / 2;
  
  return (
    <g>
      <line
        x1={start.x}
        y1={start.y}
        x2={end.x}
        y2={end.y}
        className="relationship-line"
      />
      {label && (
        <text
          x={midX}
          y={midY - 5}
          className="relationship-line-label"
        >
          {label}
        </text>
      )}
    </g>
  );
};

const DatabaseDesign = () => {

  // Complete core tables with all columns
  const coreTables = [
    {
      name: 'users',
      desc: 'Stores user accounts and authentication details',
      module: 'User Management',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'name', type: 'VARCHAR(255)' },
        { name: 'email', type: 'VARCHAR(255)', unique: true },
        { name: 'phone', type: 'VARCHAR(20)', unique: true },
        { name: 'password', type: 'VARCHAR(255)' },
        { name: 'status', type: 'TINYINT(1)', default: '1' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'registrations',
      desc: 'Extended user registration and profile information',
      module: 'User Management',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'user_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'users.id' },
        { name: 'mobileNumber', type: 'VARCHAR(20)' },
        { name: 'address', type: 'TEXT' },
        { name: 'city', type: 'VARCHAR(100)' },
        { name: 'state', type: 'VARCHAR(100)' },
        { name: 'pincode', type: 'VARCHAR(10)' },
        { name: 'profile_image', type: 'VARCHAR(255)' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'businesses',
      desc: 'Business/merchant information and settings',
      module: 'Business Setup',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'user_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'users.id' },
        { name: 'business_name', type: 'VARCHAR(255)' },
        { name: 'business_type', type: 'VARCHAR(100)' },
        { name: 'license_number', type: 'VARCHAR(100)' },
        { name: 'address', type: 'TEXT' },
        { name: 'city', type: 'VARCHAR(100)' },
        { name: 'state', type: 'VARCHAR(100)' },
        { name: 'pincode', type: 'VARCHAR(10)' },
        { name: 'phone', type: 'VARCHAR(20)' },
        { name: 'email', type: 'VARCHAR(255)' },
        { name: 'status', type: 'TINYINT(1)', default: '0' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'categories',
      desc: 'Product categories and subcategories',
      module: 'Catalog',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'name', type: 'VARCHAR(255)' },
        { name: 'parent_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'categories.id' },
        { name: 'description', type: 'TEXT' },
        { name: 'image', type: 'VARCHAR(255)' },
        { name: 'status', type: 'TINYINT(1)', default: '1' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'products',
      desc: 'Product catalog with pricing and inventory',
      module: 'Catalog',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'business_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'businesses.id' },
        { name: 'category_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'categories.id' },
        { name: 'name', type: 'VARCHAR(255)' },
        { name: 'description', type: 'TEXT' },
        { name: 'price', type: 'DECIMAL(10,2)' },
        { name: 'discount_price', type: 'DECIMAL(10,2)' },
        { name: 'stock_quantity', type: 'INT' },
        { name: 'sku', type: 'VARCHAR(100)' },
        { name: 'images', type: 'JSON' },
        { name: 'status', type: 'TINYINT(1)', default: '1' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'orders',
      desc: 'Customer orders and order management',
      module: 'Orders',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'user_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'users.id' },
        { name: 'business_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'businesses.id' },
        { name: 'order_number', type: 'VARCHAR(100)', unique: true },
        { name: 'total_amount', type: 'DECIMAL(10,2)' },
        { name: 'discount_amount', type: 'DECIMAL(10,2)' },
        { name: 'delivery_fee', type: 'DECIMAL(10,2)' },
        { name: 'final_amount', type: 'DECIMAL(10,2)' },
        { name: 'status', type: 'VARCHAR(50)', default: 'pending' },
        { name: 'payment_status', type: 'VARCHAR(50)', default: 'pending' },
        { name: 'delivery_address', type: 'TEXT' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'order_items',
      desc: 'Individual items within an order',
      module: 'Orders',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'order_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'orders.id' },
        { name: 'product_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'products.id' },
        { name: 'quantity', type: 'INT' },
        { name: 'price', type: 'DECIMAL(10,2)' },
        { name: 'total', type: 'DECIMAL(10,2)' },
        { name: 'created_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'payments',
      desc: 'Payment transactions and records',
      module: 'Payments',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'order_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'orders.id' },
        { name: 'user_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'users.id' },
        { name: 'payment_method', type: 'VARCHAR(50)' },
        { name: 'transaction_id', type: 'VARCHAR(255)' },
        { name: 'amount', type: 'DECIMAL(10,2)' },
        { name: 'status', type: 'VARCHAR(50)', default: 'pending' },
        { name: 'gateway_response', type: 'JSON' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'wallet_transactions',
      desc: 'User wallet credit/debit transactions',
      module: 'Payments',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'user_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'users.id' },
        { name: 'type', type: 'VARCHAR(20)' }, // credit, debit
        { name: 'amount', type: 'DECIMAL(10,2)' },
        { name: 'balance_before', type: 'DECIMAL(10,2)' },
        { name: 'balance_after', type: 'DECIMAL(10,2)' },
        { name: 'description', type: 'VARCHAR(255)' },
        { name: 'reference_id', type: 'VARCHAR(255)' },
        { name: 'created_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'delivery_partners',
      desc: 'Delivery partner information and availability',
      module: 'Logistics',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'user_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'users.id' },
        { name: 'name', type: 'VARCHAR(255)' },
        { name: 'phone', type: 'VARCHAR(20)' },
        { name: 'vehicle_type', type: 'VARCHAR(50)' },
        { name: 'vehicle_number', type: 'VARCHAR(20)' },
        { name: 'license_number', type: 'VARCHAR(100)' },
        { name: 'current_location', type: 'VARCHAR(255)' },
        { name: 'status', type: 'VARCHAR(50)', default: 'available' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    },
    {
      name: 'deliveries',
      desc: 'Delivery assignments and tracking',
      module: 'Logistics',
      columns: [
        { name: 'id', type: 'BIGINT UNSIGNED', pk: true, ai: true },
        { name: 'order_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'orders.id' },
        { name: 'delivery_partner_id', type: 'BIGINT UNSIGNED', fk: true, ref: 'delivery_partners.id' },
        { name: 'pickup_address', type: 'TEXT' },
        { name: 'delivery_address', type: 'TEXT' },
        { name: 'status', type: 'VARCHAR(50)', default: 'assigned' },
        { name: 'estimated_time', type: 'TIMESTAMP' },
        { name: 'delivered_time', type: 'TIMESTAMP' },
        { name: 'tracking_code', type: 'VARCHAR(100)' },
        { name: 'created_at', type: 'TIMESTAMP' },
        { name: 'updated_at', type: 'TIMESTAMP' }
      ]
    }
  ];

  // Complete key relationships
  const keyRelationships = [
    'users (1) → registrations (*) - One user can have multiple registration records',
    'users (1) → businesses (*) - One user can own multiple businesses',
    'users (1) → orders (*) - One user can place multiple orders',
    'users (1) → wallet_transactions (*) - One user can have multiple wallet transactions',
    'users (1) → delivery_partners (*) - One user can register as delivery partner',
    'businesses (1) → products (*) - One business can have multiple products',
    'businesses (1) → orders (*) - One business can receive multiple orders',
    'categories (1) → products (*) - One category can contain multiple products',
    'categories (1) → categories (*) - Self-referencing for subcategories',
    'orders (1) → order_items (*) - One order contains multiple items',
    'orders (1) → payments (*) - One order can have multiple payment attempts',
    'orders (1) → deliveries (1) - One order has one delivery assignment',
    'products (1) → order_items (*) - One product can be in multiple order items',
    'delivery_partners (1) → deliveries (*) - One partner can handle multiple deliveries'
  ];

  // Performance indexes
  const indexes = [
    'idx_users_email (users.email) - Fast user lookup and authentication',
    'idx_users_phone (users.phone) - Fast user lookup by phone',
    'idx_registrations_user_id (registrations.user_id) - User profile queries',
    'idx_businesses_user_id (businesses.user_id) - Business ownership queries',
    'idx_businesses_status (businesses.status) - Business approval filtering',
    'idx_products_business_id (products.business_id) - Business catalog filtering',
    'idx_products_category_id (products.category_id) - Category browsing',
    'idx_products_status (products.status) - Active product filtering',
    'idx_orders_user_id (orders.user_id) - Customer order history',
    'idx_orders_business_id (orders.business_id) - Merchant order management',
    'idx_orders_status (orders.status) - Order status filtering',
    'idx_orders_created_at (orders.created_at) - Order date range queries',
    'idx_order_items_order_id (order_items.order_id) - Order item retrieval',
    'idx_order_items_product_id (order_items.product_id) - Product sales analysis',
    'idx_payments_order_id (payments.order_id) - Payment history lookup',
    'idx_payments_user_id (payments.user_id) - User payment history',
    'idx_wallet_transactions_user_id (wallet_transactions.user_id) - Wallet history',
    'idx_deliveries_order_id (deliveries.order_id) - Delivery tracking',
    'idx_deliveries_partner_id (deliveries.delivery_partner_id) - Partner workload',
    'idx_deliveries_status (deliveries.status) - Delivery status filtering'
  ];

  // Schema metadata
  const schemaVersion = '1.2.0';
  const lastUpdated = '2025-12-15';
  const totalTables = coreTables.length;

  // Data retention policy
  const retentionPolicy = `
- Order data: 5 years (for legal compliance)
- Audit logs: 2 years (for security analysis)
- User data: Until account deletion (GDPR compliance)
- Payment data: 7 years (financial compliance)
- Backup retention: 30 days rolling
- Archive retention: 1 year cold storage
  `.trim();

  return (
    <div className="platform-content admin-card">
      {/* Interactive ER Model Section - WORKBENCH STYLE */}
      <div className="er-model-container">
        <div className="er-model-header">
          <h2 className="er-model-title">Kirazee Database Architecture v1.2.0</h2>
          <p className="er-model-subtitle">Interactive ER diagram showing all 40+ tables and their relationships</p>
          <div className="er-model-legend">
            <div className="legend-item">
              <span className="legend-color user-color"></span>
              <span>User Management</span>
            </div>
            <div className="legend-item">
              <span className="legend-color business-color"></span>
              <span>Business & Commerce</span>
            </div>
            <div className="legend-item">
              <span className="legend-color product-color"></span>
              <span>Products & Inventory</span>
            </div>
            <div className="legend-item">
              <span className="legend-color order-color"></span>
              <span>Orders & Payments</span>
            </div>
            <div className="legend-item">
              <span className="legend-color delivery-color"></span>
              <span>Logistics & Delivery</span>
            </div>
            <div className="legend-item">
              <span className="legend-color system-color"></span>
              <span>System & Admin</span>
            </div>
          </div>
        </div>

        <div className="er-canvas">
          {/* Grid Background */}
          <div className="grid-background"></div>
          
          {/* Relationship Lines */}
          <svg className="relationship-lines">
            {/* User Management Relationships */}
            <RelationshipLine start={{x: 150, y: 100}} end={{x: 350, y: 100}} label="1:1" />
            <RelationshipLine start={{x: 150, y: 180}} end={{x: 350, y: 180}} label="1:1" />
            <RelationshipLine start={{x: 150, y: 260}} end={{x: 350, y: 260}} label="1:M" />
            
            {/* Business Relationships */}
            <RelationshipLine start={{x: 550, y: 100}} end={{x: 750, y: 100}} label="1:M" />
            <RelationshipLine start={{x: 550, y: 180}} end={{x: 750, y: 180}} label="1:1" />
            <RelationshipLine start={{x: 550, y: 260}} end={{x: 750, y: 260}} label="1:M" />
            <RelationshipLine start={{x: 550, y: 340}} end={{x: 750, y: 340}} label="1:M" />
            
            {/* Product Relationships */}
            <RelationshipLine start={{x: 150, y: 420}} end={{x: 350, y: 420}} label="1:M" />
            <RelationshipLine start={{x: 150, y: 500}} end={{x: 350, y: 500}} label="1:M" />
            <RelationshipLine start={{x: 550, y: 420}} end={{x: 750, y: 420}} label="1:M" />
            <RelationshipLine start={{x: 550, y: 500}} end={{x: 750, y: 500}} label="1:M" />
            
            {/* Order Relationships */}
            <RelationshipLine start={{x: 150, y: 580}} end={{x: 350, y: 580}} label="1:M" />
            <RelationshipLine start={{x: 150, y: 660}} end={{x: 350, y: 660}} label="1:M" />
            <RelationshipLine start={{x: 550, y: 580}} end={{x: 750, y: 580}} label="1:M" />
            <RelationshipLine start={{x: 550, y: 660}} end={{x: 750, y: 660}} label="1:1" />
            
            {/* Delivery Relationships */}
            <RelationshipLine start={{x: 150, y: 740}} end={{x: 350, y: 740}} label="1:M" />
            <RelationshipLine start={{x: 550, y: 740}} end={{x: 750, y: 740}} label="1:M" />
          </svg>

          {/* User Management Tables */}
          <ERTable 
            name="registrations" 
            moduleColor="user"
            x={50} y={50} 
            columns={[
              { name: 'user_id', type: 'BIGINT', pk: true },
              { name: 'firstName', type: 'VARCHAR(100)' },
              { name: 'lastName', type: 'VARCHAR(100)' },
              { name: 'mobileNumber', type: 'VARCHAR(15)', unique: true },
              { name: 'emailID', type: 'VARCHAR(255)', unique: true },
              { name: 'is_verified', type: 'BOOLEAN' },
              { name: 'user_mode', type: 'VARCHAR(255)' }
            ]}
          />
          
          <ERTable 
            name="otps" 
            moduleColor="user"
            x={380} y={50} 
            columns={[
              { name: 'mobileNumber', type: 'VARCHAR(15)', fk: true },
              { name: 'code', type: 'VARCHAR(6)' },
              { name: 'status', type: 'BOOLEAN' },
              { name: 'created_at', type: 'DATETIME' }
            ]}
          />
          
          <ERTable 
            name="user_address" 
            moduleColor="user"
            x={380} y={180} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'address_type', type: 'VARCHAR(10)' },
              { name: 'address', type: 'JSON' },
              { name: 'is_default', type: 'BOOLEAN' }
            ]}
          />
          
          <ERTable 
            name="CountryandStates" 
            moduleColor="user"
            x={380} y={310} 
            columns={[
              { name: 'country', type: 'TEXT' },
              { name: 'state', type: 'TEXT' },
              { name: 'district', type: 'TEXT' },
              { name: 'pincode', type: 'TEXT' }
            ]}
          />

          {/* Business Tables */}
          <ERTable 
            name="businesses" 
            moduleColor="business"
            x={620} y={50} 
            columns={[
              { name: 'business_id', type: 'VARCHAR(50)', pk: true },
              { name: 'businessName', type: 'VARCHAR(255)' },
              { name: 'businessType', type: 'VARCHAR(10)' },
              { name: 'businessEmail', type: 'VARCHAR(255)' },
              { name: 'businessNumber', type: 'VARCHAR(15)' },
              { name: 'is_verified', type: 'BOOLEAN' },
              { name: 'status', type: 'BOOLEAN' }
            ]}
          />
          
          <ERTable 
            name="business_mapping" 
            moduleColor="business"
            x={880} y={50} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'status', type: 'BOOLEAN' }
            ]}
          />
          
          <ERTable 
            name="business_owner_details" 
            moduleColor="business"
            x={880} y={180} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'pan', type: 'VARCHAR(20)' },
              { name: 'aadhaar', type: 'VARCHAR(20)' },
              { name: 'per_mobile_number', type: 'VARCHAR(15)' }
            ]}
          />
          
          <ERTable 
            name="business_financials" 
            moduleColor="business"
            x={880} y={310} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'owner_pan', type: 'VARCHAR(20)' },
              { name: 'gstin', type: 'VARCHAR(20)' },
              { name: 'ifsc_code', type: 'VARCHAR(20)' },
              { name: 'account_number', type: 'VARCHAR(50)' }
            ]}
          />
          
          <ERTable 
            name="business_payments" 
            moduleColor="business"
            x={880} y={440} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'transaction_id', type: 'VARCHAR(100)' },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'amount', type: 'DECIMAL(10,2)' },
              { name: 'payment_method', type: 'VARCHAR(50)' },
              { name: 'status', type: 'VARCHAR(50)' }
            ]}
          />

          {/* Product & Inventory Tables */}
          <ERTable 
            name="menuItems" 
            moduleColor="product"
            x={50} y={420} 
            columns={[
              { name: 'item_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'item_name', type: 'VARCHAR(255)' },
              { name: 'sku', type: 'VARCHAR(255)' },
              { name: 'selling_price', type: 'DECIMAL(10,2)' },
              { name: 'gst', type: 'DECIMAL(5,2)' },
              { name: 'is_active', type: 'BOOLEAN' }
            ]}
          />
          
          <ERTable 
            name="Groceries_Products" 
            moduleColor="product"
            x={380} y={420} 
            columns={[
              { name: 'product_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'product_name', type: 'VARCHAR(255)' },
              { name: 'brand_name', type: 'VARCHAR(100)' },
              { name: 'category_id', type: 'BIGINT', fk: true },
              { name: 'is_organic', type: 'BOOLEAN' }
            ]}
          />
          
          <ERTable 
            name="Groceries_Categories" 
            moduleColor="product"
            x={620} y={420} 
            columns={[
              { name: 'category_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'category_name', type: 'VARCHAR(100)' },
              { name: 'parent_category', type: 'VARCHAR(100)' },
              { name: 'gst_rate', type: 'DECIMAL(5,2)' }
            ]}
          />
          
          <ERTable 
            name="Groceries_ProductVariants_1" 
            moduleColor="product"
            x={880} y={420} 
            columns={[
              { name: 'variant_id', type: 'BIGINT', pk: true },
              { name: 'product_id', type: 'BIGINT', fk: true },
              { name: 'sku', type: 'VARCHAR(100)' },
              { name: 'net_weight', type: 'INT' },
              { name: 'selling_price', type: 'DECIMAL(10,2)' },
              { name: 'stock', type: 'INT' }
            ]}
          />
          
          <ERTable 
            name="bill_of_materials" 
            moduleColor="product"
            x={50} y={580} 
            columns={[
              { name: 'bom_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'product_id', type: 'BIGINT', fk: true },
              { name: 'ingredients', type: 'VARCHAR(100)' },
              { name: 'quantity', type: 'DECIMAL(10,2)' },
              { name: 'cost', type: 'DECIMAL(10,2)' }
            ]}
          />
          
          <ERTable 
            name="Inventory" 
            moduleColor="product"
            x={380} y={580} 
            columns={[
              { name: 'inventory_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'reference_table', type: 'VARCHAR(50)' },
              { name: 'reference_id', type: 'BIGINT' },
              { name: 'current_stock', type: 'INT' },
              { name: 'last_updated', type: 'DATETIME' }
            ]}
          />
          
          <ERTable 
            name="Suppliers" 
            moduleColor="product"
            x={620} y={580} 
            columns={[
              { name: 'supplier_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'supplier_name', type: 'VARCHAR(255)' },
              { name: 'contact_person', type: 'VARCHAR(255)' },
              { name: 'phone', type: 'VARCHAR(20)' },
              { name: 'status', type: 'VARCHAR(20)' }
            ]}
          />
          
          <ERTable 
            name="Purchases" 
            moduleColor="product"
            x={880} y={580} 
            columns={[
              { name: 'purchase_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'supplier_id', type: 'BIGINT', fk: true },
              { name: 'total_amount', type: 'DECIMAL(12,2)' },
              { name: 'payment_status', type: 'VARCHAR(20)' }
            ]}
          />

          {/* Order & Payment Tables */}
          <ERTable 
            name="Groceries_orders" 
            moduleColor="order"
            x={50} y={740} 
            columns={[
              { name: 'order_id', type: 'BIGINT', pk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'order_status', type: 'VARCHAR(20)' },
              { name: 'total_amount', type: 'DECIMAL(10,2)' },
              { name: 'final_amount', type: 'DECIMAL(10,2)' },
              { name: 'delivery_address', type: 'TEXT' }
            ]}
          />
          
          <ERTable 
            name="Groceries_order_items" 
            moduleColor="order"
            x={380} y={740} 
            columns={[
              { name: 'order_item_id', type: 'BIGINT', pk: true },
              { name: 'order_id', type: 'BIGINT', fk: true },
              { name: 'product_id', type: 'BIGINT', fk: true },
              { name: 'quantity', type: 'INT' },
              { name: 'unit_price', type: 'DECIMAL(10,2)' },
              { name: 'total_price', type: 'DECIMAL(10,2)' }
            ]}
          />
          
          <ERTable 
            name="Groceries_payments" 
            moduleColor="order"
            x={620} y={740} 
            columns={[
              { name: 'payment_id', type: 'BIGINT', pk: true },
              { name: 'order_id', type: 'BIGINT', fk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'amount', type: 'DECIMAL(10,2)' },
              { name: 'payment_method', type: 'VARCHAR(10)' },
              { name: 'payment_status', type: 'VARCHAR(10)' }
            ]}
          />
          
          <ERTable 
            name="business_counter_orders" 
            moduleColor="order"
            x={880} y={740} 
            columns={[
              { name: 'order_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'token_number', type: 'VARCHAR(50)' },
              { name: 'total_amount', type: 'DECIMAL(10,2)' },
              { name: 'payment_method', type: 'VARCHAR(50)' }
            ]}
          />
          
          <ERTable 
            name="business_counter_items" 
            moduleColor="order"
            x={50} y={900} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'order_id', type: 'BIGINT', fk: true },
              { name: 'menu_item_id', type: 'BIGINT', fk: true },
              { name: 'item_name', type: 'VARCHAR(255)' },
              { name: 'quantity', type: 'INT' },
              { name: 'unit_price', type: 'DECIMAL(10,2)' }
            ]}
          />
          
          <ERTable 
            name="business_tax_invoice" 
            moduleColor="order"
            x={380} y={900} 
            columns={[
              { name: 'invoice_id', type: 'BIGINT', pk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'invoice_number', type: 'VARCHAR(100)' },
              { name: 'total_amount', type: 'DECIMAL(12,2)' },
              { name: 'cgst_amount', type: 'DECIMAL(12,2)' },
              { name: 'sgst_amount', type: 'DECIMAL(12,2)' }
            ]}
          />

          {/* Delivery & Logistics Tables */}
          <ERTable 
            name="Grocery_partner" 
            moduleColor="delivery"
            x={620} y={900} 
            columns={[
              { name: 'id', type: 'INT', pk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'vehicle_number', type: 'VARCHAR(20)' },
              { name: 'vehicle_type', type: 'VARCHAR(20)' },
              { name: 'availability_status', type: 'VARCHAR(10)' }
            ]}
          />
          
          <ERTable 
            name="GroceryDeliverDetails" 
            moduleColor="delivery"
            x={880} y={900} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'order_id', type: 'BIGINT', fk: true },
              { name: 'partner_id', type: 'INT', fk: true },
              { name: 'delivery_status', type: 'VARCHAR(20)' },
              { name: 'assigned_at', type: 'DATETIME' },
              { name: 'delivered_at', type: 'DATETIME' }
            ]}
          />
          
          <ERTable 
            name="Groceries_cart" 
            moduleColor="delivery"
            x={50} y={1060} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'product_id', type: 'BIGINT', fk: true },
              { name: 'business_id', type: 'VARCHAR(50)', fk: true },
              { name: 'quantity', type: 'INT' },
              { name: 'added_at', type: 'DATETIME' }
            ]}
          />

          {/* System & Admin Tables */}
          <ERTable 
            name="business_applications" 
            moduleColor="system"
            x={380} y={1060} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'application_id', type: 'VARCHAR(100)', unique: true },
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'current_step', type: 'INT' },
              { name: 'status', type: 'VARCHAR(50)' },
              { name: 'submitted_at', type: 'DATETIME' }
            ]}
          />
          
          <ERTable 
            name="notifications_log" 
            moduleColor="system"
            x={620} y={1060} 
            columns={[
              { name: 'user_id', type: 'BIGINT', fk: true },
              { name: 'title', type: 'VARCHAR(255)' },
              { name: 'body', type: 'TEXT' },
              { name: 'status', type: 'VARCHAR(20)' },
              { name: 'is_read', type: 'BOOLEAN' },
              { name: 'created_at', type: 'DATETIME' }
            ]}
          />
          
          <ERTable 
            name="mcp_logs" 
            moduleColor="system"
            x={880} y={1060} 
            columns={[
              { name: 'id', type: 'BIGINT', pk: true },
              { name: 'entity_type', type: 'VARCHAR(50)' },
              { name: 'table_name', type: 'VARCHAR(100)' },
              { name: 'entity_id', type: 'VARCHAR(100)' },
              { name: 'action_type', type: 'VARCHAR(10)' },
              { name: 'created_at', type: 'DATETIME' }
            ]}
          />
        </div>
      </div>

      {/* Core Tables Documentation */}
      <section className="db-section">
        <h2 className="section-title">Core Tables Documentation</h2>
        <div className="table-grid">
          {coreTables.map((table) => (
            <div key={table.name} className="table-card">
              <h3 className="table-title">
                <FaTable className="table-icon" />
                {table.name}
                <span className="table-module">{table.module}</span>
              </h3>
              <p className="table-desc">{table.desc}</p>
              <div className="table-columns">
                {table.columns.map((col, idx) => (
                  <div key={idx} className={`column ${col.pk ? 'pk' : col.fk ? 'fk' : ''}`}>
                    <span className="column-name">{col.name}</span>
                    <span className="column-type">{col.type}</span>
                    {col.pk && <span className="column-tag pk-tag">PK</span>}
                    {col.fk && <span className="column-tag fk-tag">FK</span>}
                    {col.ai && <span className="column-tag ai-tag">AI</span>}
                    {col.unique && <span className="column-tag unique-tag">UNIQUE</span>}
                    {col.default && <span className="column-tag default-tag">DEFAULT</span>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Performance Indexes */}
      <section className="db-section">
        <h2 className="section-title">Performance Indexes</h2>
        <div className="indexes-list">
          {indexes.map((index, idx) => (
            <div key={idx} className="index-item">
              <FaKey className="index-icon" />
              <code>{index}</code>
            </div>
          ))}
        </div>
      </section>

      {/* Data Retention Policy */}
      <section className="db-section">
        <h2 className="section-title">Data Retention Policy</h2>
        <pre className="retention-policy">{retentionPolicy}</pre>
      </section>

      {/* High-Level Data Architecture */}
      <section className="db-section">
        <h2 className="section-title">High-Level Data Architecture</h2>
        <div className="arch-grid">
          <div className="arch-item">
            <FaUsers className="arch-icon" />
            <h4>User Management</h4>
            <ul>
              <li>User profiles & authentication</li>
              <li>Contact information</li>
              <li>Address management</li>
              <li>OTP verification</li>
            </ul>
          </div>
          <div className="arch-item">
            <FaServer className="arch-icon" />
            <h4>Business Setup</h4>
            <ul>
              <li>Business registration</li>
              <li>Owner details</li>
              <li>Financial information</li>
              <li>Payment processing</li>
            </ul>
          </div>
          <div className="arch-item">
            <FaShoppingCart className="arch-icon" />
            <h4>Products & Inventory</h4>
            <ul>
              <li>Menu items & groceries</li>
              <li>Categories & variants</li>
              <li>Stock management</li>
              <li>Supplier management</li>
            </ul>
          </div>
          <div className="arch-item">
            <FaMoneyBillWave className="arch-icon" />
            <h4>Orders & Payments</h4>
            <ul>
              <li>Order processing</li>
              <li>Payment tracking</li>
              <li>Invoicing</li>
              <li>Counter sales</li>
            </ul>
          </div>
          <div className="arch-item">
            <FaTruck className="arch-icon" />
            <h4>Logistics & Delivery</h4>
            <ul>
              <li>Delivery partners</li>
              <li>Order tracking</li>
              <li>Cart management</li>
              <li>Delivery assignments</li>
            </ul>
          </div>
          <div className="arch-item">
            <FaDatabase className="arch-icon" />
            <h4>System & Audit</h4>
            <ul>
              <li>Application tracking</li>
              <li>Notification logs</li>
              <li>Change tracking (MCP)</li>
              <li>System monitoring</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
};

export default DatabaseDesign;
