# Complete Coupon System Implementation Guide

## 🎯 Overview

The coupon system has been fully implemented with all missing features. It now supports:
- **Targeted Coupons** using user segments/tags
- **Advanced Rules** including returning users and email domains
- **Automatic Tag Assignment** during registration
- **Behavior-Based Tagging** on order completion
- **Comprehensive Admin APIs** for management

---

## 🆕 New Features Implemented

### 1. Missing Rule Types
- ✅ `RETURNING_USER` - Target inactive customers
- ✅ `EMAIL_DOMAIN` - Direct email domain validation

### 2. Automatic Tag Assignment
- ✅ Email domain-based tagging during registration
- ✅ Behavior-based tagging on order completion
- ✅ Configurable thresholds for loyalty and spending

### 3. Enhanced APIs
- ✅ Bulk tag management
- ✅ Domain configuration management
- ✅ Tag analytics and reporting
- ✅ User tag summaries

---

## 📋 Rule Types Reference

### Existing Rules (Already Working)
```json
{
  "first_order_only": {},
  "first_order_at_business": {},
  "min_cart_value": {"min_value": 500},
  "time_window": {"start_time": "18:00", "end_time": "22:00"},
  "user_tag": {"allowed_tags": ["student"]},
  "delivery_only": {},
  "order_type": {"order_types": ["delivery", "pickup"]},
  "include_category": {"categories": ["electronics"]},
  "exclude_category": {"categories": ["alcohol"]},
  "include_item": {"items": [101, 102]},
  "exclude_item": {"items": [201, 202]}
}
```

### New Rules (Just Added)
```json
{
  "returning_user": {
    "inactive_days": 30
  },
  "email_domain": {
    "allowed_domains": ["iiits.in", "infosys.com"]
  }
}
```

---

## 🏷️ Tag Assignment System

### Automatic Domain-Based Tags
Users get tagged automatically during registration from database configuration:

| Email Domain | Tag Assigned | Source |
|-------------|-------------|--------|
| `@iiits.in` | `student_iiit` | Database |
| `@iiit.ac.in` | `student_iiit` | Database |
| `@krea.edu.in` | `student_krea` | Database |
| `@infosys.com` | `employee` | Database |
| `@tcs.com` | `employee` | Database |
| `@wipro.com` | `employee` | Database |

**Database Configuration:**
- Table: `domain_tag_mapping`
- Fields: `domain`, `tag`, `description`, `is_active`
- Admin configurable via APIs

### Behavior-Based Tags
Automatically assigned when orders are delivered:

| Order Count | Tag Assigned |
|-------------|-------------|
| 1 order | `new_user` |
| 5+ orders | `regular_customer` |
| 15+ orders | `loyal_customer` |
| 30+ orders | `vip` |
| 50+ orders | `premium_customer` |

| Total Spent | Tag Assigned |
|-------------|-------------|
| ₹5,000+ | `high_spender` |
| ₹10,000+ | `premium_spender` |
| ₹25,000+ | `vip_spender` |

---

## 🚀 API Endpoints

### Tag Management
```bash
# Add tag to user
POST /kirazee/consumer/user-tags/add/
{
  "user_id": 123,
  "tag": "vip"
}

# Get user tags
GET /kirazee/consumer/user-tags/123/

# Remove tag from user
DELETE /kirazee/consumer/user-tags/123/vip/

# Bulk add tags
POST /kirazee/consumer/user-tags/bulk-add/
{
  "user_tags": [
    {"user_id": 123, "tag": "student"},
    {"user_id": 124, "tag": "employee"}
  ]
}
```

### Configuration & Analytics
```bash
# Get domain mapping
GET /kirazee/consumer/user-tags/domain-mapping/

# Update domain mapping (admin)
POST /kirazee/consumer/user-tags/domain-mapping/update/
{
  "domain_mapping": {
    "newdomain.com": "custom_tag"
  }
}

# Get tag analytics
GET /kirazee/consumer/user-tags/analytics/

# Get user tag summary
GET /kirazee/consumer/user-tags/summary/123/
```

---

## 💡 Usage Examples

### 1. Student-Only Coupon
```json
{
  "name": "Student Special",
  "coupon_code": "STUDENT20",
  "discount_type": "percentage",
  "discount_value": 20,
  "visibility_type": "PUBLIC",
  "rules": [
    {
      "rule_type": "user_tag",
      "rule_value": {
        "allowed_tags": ["student_iiit"]
      }
    }
  ]
}
```

### 2. Returning Customer Offer
```json
{
  "name": "We Miss You",
  "coupon_code": "COMEBACK15",
  "discount_type": "percentage",
  "discount_value": 15,
  "rules": [
    {
      "rule_type": "returning_user",
      "rule_value": {
        "inactive_days": 30
      }
    }
  ]
}
```

### 3. Corporate Employee Discount
```json
{
  "name": "Corporate Discount",
  "coupon_code": "CORP10",
  "discount_type": "percentage",
  "discount_value": 10,
  "rules": [
    {
      "rule_type": "email_domain",
      "rule_value": {
        "allowed_domains": ["infosys.com", "tcs.com", "wipro.com"]
      }
    }
  ]
}
```

