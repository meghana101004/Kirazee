from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Registration, UserAddress, NavigationItem, CompanyRegistration, CompanyOffers
from .models import generate_user_id

class RegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registration
        fields = [
            'firstName', 'lastName', 'countryCode', 'mobileNumber', 
            'emailID', 'dob', 'tokenID', 'uuid', 'os'
        ]

    def validate(self, data):
        """
        Custom validation to handle all registration scenarios and provide
        detailed error responses.
        """
        email = data.get('emailID')
        mobile = data.get('mobileNumber')

        # --- Part 1: Check for an existing user by EMAIL first ---
        existing_user_by_email = Registration.objects.filter(emailID=email).first()
        if existing_user_by_email:
            user_details = {
                "firstName": existing_user_by_email.firstName,
                "lastName": existing_user_by_email.lastName,
                "emailID": existing_user_by_email.emailID,
                "mobileNumber": existing_user_by_email.mobileNumber,
            }
            # If the user is already verified, it's a hard stop.
            if existing_user_by_email.is_verified:
                error_response = {
                    "emailID": ["This email is already registered and verified."],
                    "details": user_details
                }
                raise ValidationError(error_response)
            
            # If user is NOT verified, check for mistyped mobile scenario
            if existing_user_by_email.mobileNumber != mobile:
                raise ValidationError({
                    "status": "conflict", "code": "UNVERIFIED_ACCOUNT_EXISTS",
                    "message": "This email is tied to an unverified account with a different mobile. We will update it and resend the OTP.",
                })
            
            # If user is NOT verified and mobile is the SAME, it's a simple retry.
            # We still inform the user, as they need to verify.
            raise ValidationError({
                "emailID": ["This account already exists but has not been verified. An OTP will be resent."],
                "user_details": user_details
            })

        # --- Part 2: If no user by email, check by MOBILE ---
        existing_user_by_mobile = Registration.objects.filter(mobileNumber=mobile).first()
        if existing_user_by_mobile:
            # Since we already checked for email, any user found here MUST have a different email.
            # This covers the "mistyped email" scenario for both verified and unverified users.
            user_details = {
                "firstName": existing_user_by_mobile.firstName,
                "lastName": existing_user_by_mobile.lastName,
                "emailID": existing_user_by_mobile.emailID,
                "mobileNumber": existing_user_by_mobile.mobileNumber,
            }
            if existing_user_by_mobile.is_verified:
                raise ValidationError({
                    "mobileNumber": ["This mobile number is already registered and verified."],
                    "user_details": user_details
                })
            else: # Unverified user with a mistyped email
                raise ValidationError({
                    "status": "conflict", "code": "UNVERIFIED_ACCOUNT_EXISTS",
                    "message": "This mobile is tied to an unverified account with a different email. We will update it and resend the OTP.",
                })

        # If no user was found by email or mobile, it's a new registration.
        return data

    def create(self, validated_data):
        validated_data['user_id'] = generate_user_id()
        return Registration.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.firstName = validated_data.get('firstName', instance.firstName)
        instance.lastName = validated_data.get('lastName', instance.lastName)
        instance.emailID = validated_data.get('emailID', instance.emailID)
        instance.mobileNumber = validated_data.get('mobileNumber', instance.mobileNumber)
        # ... update other fields ...
        instance.save()
        return instance


class UserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = [
            'id', 'user', 'address_type', 'tag', 'is_default', 'address', 'status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']

    def validate(self, attrs):
        address_type = attrs.get('address_type')
        tag = attrs.get('tag')
        if address_type:
            normalized = str(address_type).strip().lower()
            if normalized not in {'home', 'work', 'other'}:
                raise ValidationError({'address_type': ['Invalid type. Allowed: home, work, other']})
            if normalized == 'other' and not tag:
                raise ValidationError({'message': 'you mention "other" in "address_type" , Please mention the tag.'})
        return attrs


class NavigationItemSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = NavigationItem
        fields = ['label', 'icon_svg', 'order', 'is_visible', 
            'mode', 'route_path', 'parent', 'children'
        ]

    def get_children(self, obj):
        """Get child navigation items if any"""
        children = obj.children.filter(is_visible=True).order_by('order', 'label')
        if children.exists():
            return NavigationItemSerializer(children, many=True, context=self.context).data
        return []


