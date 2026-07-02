# Company Employee Management API Documentation

## Overview
This document describes the API endpoints for managing company employees in the Kirazee B2B system.

## Base URL
```
{{base_url}}/kirazee/company/{company_id}/
```

---

## 1. Company Detail with Employees

### Endpoint: `GET /kirazee/company/{company_id}/?include=employees`

**Description:** Get company details along with all employees when `include=employees` parameter is provided.

**Parameters:**
- `company_id` (path): ID of the company
- `include` (query): Set to `employees` to include employee list

**Request:**
```http
GET /kirazee/company/1/?include=employees
```

**Response:**
```json
{
    "status": "success",
    "data": {
        "company_id": 1,
        "company_name": "TechCorp Solutions Pvt Ltd",
        "gst_number": "123456789012345",
        "business_type": "IT Services",
        "contact_person_name": "John Doe",
        "contact_person_phone": "9876543210",
        "contact_person_email": "john@techcorp.com",
        "verification_status": "approved",
        "created_at": "2024-01-15T10:30:00Z"
    },
    "employees": {
        "count": 3,
        "employees": [
            {
                "user_id": 12345,
                "firstName": "Alice",
                "lastName": "Johnson",
                "emailID": "alice.johnson@techcorp.com",
                "mobileNumber": "9876543213",
                "countryCode": "+91",
                "employee_role": "purchaser",
                "department": "Procurement",
                "employee_id": "EMP001",
                "purchase_limit": 10000.00,
                "reporting_manager": 12346,
                "can_approve_orders": false,
                "is_verified": true,
                "joined_company_at": "2024-01-20T09:15:00Z",
                "verification_documents": {
                    "aadhar_number": "123456789012",
                    "pan_number": "ABCDE1234F",
                    "employee_id_card": "EMP-2024-001"
                }
            }
        ]
    }
}
```

---

## 2. Employee List with Filtering

### Endpoint: `GET /kirazee/company/{company_id}/employees/`

**Description:** Get a detailed list of all employees with filtering options and statistics.

**Parameters:**
- `company_id` (path): ID of the company
- `department` (query, optional): Filter by department name
- `role` (query, optional): Filter by employee role
- `verified` (query, optional): Filter by verification status (`true`/`false`)

**Requests:**

**Get all employees:**
```http
GET /kirazee/company/1/employees/
```

**Filter by department:**
```http
GET /kirazee/company/1/employees/?department=Procurement
```

**Filter by role:**
```http
GET /kirazee/company/1/employees/?role=purchaser
```

**Filter by verification status:**
```http
GET /kirazee/company/1/employees/?verified=true
```

**Multiple filters:**
```http
GET /kirazee/company/1/employees/?department=Procurement&verified=true
```

**Response:**
```json
{
    "status": "success",
    "message": "Found 3 employees",
    "data": {
        "company_id": 1,
        "company_name": "TechCorp Solutions Pvt Ltd",
        "summary": {
            "total_employees": 3,
            "verified_employees": 2,
            "unverified_employees": 1,
            "departments": {
                "Procurement": {"count": 2, "verified": 1},
                "IT": {"count": 1, "verified": 1}
            }
        },
        "employees": [
            {
                "user_id": 12345,
                "firstName": "Alice",
                "lastName": "Johnson",
                "emailID": "alice.johnson@techcorp.com",
                "mobileNumber": "9876543213",
                "countryCode": "+91",
                "employee_role": "purchaser",
                "department": "Procurement",
                "employee_id": "EMP001",
                "purchase_limit": 10000.00,
                "reporting_manager": 12346,
                "can_approve_orders": false,
                "is_verified": true,
                "joined_company_at": "2024-01-20T09:15:00Z",
                "verification_documents": {
                    "aadhar_number": "123456789012",
                    "pan_number": "ABCDE1234F",
                    "employee_id_card": "EMP-2024-001"
                }
            }
        ],
        "filters_applied": {
            "department": "Procurement",
            "role": null,
            "verified": "true"
        }
    }
}
```

---

## 3. Add New Employee

### Endpoint: `POST /kirazee/company/{company_id}/employees/add/`

**Description:** Add a new employee to the company with comprehensive validation and business logic.

**Parameters:**
- `company_id` (path): ID of the company

**Request Body:**
```json
{
    "employee_name": "Bob Wilson",
    "employee_email": "bob.wilson@techcorp.com",
    "employee_phone": "9876543214",
    "countryCode": "+91",
    "employee_role": "purchaser",
    "department": "Procurement",
    "employee_id": "EMP002",
    "purchase_limit": 15000.00,
    "reporting_manager": 12345,
    "can_approve_orders": false,
    "aadhar_number": "987654321098",
    "pan_number": "FGHIJ5678K",
    "employee_id_card": "EMP-2024-002"
}
```

