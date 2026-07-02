import React from 'react';
import { HiOutlineUser, HiOutlineHome, HiOutlineShoppingCart, HiOutlineCreditCard, HiOutlineTruck, HiOutlineChartBar, HiOutlineBell, HiOutlineCog, HiOutlineUsers, HiOutlineDocumentText, HiOutlineServer, HiOutlineCurrencyDollar, HiOutlineLockClosed, HiOutlineKey, HiOutlineClipboardList } from 'react-icons/hi';

const ApiServiceSpecifications = () => {
  return (
    <div className="platform-content admin-card">
      <h1 className="platform-title">API & Service Specifications</h1>
      <p className="platform-description">
        Comprehensive API documentation for the Kirazee platform covering all modules including authentication, business management, 
        orders, payments, delivery, and administrative functions.
      </p>

      {/* Authentication & User Management */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineUser className="section-icon" />
          Authentication & User Management
        </h2>
        <p className="platform-description">
          Complete user lifecycle management from registration to profile management with OTP-based authentication.
        </p>
        
        <div className="api-grid">
          <div className="api-card">
            <h3 className="api-card-title">Registration & Verification</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/register/</span>
                <span className="endpoint-desc">User registration with mobile/email</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/verify-otp/</span>
                <span className="endpoint-desc">OTP verification for account activation</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/login/</span>
                <span className="endpoint-desc">User login with OTP</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/verify-login-otp/</span>
                <span className="endpoint-desc">Login OTP verification</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Profile Management</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/consumer/user-profile/</span>
                <span className="endpoint-desc">Get user profile details</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/update-profile/</span>
                <span className="endpoint-desc">Update user profile information</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/address/</span>
                <span className="endpoint-desc">Manage user addresses</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Business Management */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineHome className="section-icon" />
          Business Management
        </h2>
        <p className="platform-description">
          Complete business lifecycle including onboarding, menu management, financial setup, and operations.
        </p>
        
        <div className="api-grid">
          <div className="api-card">
            <h3 className="api-card-title">Business Onboarding</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/create</span>
                <span className="endpoint-desc">Create new business (3-step process)</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/onboarding/progress/:user_id/</span>
                <span className="endpoint-desc">Get onboarding progress</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/onboarding/submit</span>
                <span className="endpoint-desc">Submit completed application</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Menu & Product Management</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/add-menu-items</span>
                <span className="endpoint-desc">Add restaurant menu items</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/add-product-items</span>
                <span className="endpoint-desc">Add grocery products</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/menu-items</span>
                <span className="endpoint-desc">List menu items</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/groceries/product-items</span>
                <span className="endpoint-desc">List grocery products</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Business Operations</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/summary</span>
                <span className="endpoint-desc">Business summary dashboard</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/user-businesses/</span>
                <span className="endpoint-desc">Get user's businesses</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/coupons/create/</span>
                <span className="endpoint-desc">Create discount coupons</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Orders & Cart Management */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineShoppingCart className="section-icon" />
          Orders & Cart Management
        </h2>
        <p className="platform-description">
          Complete order processing from cart management to order tracking and analytics.
        </p>
        
        <div className="api-grid">
          <div className="api-card">
            <h3 className="api-card-title">Cart Operations</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/add-to-cart</span>
                <span className="endpoint-desc">Add items to cart</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/consumer/viewcart</span>
                <span className="endpoint-desc">View cart items</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/update-cart-quantity</span>
                <span className="endpoint-desc">Update cart quantities</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Order Processing</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/orders/create/</span>
                <span className="endpoint-desc">Create new order</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/consumer/orders/:user_id/</span>
                <span className="endpoint-desc">Get user order history</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/consumer/order-details/</span>
                <span className="endpoint-desc">Get order details</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Counter POS</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/counter/orders/create/</span>
                <span className="endpoint-desc">Create counter order</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/counter/orders/:business_id/</span>
                <span className="endpoint-desc">Get counter orders</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/counter/collections/:business_id/</span>
                <span className="endpoint-desc">Get payment collections</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Payment & Financial */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineCreditCard className="section-icon" />
          Payment & Financial Management
        </h2>
        <p className="platform-description">
          Comprehensive payment processing, wallet management, and financial operations.
        </p>
        
        <div className="api-grid">
          <div className="api-card">
            <h3 className="api-card-title">Payment Gateway</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/payment/initiate/</span>
                <span className="endpoint-desc">Initiate payment</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/payment/verify/</span>
                <span className="endpoint-desc">Verify payment</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/payment-gateway/</span>
                <span className="endpoint-desc">Business setup payment</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Wallet & Coupons</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/consumer/wallet/:user_id/</span>
                <span className="endpoint-desc">Get wallet balance</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/wallet/spend/</span>
                <span className="endpoint-desc">Spend wallet points</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/coupons/validate/</span>
                <span className="endpoint-desc">Validate coupon code</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Refunds</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/consumer/refund/initiate/</span>
                <span className="endpoint-desc">Initiate order refund</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/consumer/refund/status/</span>
                <span className="endpoint-desc">Get refund status</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Delivery & Logistics */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineTruck className="section-icon" />
          Delivery & Logistics
        </h2>
        <p className="platform-description">
          Complete delivery partner management and order fulfillment operations.
        </p>
        
        <div className="api-grid">
          <div className="api-card">
            <h3 className="api-card-title">Delivery Partner Management</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/delivery-partner/register/</span>
                <span className="endpoint-desc">Register delivery partner</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/delivery-partner/boys/</span>
                <span className="endpoint-desc">List delivery partners</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/delivery-partner/update-location/</span>
                <span className="endpoint-desc">Update partner location</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Order Assignment</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/delivery-partner/nearby-orders/</span>
                <span className="endpoint-desc">Get nearby orders</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/delivery-partner/assign-order/</span>
                <span className="endpoint-desc">Assign order to partner</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/delivery-partner/update-delivery-status/</span>
                <span className="endpoint-desc">Update delivery status</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Delivery Configuration</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/delivery/configure/</span>
                <span className="endpoint-desc">Configure delivery charges</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/delivery/configuration/</span>
                <span className="endpoint-desc">Get delivery configuration</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/business/delivery/calculate/</span>
                <span className="endpoint-desc">Calculate delivery charges</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Analytics & Reporting */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineChartBar className="section-icon" />
          Analytics & Reporting
        </h2>
        <p className="platform-description">
          Comprehensive analytics, reporting, and business intelligence features.
        </p>
        
        <div className="api-grid">
          <div className="api-card">
            <h3 className="api-card-title">Business Analytics</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/api/v1/businesses/:business_id/dashboard/today/</span>
                <span className="endpoint-desc">Today's snapshot</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/api/v1/businesses/:business_id/dashboard/daily-sales/</span>
                <span className="endpoint-desc">Daily sales analytics</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/business/api/v1/businesses/:business_id/dashboard/recent-orders/</span>
                <span className="endpoint-desc">Recent orders</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Management Reports</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/management/reports/daily/</span>
                <span className="endpoint-desc">Daily reports</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/management/reports/profit-loss/</span>
                <span className="endpoint-desc">Profit & loss reports</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/management/financial/breakdown/</span>
                <span className="endpoint-desc">Financial breakdown</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Admin Analytics</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/dashboard/summary/</span>
                <span className="endpoint-desc">Admin dashboard summary</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/analytics/revenue-trend/</span>
                <span className="endpoint-desc">Revenue trends</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/delivery/active-fleet/</span>
                <span className="endpoint-desc">Active delivery fleet</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Administrative Functions */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineCog className="section-icon" />
          Administrative Functions
        </h2>
        <p className="platform-description">
          Super admin functions for system management, monitoring, and configuration.
        </p>
        
        <div className="api-grid">
          <div className="api-card">
            <h3 className="api-card-title">Business Administration</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/businesses/</span>
                <span className="endpoint-desc">List all businesses</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/businesses/:business_id/status/</span>
                <span className="endpoint-desc">Update business status</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/businesses/:business_id/details/</span>
                <span className="endpoint-desc">Business details</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Order Management</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/orders/</span>
                <span className="endpoint-desc">List all orders</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/orders/:order_id/status/</span>
                <span className="endpoint-desc">Update order status</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/orders/:order_id/assign-delivery/</span>
                <span className="endpoint-desc">Assign delivery partner</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">System Monitoring</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/dashboard/health/</span>
                <span className="endpoint-desc">System health monitoring</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/export/orders/</span>
                <span className="endpoint-desc">Export orders data</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/v1/admin/contact-us/</span>
                <span className="endpoint-desc">Contact us management</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Notifications & Communications */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineBell className="section-icon" />
          Notifications & Communications
        </h2>
        <p className="platform-description">
          Push notifications, SMS, and in-app messaging system.
        </p>
        
        <div className="api-grid">
          <div className="api-card">
            <h3 className="api-card-title">User Notifications</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/notifications/list/:user_id/</span>
                <span className="endpoint-desc">Get user notifications</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/api/notifications/read/:notif_id/</span>
                <span className="endpoint-desc">Mark notification as read</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/api/notifications/clear-all/:user_id/</span>
                <span className="endpoint-desc">Clear all notifications</span>
              </div>
            </div>
          </div>

          <div className="api-card">
            <h3 className="api-card-title">Campaign Management</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/notifications/superadmin/campaigns/</span>
                <span className="endpoint-desc">List notification campaigns</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge post">POST</span>
                <span className="endpoint-path">/kirazee/api/notifications/superadmin/campaigns/create/</span>
                <span className="endpoint-desc">Create notification campaign</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge get">GET</span>
                <span className="endpoint-path">/kirazee/api/notifications/campaigns/:campaign_id/performance/</span>
                <span className="endpoint-desc">Campaign performance analytics</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* API Standards & Guidelines */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineDocumentText className="section-icon" />
          API Standards & Guidelines
        </h2>
        
        <div className="standards-grid">
          <div className="standard-card">
            <h3 className="standard-title">Authentication</h3>
            <ul className="standard-list">
              <li>JWT tokens for API authentication</li>
              <li>OTP-based user verification</li>
              <li>Session management with refresh tokens</li>
              <li>Role-based access control</li>
            </ul>
          </div>

          <div className="standard-card">
            <h3 className="standard-title">Response Format</h3>
            <ul className="standard-list">
              <li>JSON responses for all endpoints</li>
              <li>Standard HTTP status codes</li>
              <li>Consistent error message format</li>
              <li>Pagination for list endpoints</li>
            </ul>
          </div>

          <div className="standard-card">
            <h3 className="standard-title">Rate Limiting</h3>
            <ul className="standard-list">
              <li>100 requests per minute per user</li>
              <li>1000 requests per hour per IP</li>
              <li>Exponential backoff for violations</li>
              <li>Custom limits for business accounts</li>
            </ul>
          </div>

          <div className="standard-card">
            <h3 className="standard-title">Security</h3>
            <ul className="standard-list">
              <li>HTTPS required for all endpoints</li>
              <li>CORS configuration for web clients</li>
              <li>Input validation and sanitization</li>
              <li>SQL injection prevention</li>
            </ul>
          </div>
        </div>
      </section>

      {/* WebSocket Support */}
      <section className="api-section">
        <h2 className="section-title">
          <HiOutlineServer className="section-icon" />
          Real-time Features
        </h2>
        <p className="platform-description">
          WebSocket support for real-time order tracking, delivery updates, and live notifications.
        </p>
        
        <div className="websocket-grid">
          <div className="ws-card">
            <h3 className="ws-card-title">Order Tracking</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge ws">WS</span>
                <span className="endpoint-path">/ws/delivery/tracking/</span>
                <span className="endpoint-desc">Real-time order tracking</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge ws">WS</span>
                <span className="endpoint-path">/ws/order/status/</span>
                <span className="endpoint-desc">Live order status updates</span>
              </div>
            </div>
          </div>

          <div className="ws-card">
            <h3 className="ws-card-title">Dashboard Updates</h3>
            <div className="endpoint-list">
              <div className="endpoint-item">
                <span className="method-badge ws">WS</span>
                <span className="endpoint-path">/ws/dashboard/live/</span>
                <span className="endpoint-desc">Live dashboard metrics</span>
              </div>
              <div className="endpoint-item">
                <span className="method-badge ws">WS</span>
                <span className="endpoint-path">/ws/notifications/live/</span>
                <span className="endpoint-desc">Real-time notifications</span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ApiServiceSpecifications;