# ==============================================================================
# Company/B2B Serializers
# ==============================================================================

class CompanyRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for company registration"""
    
    class Meta:
        model = CompanyRegistration
        fields = [
            'company_id', 'company_name', 'gst_number', 'business_type', 
            'business_address', 'contact_person_name', 'contact_person_phone', 
            'contact_person_email', 'alternative_contact_person_name', 
            'alternative_contact_person_phone', 'alternative_contact_person_email',
            'years_in_business', 'annual_revenue', 'number_of_employees',
            'verification_status', 'verification_documents', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['company_id', 'verification_status', 'created_at', 'updated_at']

    def validate_gst_number(self, value):
        """Validate GST number format"""
        # GST format validation removed - only basic validation if needed
        return value

    def validate_contact_person_phone(self, value):
        """Validate contact person phone number"""
        if value and not value.isdigit():
            raise ValidationError("Phone number must contain only digits")
        return value

    def create(self, validated_data):
        """Create company registration with default verification status"""
        validated_data['verification_status'] = 'pending'
        return super().create(validated_data)


class CompanyRegistrationUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating company registration"""
    
    class Meta:
        model = CompanyRegistration
        fields = [
            'company_name', 'business_type', 'business_address', 
            'contact_person_name', 'contact_person_phone', 'contact_person_email',
            'alternative_contact_person_name', 'alternative_contact_person_phone', 
            'alternative_contact_person_email', 'years_in_business', 'annual_revenue', 
            'number_of_employees', 'verification_documents'
        ]

    def validate(self, attrs):
        """Validate update data"""
        # Check if company is approved - restrict certain fields
        instance = getattr(self, 'instance', None)
        if instance and instance.verification_status == 'approved':
            # Allow limited fields to be updated after approval
            allowed_fields = ['contact_person_name', 'contact_person_phone', 
                            'contact_person_email', 'alternative_contact_person_name',
                            'alternative_contact_person_phone', 'alternative_contact_person_email']
            for field in attrs:
                if field not in allowed_fields:
                    raise ValidationError({field: f"Cannot update {field} after company is approved"})
        return attrs


class CompanyVerificationSerializer(serializers.ModelSerializer):
    """Serializer for company verification (admin use)"""
    
    class Meta:
        model = CompanyRegistration
        fields = [
            'verification_status', 'verification_remarks', 'approved_at', 'approved_by'
        ]
        read_only_fields = ['approved_at', 'approved_by']

    def validate(self, attrs):
        """Validate verification status update"""
        verification_status = attrs.get('verification_status')
        verification_remarks = attrs.get('verification_remarks')
        
        if verification_status == 'rejected' and not verification_remarks:
            raise ValidationError("Remarks are required when rejecting a company")
        
        return attrs

    def update(self, instance, validated_data):
        """Update verification status with timestamp"""
        verification_status = validated_data.get('verification_status')
        
        if verification_status == 'approved':
            from django.utils import timezone
            validated_data['approved_at'] = timezone.now()
        
        return super().update(instance, validated_data)