**Field Descriptions:**
- `employee_name` (required): Full name of the employee
- `employee_email` (required): Email address (must be unique)
- `employee_phone` (required): Phone number (must be unique, 10-15 digits)
- `countryCode` (required): Country code (e.g., "+91")
- `employee_role` (required): Role in company (`admin`, `purchaser`, `manager`, `employee`)
- `department` (required): Department name
- `employee_id` (optional): Employee ID within the company
- `purchase_limit` (optional): Maximum purchase amount per order
- `reporting_manager` (optional): User ID of reporting manager
- `can_approve_orders` (optional): Whether employee can approve orders
- `aadhar_number` (optional): 12-digit Aadhar number
- `pan_number` (optional): 10-character PAN number
- `employee_id_card` (optional): Employee ID card number

**Response Examples:**

**New Registration Success:**
```json
{
    "status": "success",
    "message": "Employee registered successfully. Verification required.",
    "action": "new_registration",
    "user": {
        "user_id": 12347,
        "firstName": "Bob",
        "lastName": "Wilson",
        "emailID": "bob.wilson@techcorp.com",
        "mobileNumber": "9876543214",
        "countryCode": "+91",
        "user_type": "company_employee",
        "company_id": 1,
        "employee_role": "purchaser",
        "department": "Procurement",
        "employee_id": "EMP002",
        "is_verified": false
    }
}
```

**Employee Already with Another Company:**
```json
{
    "status": "conflict",
    "code": "EMPLOYEE_ALREADY_WITH_COMPANY",
    "message": "This employee is already registered with another company",
    "employee_details": {
        "user_id": 12348,
        "name": "Charlie Brown",
        "email": "charlie@othercorp.com",
        "phone": "+919876543215",
        "current_company": {
            "company_id": 2,
            "company_name": "Other Corp Pvt Ltd",
            "contact_person": "Jane Smith",
            "contact_phone": "9876543210"
        },
        "suggestion": "Please contact the current company administrator to transfer this employee"
    }
}
```

**Existing Employee Updated:**
```json
{
    "status": "success",
    "message": "Employee details updated successfully.",
    "action": "updated",
    "user": {
        "user_id": 12345,
        "firstName": "Alice",
        "lastName": "Johnson",
        "emailID": "alice.johnson@techcorp.com",
        "mobileNumber": "9876543213",
        "countryCode": "+91",
        "user_type": "company_employee",
        "company_id": 1,
        "employee_role": "purchaser",
        "department": "Procurement",
        "employee_id": "EMP001",
        "is_verified": true
    },
    "verification_required": false
}
```

---

## Business Logic Rules

### 1. New Employee Registration
- If email/phone doesn't exist → Create new employee with `is_verified = false`
- Employee must complete verification process

### 2. Existing User Assignment
- If user exists but not with any company → Assign to current company, `is_verified = false`
- Requires verification for new company assignment

### 3. Same Company Update
- If user already with this company → Update details, keep current verification status
- No additional verification required

### 4. Cross-Company Conflict
- If user already with another company → Show detailed error with current company info
- User must contact current company administrator for transfer

### 5. Validation Rules
- Phone number: 10-15 digits, numeric only
- Aadhar number: 12 digits, numeric only (if provided)
- PAN number: 10 characters (if provided)
- Email and phone must be unique across all users

---

## Error Responses

### Validation Error
```json
{
    "status": "error",
    "message": "Validation failed",
    "errors": {
        "employee_phone": ["Phone number must be between 10 and 15 digits"],
        "aadhar_number": ["Aadhar number must be 12 digits"]
    }
}
```

### Company Not Found
```json
{
    "status": "error",
    "message": "Company not found"
}
```

### Company Not Approved
```json
{
    "status": "error",
    "message": "Company is not approved to add employees"
}
```

---

## Usage Examples

### 1. Get Company Overview with Employees
```bash
curl -X GET "{{base_url}}/kirazee/company/1/?include=employees"
```

### 2. Get All Procurement Department Employees
```bash
curl -X GET "{{base_url}}/kirazee/company/1/employees/?department=Procurement"
```

### 3. Get Unverified Employees
```bash
curl -X GET "{{base_url}}/kirazee/company/1/employees/?verified=false"
```

### 4. Add New Employee
```bash
curl -X POST "{{base_url}}/kirazee/company/1/employees/add/" \
  -H "Content-Type: application/json" \
  -d '{
    "employee_name": "David Lee",
    "employee_email": "david.lee@techcorp.com",
    "employee_phone": "9876543216",
    "countryCode": "+91",
    "employee_role": "manager",
    "department": "IT",
    "employee_id": "EMP003",
    "purchase_limit": 25000.00,
    "can_approve_orders": true,
    "aadhar_number": "456789012345",
    "pan_number": "LMNOP3456Q"
  }'
```

---

## Database Schema

The employee data is stored in the `registrations` table with additional fields:

- `user_type`: Set to 'company_employee'
- `company_id`: Foreign key to company_registrations
- `employee_role`: Role within the company
- `department`: Department name
- `employee_id`: Employee ID within company
- `purchase_limit`: Maximum purchase amount
- `reporting_manager`: User ID of manager
- `can_approve_orders`: Boolean for approval permissions
- `joined_company_at`: Timestamp when joined company
- `verification_documents`: JSON field for Aadhar, PAN, etc.

---

## Security Notes

- All endpoints should be protected with proper authentication
- Company administrators can only manage their own employees
- Verification documents are stored securely and should be encrypted
- Phone numbers and emails are validated for uniqueness across the system