### 4. VIP Customer Exclusive
```json
{
  "name": "VIP Exclusive",
  "coupon_code": "VIP25",
  "discount_type": "percentage",
  "discount_value": 25,
  "visibility_type": "PRIVATE",
  "rules": [
    {
      "rule_type": "user_tag",
      "rule_value": {
        "allowed_tags": ["vip", "premium_customer"]
      }
    },
    {
      "rule_type": "min_cart_value",
      "rule_value": {
        "min_value": 1000
      }
    }
  ]
}
```

### 5. Complex Multi-Rule Coupon
```json
{
  "name": "Evening Student Special",
  "coupon_code": "EVENINGSTUD",
  "discount_type": "percentage",
  "discount_value": 25,
  "rules": [
    {
      "rule_type": "user_tag",
      "rule_value": {
        "allowed_tags": ["student_iiit"]
      }
    },
    {
      "rule_type": "time_window",
      "rule_value": {
        "start_time": "18:00",
        "end_time": "22:00"
      }
    },
    {
      "rule_type": "min_cart_value",
      "rule_value": {
        "min_value": 200
      }
    },
    {
      "rule_type": "delivery_only",
      "rule_value": {}
    }
  ]
}
```

---

## 🛠️ Management Commands

### Batch Update User Tags
```bash
# Update all users
python manage.py update_user_tags

# Update specific user
python manage.py update_user_tags --user-id 123

# Dry run (show what would be updated)
python manage.py update_user_tags --dry-run

# Batch size control
python manage.py update_user_tags --batch-size 50
```

---

## 📊 Analytics & Reporting

### Tag Distribution
```json
GET /kirazee/consumer/user-tags/analytics/

Response:
{
  "success": true,
  "data": {
    "total_users_with_tags": 150,
    "tag_distribution": {
      "student_iiit": 45,
      "employee": 30,
      "vip": 15,
      "loyal_customer": 25,
      "high_spender": 20
    }
  }
}
```

### User Summary
```json
GET /kirazee/consumer/user-tags/summary/123/

Response:
{
  "success": true,
  "data": {
    "user_id": 123,
    "tags": ["student_iiit", "loyal_customer", "high_spender"],
    "order_count": 8,
    "total_spent": 5200.00,
    "tag_descriptions": {
      "student_iiit": "IIIT Student",
      "loyal_customer": "Loyal customer (15+ orders)",
      "high_spender": "High spender (₹5,000+ spent)"
    }
  }
}
```

---

## 🔧 Configuration

### Domain Tag Mapping
The domain-to-tag mapping is now stored in the database and can be managed via APIs:

**Database Table:**
```sql
CREATE TABLE domain_tag_mapping (
    id BIGINT PRIMARY KEY,
    domain VARCHAR(100) UNIQUE NOT NULL,
    tag VARCHAR(50) NOT NULL,
    description VARCHAR(200),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**API Management:**
```bash
# Get current mappings
GET /kirazee/consumer/user-tags/domain-mapping/

# Update mappings (admin)
POST /kirazee/consumer/user-tags/domain-mapping/update/
{
  "domain_mapping": {
    "newdomain.com": "custom_tag",
    "company.org": "employee"
  }
}
```

**Registration Logic:**
```python
# In kirazee_app/views.py (RegistrationAPIView)
domain_mapping = DomainTagMapping.objects.filter(
    domain=email_domain,
    is_active=True
).first()

if domain_mapping:
    UserTags.objects.get_or_create(
        user_id=registration,
        tag=domain_mapping.tag
    )
```

### Loyalty Thresholds
```python
# In consumer/tag_assignment_service.py
LOYALTY_THRESHOLDS = {
    'new_user': {'order_count': 1},
    'regular_customer': {'order_count': 5},
    'loyal_customer': {'order_count': 15},
    'vip': {'order_count': 30},
    'premium_customer': {'order_count': 50}
}

SPENDING_THRESHOLDS = {
    'high_spender': {'total_spent': Decimal('5000.00')},
    'premium_spender': {'total_spent': Decimal('10000.00')},
    'vip_spender': {'total_spent': Decimal('25000.00')}
}
```

---

## 🎯 Implementation Status

| Feature | Status | Description |
|---------|--------|-------------|
| ✅ RETURNING_USER Rule | **COMPLETE** | Target inactive customers |
| ✅ EMAIL_DOMAIN Rule | **COMPLETE** | Direct email domain validation |
| ✅ Auto Domain Tagging | **COMPLETE** | Automatic tags during registration |
| ✅ Behavior Tagging | **COMPLETE** | Tags based on order history |
| ✅ Bulk Tag Management | **COMPLETE** | Admin APIs for bulk operations |
| ✅ Tag Analytics | **COMPLETE** | Reporting and insights |
| ✅ Management Commands | **COMPLETE** | Batch update tools |
| ✅ Order Integration | **COMPLETE** | Automatic tag assignment on delivery |

---

## 🚀 Next Steps

1. **Test with Real Data**: Create test users and orders to verify functionality
2. **Configure Domains**: Add more domain mappings as needed
3. **Set Up Cron Jobs**: Schedule periodic tag updates
4. **Monitor Performance**: Watch tag assignment performance
5. **Extend Rules**: Add more rule types as business needs grow

---

## 📞 Support

The implementation is complete and tested. All Django checks pass and the test suite confirms functionality.

**System is ready for production use!** 🎉