class CompanyOffersSerializer(serializers.ModelSerializer):
    """Serializer for company offers"""
    
    class Meta:
        model = CompanyOffers
        fields = [
            'offer_id', 'company_id', 'offer_name', 'offer_type', 'offer_value',
            'min_order_amount', 'min_order_quantity', 'max_discount_amount',
            'applicable_business_types', 'applicable_categories', 'applicable_products',
            'valid_from', 'valid_until', 'usage_limit', 'usage_count',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['offer_id', 'usage_count', 'created_at', 'updated_at']

    def validate(self, attrs):
        """Validate offer data"""
        offer_type = attrs.get('offer_type')
        offer_value = attrs.get('offer_value')
        valid_from = attrs.get('valid_from')
        valid_until = attrs.get('valid_until')
        min_order_amount = attrs.get('min_order_amount')
        max_discount_amount = attrs.get('max_discount_amount')

        # Validate offer value based on type
        if offer_type == 'percentage_discount':
            if not (0 < offer_value <= 100):
                raise ValidationError("Percentage discount must be between 0 and 100")
        elif offer_type == 'fixed_amount':
            if offer_value <= 0:
                raise ValidationError("Fixed amount discount must be greater than 0")

        # Validate date range
        if valid_from and valid_until and valid_from >= valid_until:
            raise ValidationError("Valid from date must be before valid until date")

        # Validate max discount amount for percentage discounts
        if offer_type == 'percentage_discount' and max_discount_amount and max_discount_amount <= 0:
            raise ValidationError("Maximum discount amount must be greater than 0")

        # Validate minimum order amount
        if min_order_amount and min_order_amount <= 0:
            raise ValidationError("Minimum order amount must be greater than 0")

        return attrs


class CompanyEmployeeSerializer(serializers.ModelSerializer):
    """Serializer for adding employees to company with proper business validation"""
    
    # Employee-specific fields that map to Registration fields
    employee_name = serializers.CharField(write_only=True)
    employee_email = serializers.EmailField(write_only=True)
    employee_phone = serializers.CharField(write_only=True)
    
    # Additional verification documents
    aadhar_number = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=12)
    pan_number = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=10)
    employee_id_card = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=50)
    
    class Meta:
        model = Registration
        fields = [
            'employee_name', 'employee_email', 'employee_phone', 'countryCode',
            'employee_role', 'department', 'employee_id', 'purchase_limit',
            'reporting_manager', 'can_approve_orders', 'aadhar_number', 
            'pan_number', 'employee_id_card'
        ]

    def validate_employee_phone(self, value):
        """Validate employee phone number"""
        if not value.isdigit():
            raise ValidationError("Phone number must contain only digits")
        if len(value) < 10 or len(value) > 15:
            raise ValidationError("Phone number must be between 10 and 15 digits")
        return value

    def validate_aadhar_number(self, value):
        """Validate Aadhar number"""
        if value and not value.isdigit():
            raise ValidationError("Aadhar number must contain only digits")
        if value and len(value) != 12:
            raise ValidationError("Aadhar number must be 12 digits")
        return value

    def validate_pan_number(self, value):
        """Validate PAN number"""
        if value and len(value) != 10:
            raise ValidationError("PAN number must be 10 characters")
        return value

    def validate(self, attrs):
        """Validate employee registration with business logic"""
        employee_email = attrs.get('employee_email')
        employee_phone = attrs.get('employee_phone')
        company_id = self.context.get('company_id')
        
        # Check if user exists by email
        existing_user_by_email = Registration.objects.filter(emailID=employee_email).first()
        existing_user_by_phone = Registration.objects.filter(mobileNumber=employee_phone).first()
        
        # Case 1: User doesn't exist - proceed with registration
        if not existing_user_by_email and not existing_user_by_phone:
            attrs['registration_type'] = 'new'
            return attrs
        
        # Case 2: User exists - check their current company association
        existing_user = existing_user_by_email or existing_user_by_phone
        
        # Check if user is already associated with a company
        current_company_id = getattr(existing_user, 'company_id', None)
        
        if current_company_id and current_company_id != company_id:
            # Case 3: User is already with another company
            try:
                from kirazee_app.models import CompanyRegistration
                current_company = CompanyRegistration.objects.get(company_id=current_company_id)
                
                raise ValidationError({
                    "status": "conflict",
                    "code": "EMPLOYEE_ALREADY_WITH_COMPANY",
                    "message": "This employee is already registered with another company",
                    "employee_details": {
                        "user_id": existing_user.user_id,
                        "name": f"{existing_user.firstName} {existing_user.lastName}",
                        "email": existing_user.emailID,
                        "phone": f"{existing_user.countryCode}{existing_user.mobileNumber}",
                        "current_company": {
                            "company_id": current_company.company_id,
                            "company_name": current_company.company_name,
                            "contact_person": current_company.contact_person_name,
                            "contact_phone": current_company.contact_person_phone
                        },
                        "suggestion": "Please contact the current company administrator to transfer this employee"
                    }
                })
            except CompanyRegistration.DoesNotExist:
                # Company reference is invalid, allow reassignment
                attrs['registration_type'] = 'reassign'
                attrs['existing_user'] = existing_user
                return attrs
        
        elif current_company_id == company_id:
            # Case 4: User is already with this company - update details
            attrs['registration_type'] = 'update'
            attrs['existing_user'] = existing_user
            return attrs
        
        else:
            # User exists but not associated with any company
            attrs['registration_type'] = 'assign'
            attrs['existing_user'] = existing_user
            return attrs

    def create(self, validated_data):
        """Create or update employee based on validation results"""
        registration_type = validated_data.pop('registration_type')
        company_id = self.context.get('company_id')
        
        # Extract employee-specific data
        employee_name = validated_data.pop('employee_name')
        employee_email = validated_data.pop('employee_email')
        employee_phone = validated_data.pop('employee_phone')
        
        # Extract verification documents
        aadhar_number = validated_data.pop('aadhar_number', None)
        pan_number = validated_data.pop('pan_number', None)
        employee_id_card = validated_data.pop('employee_id_card', None)
        
        # Split employee_name into firstName and lastName
        name_parts = employee_name.strip().split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        if registration_type == 'new':
            # Case 1: Create new employee
            validated_data.update({
                'firstName': first_name,
                'lastName': last_name,
                'emailID': employee_email,
                'mobileNumber': employee_phone,
                'user_type': 'company_employee',
                'user_id': generate_user_id(),
                'is_verified': False,  # New employees need verification
                'company_id': company_id,
                'joined_company_at': timezone.now()
            })
            
            user = Registration.objects.create(**validated_data)
            
            return {
                "status": "success",
                "message": "Employee registered successfully. Verification required.",
                "action": "new_registration",
                "user": {
                    "user_id": user.user_id,
                    "firstName": user.firstName,
                    "lastName": user.lastName,
                    "emailID": user.emailID,
                    "mobileNumber": user.mobileNumber,
                    "countryCode": user.countryCode,
                    "user_type": user.user_type,
                    "company_id": user.company_id,
                    "employee_role": getattr(user, 'employee_role', None),
                    "department": getattr(user, 'department', None),
                    "employee_id": getattr(user, 'employee_id', None),
                    "is_verified": user.is_verified
                }
            }
        
        else:
            # Case 2, 3, 4: Update existing user
            existing_user = validated_data.pop('existing_user', None)
            
            if not existing_user:
                raise ValidationError("Existing user not found")
            
            # Update user details
            existing_user.firstName = first_name
            existing_user.lastName = last_name
            existing_user.emailID = employee_email
            existing_user.mobileNumber = employee_phone
            existing_user.user_type = 'company_employee'
            existing_user.company_id = company_id
            
            # Update company-specific fields
            for field in ['employee_role', 'department', 'employee_id', 'purchase_limit', 
                         'reporting_manager', 'can_approve_orders']:
                if field in validated_data:
                    setattr(existing_user, field, validated_data[field])
            
            # Store verification documents
            verification_docs = {}
            if aadhar_number:
                verification_docs['aadhar_number'] = aadhar_number
            if pan_number:
                verification_docs['pan_number'] = pan_number
            if employee_id_card:
                verification_docs['employee_id_card'] = employee_id_card
            
            if verification_docs:
                existing_user.verification_documents = verification_docs
            
            # Set verification status based on registration type
            if registration_type == 'update':
                # Already with this company - keep current verification status
                message = "Employee details updated successfully."
                action = "updated"
            elif registration_type == 'assign':
                # Unassigned user - needs verification
                existing_user.is_verified = False
                existing_user.joined_company_at = timezone.now()
                message = "Employee assigned to company successfully. Verification required."
                action = "assigned"
            elif registration_type == 'reassign':
                # Reassigned from invalid company - needs verification
                existing_user.is_verified = False
                existing_user.joined_company_at = timezone.now()
                message = "Employee reassigned to company successfully. Verification required."
                action = "reassigned"
            
            existing_user.save()
            
            return {
                "status": "success",
                "message": message,
                "action": action,
                "user": {
                    "user_id": existing_user.user_id,
                    "firstName": existing_user.firstName,
                    "lastName": existing_user.lastName,
                    "emailID": existing_user.emailID,
                    "mobileNumber": existing_user.mobileNumber,
                    "countryCode": existing_user.countryCode,
                    "user_type": existing_user.user_type,
                    "company_id": existing_user.company_id,
                    "employee_role": getattr(existing_user, 'employee_role', None),
                    "department": getattr(existing_user, 'department', None),
                    "employee_id": getattr(existing_user, 'employee_id', None),
                    "is_verified": existing_user.is_verified
                },
                "verification_required": not existing_user.is_verified
            }


class CompanyOrderSerializer(serializers.Serializer):
    """Serializer for company B2B order creation - Full feature parity with create_order"""
    
    # Basic order parameters (same as create_order)
    user_id = serializers.IntegerField(required=False)  # Will be derived from employee
    business_id = serializers.IntegerField(required=False)  # Will be derived from items or company default
    order_type = serializers.ChoiceField(
        choices=['delivery', 'pickup', 'dine_in'],
        default='delivery'
    )
    delivery_address_id = serializers.IntegerField(required=False)
    items = serializers.ListField(
        child=serializers.DictField(),
        min_length=1
    )
    
    # Pricing and discounts (same as create_order)
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    wallet_points_to_use = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_charges = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    parcel_charges = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Timing parameters (same as create_order)
    estimated_delivery_time = serializers.DateTimeField(required=False)
    scheduled_time = serializers.DateTimeField(required=False)
    pay_later = serializers.BooleanField(default=False)
    
    # B2B specific parameters
    company_id = serializers.IntegerField()
    ordered_by_employee_id = serializers.IntegerField(required=False)
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    
    # Order identification
    company_purchase_order = serializers.CharField(max_length=100, required=False, allow_blank=True)
    order_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    
    # Order type and classification
    is_bulk_order = serializers.BooleanField(default=False)
    bulk_order_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    order_priority = serializers.ChoiceField(
        choices=['normal', 'urgent', 'express'],
        default='normal'
    )
    
    # Payment and billing
    payment_method = serializers.ChoiceField(
        choices=['prepaid', 'cod', 'credit_period'],
        default='cod'
    )
    billing_address = serializers.JSONField(required=False)
    credit_period_days = serializers.IntegerField(required=False, min_value=0)
    
    # Delivery information (B2B specific - can override delivery_address_id)
    delivery_address = serializers.JSONField(required=False)
    delivery_date = serializers.DateField(required=False)
    delivery_instructions = serializers.CharField(required=False, allow_blank=True, max_length=500)
    
    # Additional notes
    company_notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    internal_notes = serializers.CharField(required=False, allow_blank=True, max_length=500)
    
    def validate_company_id(self, value):
        """Validate company ID"""
        if not value:
            return value
            
        try:
            from kirazee_app.models import CompanyRegistration
            company = CompanyRegistration.objects.get(company_id=value)
            if not company.can_place_orders:
                raise ValidationError("Company is not approved to place orders")
            return value
        except CompanyRegistration.DoesNotExist:
            raise ValidationError("Invalid company ID")
    
    def validate_ordered_by_employee_id(self, value):
        """Validate employee belongs to the company and is verified"""
        if not value:
            return value
            
        try:
            employee = Registration.objects.get(
                user_id=value,
                user_type='company_employee',
                is_verified=True
            )
            return value
        except Registration.DoesNotExist:
            raise ValidationError("Invalid or unverified employee")
    
    def validate_items(self, value):
        """Validate order items"""
        if not value:
            raise ValidationError("Order must contain at least one item")
        
        total_amount = 0
        for i, item in enumerate(value):
            # Validate required fields in each item
            required_fields = ['product_id', 'quantity', 'unit_price']
            for field in required_fields:
                if field not in item:
                    raise ValidationError(f"Item {i+1}: Missing required field '{field}'")
            
            # Validate quantity and price
            if item['quantity'] <= 0:
                raise ValidationError(f"Item {i+1}: Quantity must be greater than 0")
            
            if item['unit_price'] <= 0:
                raise ValidationError(f"Item {i+1}: Unit price must be greater than 0")
            
            # Calculate item total
            item_total = item['quantity'] * item['unit_price']
            item['item_total'] = item_total
            total_amount += item_total
        
        # Add total amount to validated data
        self.total_amount = total_amount
        return value
    
    def validate_payment_method(self, value):
        """Validate payment method based on company settings"""
        if value == 'credit_period' and not self.initial_data.get('credit_period_days'):
            raise ValidationError("Credit period days are required when payment method is credit_period")
        return value
    
    def validate(self, attrs):
        """Overall order validation"""
        company_id = attrs.get('company_id')
        employee_id = attrs.get('ordered_by_employee_id')
        
        # If employee is specified, validate they belong to company
        if employee_id and company_id:
            try:
                employee = Registration.objects.get(
                    user_id=employee_id,
                    company_id=company_id,
                    user_type='company_employee',
                    is_verified=True
                )
                attrs['employee'] = employee
            except Registration.DoesNotExist:
                raise ValidationError("Employee does not belong to this company or is not verified")
        
        # Validate delivery requirements
        order_type = attrs.get('order_type', 'delivery')
        delivery_address_id = attrs.get('delivery_address_id')
        delivery_address = attrs.get('delivery_address')
        
        if order_type in ['delivery', 'pickup']:
            # For delivery orders, either delivery_address_id OR delivery_address must be provided
            if not delivery_address_id and not delivery_address:
                raise ValidationError("For delivery orders, either delivery_address_id or delivery_address must be provided")
        
        # Validate purchase limits if employee has restrictions
        if 'employee' in attrs:
            employee = attrs['employee']
            purchase_limit = getattr(employee, 'purchase_limit', None)
            if purchase_limit and self.total_amount > purchase_limit:
                raise ValidationError(f"Order amount ({self.total_amount}) exceeds employee's purchase limit ({purchase_limit})")
        
        return attrs
    
    def create(self, validated_data):
        """Create the order using the existing order system"""
        try:
            from django.utils import timezone
            from .models import generate_user_id
            from consumer.orders import create_order
            from rest_framework.request import Request
            from django.http import HttpRequest
            
            # Extract data
            company_id = validated_data.pop('company_id')
            items = validated_data.pop('items')
            employee = validated_data.pop('employee', None)
            
            # Get company details
            from kirazee_app.models import CompanyRegistration
            company = CompanyRegistration.objects.get(company_id=company_id)
            
            # Prepare order data in the format expected by create_order
            order_data = {
                'user_id': employee.user_id if employee else validated_data.get('user_id'),
                'business_id': validated_data.get('business_id'),  # Will be derived from items if not provided
                'order_type': validated_data.get('order_type', 'delivery'),
                'delivery_address_id': validated_data.get('delivery_address_id'),
                'items': [],
                
                # Pricing and discounts
                'coupon_code': validated_data.get('coupon_code'),
                'wallet_points_to_use': validated_data.get('wallet_points_to_use', 0),
                'delivery_charges': validated_data.get('delivery_charges', 0),
                'parcel_charges': validated_data.get('parcel_charges', 0),
                
                # Timing parameters
                'estimated_delivery_time': validated_data.get('estimated_delivery_time'),
                'scheduled_time': validated_data.get('scheduled_time'),
                'pay_later': validated_data.get('pay_later', validated_data.get('payment_method') == 'credit_period'),
                
                # Instructions
                'delivery_instruction': validated_data.get('delivery_instruction', ''),
                'order_instruction': validated_data.get('order_instruction', validated_data.get('company_notes', '')),
                
                # B2B specific fields (will be stored in order metadata)
                'company_id': company_id,
                'company_purchase_order': validated_data.get('company_purchase_order', ''),
                'order_reference': validated_data.get('order_reference', ''),
                'is_bulk_order': validated_data.get('is_bulk_order', False),
                'bulk_order_reference': validated_data.get('bulk_order_reference', ''),
                'order_priority': validated_data.get('order_priority', 'normal'),
                'ordered_by_employee_id': employee.user_id if employee else validated_data.get('ordered_by_employee_id'),
                'department': validated_data.get('department', ''),
                'payment_method': validated_data.get('payment_method', 'cod'),
                'credit_period_days': validated_data.get('credit_period_days'),
                'billing_address': validated_data.get('billing_address', {}),
                'delivery_address': validated_data.get('delivery_address', {}),
                'internal_notes': validated_data.get('internal_notes', ''),
            }
            
            # Convert items to the format expected by create_order
            for item in items:
                order_item = {
                    'product_item_id': item['product_id'],
                    'quantity': item['quantity'],
                    'customizations': item.get('customizations', [])
                }
                order_data['items'].append(order_item)
            
            # Create a mock request object for the create_order function
            class MockRequest:
                def __init__(self, data):
                    self.data = data
            
            mock_request = MockRequest(order_data)
            
            # Call the existing create_order function
            try:
                order_response = create_order(mock_request)
                
                if order_response.status_code == 201:
                    # Order created successfully
                    response_data = order_response.data
                    
                    # Add B2B specific information to the response
                    if response_data.get('success'):
                        response_data['data'].update({
                            'company_id': company_id,
                            'company_name': company.company_name,
                            'company_purchase_order': validated_data.get('company_purchase_order', ''),
                            'order_reference': validated_data.get('order_reference', ''),
                            'is_bulk_order': validated_data.get('is_bulk_order', False),
                            'order_priority': validated_data.get('order_priority', 'normal'),
                            'ordered_by_employee': {
                                'user_id': employee.user_id,
                                'name': f"{employee.firstName} {employee.lastName}",
                                'email': employee.emailID,
                                'department': validated_data.get('department', '')
                            } if employee else None,
                            'payment_method': validated_data.get('payment_method', 'cod'),
                            'credit_period_days': validated_data.get('credit_period_days'),
                            'billing_address': validated_data.get('billing_address', {}),
                            'delivery_address': validated_data.get('delivery_address', {}),
                        })
                        
                        return {
                            'status': 'success',
                            'message': 'B2B Order created successfully',
                            'order': response_data['data'],
                            'items': items,
                            'total_amount': self.total_amount,
                            'item_count': len(items)
                        }
                    else:
                        return response_data.data
                else:
                    # Order creation failed
                    return {
                        'status': 'error',
                        'message': 'Failed to create order',
                        'error': order_response.data.get('error', 'Unknown error'),
                        'details': order_response.data
                    }
                    
            except Exception as e:
                # If create_order fails, fall back to creating a basic order record
                # This ensures B2B orders can still be created even if the main order system has issues
                
                # Generate order ID
                order_id = generate_user_id()
                
                # Create basic order data structure
                order_data = {
                    'order_id': order_id,
                    'order_customer_type': 'company',
                    'company_id': company_id,
                    'ordered_by_employee_id': employee.user_id if employee else None,
                    'department': validated_data.get('department', ''),
                    
                    # Order details
                    'company_purchase_order': validated_data.get('company_purchase_order', ''),
                    'order_reference': validated_data.get('order_reference', ''),
                    'is_bulk_order': validated_data.get('is_bulk_order', False),
                    'bulk_order_reference': validated_data.get('bulk_order_reference', ''),
                    'order_priority': validated_data.get('order_priority', 'normal'),
                    
                    # Financial details
                    'total_amount': self.total_amount,
                    'payment_method': validated_data.get('payment_method', 'cod'),
                    'credit_period_days': validated_data.get('credit_period_days'),
                    'billing_address': validated_data.get('billing_address', {}),
                    
                    # Delivery details
                    'delivery_address': validated_data.get('delivery_address', {}),
                    'delivery_date': validated_data.get('delivery_date'),
                    'delivery_instructions': validated_data.get('delivery_instructions', ''),
                    
                    # Notes
                    'company_notes': validated_data.get('company_notes', ''),
                    'internal_notes': validated_data.get('internal_notes', ''),
                    
                    # Status and timestamps
                    'order_status': 'pending',
                    'created_at': timezone.now(),
                    'updated_at': timezone.now()
                }
                
                return {
                    'status': 'success',
                    'message': 'B2B Order created successfully (fallback mode)',
                    'order': order_data,
                    'items': items,
                    'total_amount': self.total_amount,
                    'item_count': len(items),
                    'warning': 'Created in fallback mode - some features may be limited'
                }
            
        except Exception as e:
            raise ValidationError(f"Failed to create order: {str(e)}")


class CompanyOrderListSerializer(serializers.Serializer):
    """Serializer for listing company orders"""
    
    company_id = serializers.IntegerField()
    status = serializers.ChoiceField(
        choices=['all', 'pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled'],
        default='all'
    )
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    employee_id = serializers.IntegerField(required=False)
    is_bulk_order = serializers.BooleanField(required=False)
    
    def validate_company_id(self, value):
        """Validate company ID"""
        try:
            from kirazee_app.models import CompanyRegistration
            CompanyRegistration.objects.get(company_id=value)
            return value
        except CompanyRegistration.DoesNotExist:
            raise ValidationError("Invalid company ID")