"""
Vendor Registration and Profile Management Views
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from delivery.image_utils import build_s3_file_url
from .models import VendorProfiles
from .serializers import VendorRegistrationSerializer, VendorProfileUpdateSerializer


class VendorRegistrationAPIView(APIView):
    """
    API View for vendor registration
    Creates both Registration and VendorProfiles records atomically
    """
    
    def post(self, request, *args, **kwargs):
        """
        Handle vendor registration request
        
        Request Body:
            - firstName, lastName, countryCode, mobileNumber, emailID (required)
            - dob (optional)
            - shop_name, business_type, shop_address, shipping_from (required)
            - gst_number, aadhar_number, business_category, business_description, 
              years_in_business, contact_email, contact_phone, website_url
        
        Returns:
            201: Vendor account created successfully
            400: Validation error
            500: Server error
        """
        serializer = VendorRegistrationSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                result = serializer.save()
                user = result['user']
                vendor = result['vendor']
                
                # Build response data
                response_data = {
                    'user': {
                        'user_id': user.user_id,
                        'firstName': user.firstName,
                        'lastName': user.lastName,
                        'countryCode': user.countryCode,
                        'mobileNumber': user.mobileNumber,
                        'emailID': user.emailID,
                        'dob': user.dob.isoformat() if user.dob else None,
                        'is_verified': user.is_verified,
                        'is_active': user.is_active,
                        'user_mode': user.user_mode,
                        'user_type': user.user_type,
                        'status': user.status,
                        'created_at': user.created_at.isoformat(),
                        'updated_at': user.updated_at.isoformat(),
                    },
                    'vendor': {
                        'vendor_id': vendor.vendor_id,
                        'shop_name': vendor.shop_name,
                        'shop_slug': vendor.shop_slug,
                        'business_type': vendor.business_type,
                        'gst_number': vendor.gst_number,
                        'aadhar_number': vendor.aadhar_number,
                        'shop_address': vendor.shop_address,
                        'shipping_from': vendor.shipping_from,
                        'business_category': vendor.business_category,
                        'business_description': vendor.business_description,
                        'years_in_business': vendor.years_in_business,
                        'contact_email': vendor.contact_email,
                        'contact_phone': vendor.contact_phone,
                        'website_url': vendor.website_url,
                       
                        'is_active': vendor.is_active,
                        'approval_status': vendor.approval_status,
                        'is_vendor_approved': vendor.is_vendor_approved,
                        'created_at': vendor.created_at.isoformat() if vendor.created_at else None,
                        'updated_at': vendor.updated_at.isoformat() if vendor.updated_at else None,
                    }
                }
                
                return Response(response_data, status=status.HTTP_201_CREATED)
            
            except Exception as e:
                return Response(
                    {'error': f'An unexpected error occurred: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


class VendorProfileUpdateAPIView(APIView):
    """
    API View for updating vendor profile
    """
    
    def get(self, request, vendor_id=None, user_id=None, *args, **kwargs):
        """
        Get vendor profile details
        
        Args:
            vendor_id: The vendor ID (optional)
            user_id: The user ID (optional)
            
        Returns:
            200: Vendor profile details
            404: Vendor not found
        """
        try:
            # Fetch vendor by vendor_id or user_id
            if vendor_id:
                vendor = VendorProfiles.objects.select_related('user').get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.select_related('user').get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            response_data = {
                'user': {
                    'user_id': vendor.user.user_id,
                    'firstName': vendor.user.firstName,
                    'lastName': vendor.user.lastName,
                    'countryCode': vendor.user.countryCode,
                    'mobileNumber': vendor.user.mobileNumber,
                    'emailID': vendor.user.emailID,
                    'dob': vendor.user.dob.isoformat() if vendor.user.dob else None,
                    'is_verified': vendor.user.is_verified,
                    'is_active': vendor.user.is_active,
                    'user_mode': vendor.user.user_mode,
                    'user_type': vendor.user.user_type,
                    'status': vendor.user.status,
                    'created_at': vendor.user.created_at.isoformat(),
                    'updated_at': vendor.user.updated_at.isoformat(),
                },
                'vendor': {
                    'vendor_id': vendor.vendor_id,
                    'shop_name': vendor.shop_name,
                    'shop_slug': vendor.shop_slug,
                    'business_type': vendor.business_type,
                    'gst_number': vendor.gst_number,
                    'aadhar_number': vendor.aadhar_number,
                    'shop_address': vendor.shop_address,
                    'shipping_from': vendor.shipping_from,
                    'business_category': vendor.business_category,
                    'business_description': vendor.business_description,
                    'years_in_business': vendor.years_in_business,
                    'contact_email': vendor.contact_email,
                    'contact_phone': vendor.contact_phone,
                    'website_url': vendor.website_url,
                   
                    'logo_url': vendor.logo_url,
                    'is_active': vendor.is_active,
                    'approval_status': vendor.approval_status,
                    'is_vendor_approved': vendor.is_vendor_approved,
                    'is_gst_verified': vendor.is_gst_verified,
                    'commission_percentage': str(vendor.commission_percentage) if vendor.commission_percentage else None,
                    'max_products_limit': vendor.max_products_limit,
                    'rejection_reason': vendor.rejection_reason,
                    'created_at': vendor.created_at.isoformat() if vendor.created_at else None,
                    'updated_at': vendor.updated_at.isoformat() if vendor.updated_at else None,
                }
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
        
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def put(self, request, vendor_id=None, user_id=None, *args, **kwargs):
        """
        Update vendor profile (full update)
        
        Args:
            vendor_id: The vendor ID (optional)
            user_id: The user ID (optional)
            
        Returns:
            200: Vendor profile updated successfully
            400: Validation error
            404: Vendor not found
            500: Server error
        """
        try:
            # Fetch vendor by vendor_id or user_id
            if vendor_id:
                vendor = VendorProfiles.objects.select_related('user').get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.select_related('user').get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = VendorProfileUpdateSerializer(vendor, data=request.data, partial=False)
        
        if serializer.is_valid():
            try:
                updated_vendor = serializer.save()
                
                # Build response data
                response_data = {
                    'user': {
                        'user_id': updated_vendor.user.user_id,
                        'firstName': updated_vendor.user.firstName,
                        'lastName': updated_vendor.user.lastName,
                        'countryCode': updated_vendor.user.countryCode,
                        'mobileNumber': updated_vendor.user.mobileNumber,
                        'emailID': updated_vendor.user.emailID,
                        'dob': updated_vendor.user.dob.isoformat() if updated_vendor.user.dob else None,
                        'is_verified': updated_vendor.user.is_verified,
                        'is_active': updated_vendor.user.is_active,
                        'user_mode': updated_vendor.user.user_mode,
                        'user_type': updated_vendor.user.user_type,
                        'status': updated_vendor.user.status,
                        'created_at': updated_vendor.user.created_at.isoformat(),
                        'updated_at': updated_vendor.user.updated_at.isoformat(),
                    },
                    'vendor': {
                        'vendor_id': updated_vendor.vendor_id,
                        'shop_name': updated_vendor.shop_name,
                        'shop_slug': updated_vendor.shop_slug,
                        'business_type': updated_vendor.business_type,
                        'gst_number': updated_vendor.gst_number,
                        'aadhar_number': updated_vendor.aadhar_number,
                        'shop_address': updated_vendor.shop_address,
                        'shipping_from': updated_vendor.shipping_from,
                        'business_category': updated_vendor.business_category,
                        'business_description': updated_vendor.business_description,
                        'years_in_business': updated_vendor.years_in_business,
                        'contact_email': updated_vendor.contact_email,
                        'contact_phone': updated_vendor.contact_phone,
                        'website_url': updated_vendor.website_url,
                       
                        'logo_url': updated_vendor.logo_url,
                        'is_active': updated_vendor.is_active,
                        'approval_status': updated_vendor.approval_status,
                        'is_vendor_approved': updated_vendor.is_vendor_approved,
                        'created_at': updated_vendor.created_at.isoformat() if updated_vendor.created_at else None,
                        'updated_at': updated_vendor.updated_at.isoformat() if updated_vendor.updated_at else None,
                    }
                }
                
                return Response(response_data, status=status.HTTP_200_OK)
            
            except Exception as e:
                return Response(
                    {'error': f'An unexpected error occurred: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def patch(self, request, vendor_id=None, user_id=None, *args, **kwargs):
        """
        Partially update vendor profile
        
        Args:
            vendor_id: The vendor ID (optional)
            user_id: The user ID (optional)
            
        Returns:
            200: Vendor profile updated successfully
            400: Validation error
            404: Vendor not found
            500: Server error
        """
        try:
            # Fetch vendor by vendor_id or user_id
            if vendor_id:
                vendor = VendorProfiles.objects.select_related('user').get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.select_related('user').get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = VendorProfileUpdateSerializer(vendor, data=request.data, partial=True)
        
        if serializer.is_valid():
            try:
                updated_vendor = serializer.save()
                
                # Build response data
                response_data = {
                    'user': {
                        'user_id': updated_vendor.user.user_id,
                        'firstName': updated_vendor.user.firstName,
                        'lastName': updated_vendor.user.lastName,
                        'countryCode': updated_vendor.user.countryCode,
                        'mobileNumber': updated_vendor.user.mobileNumber,
                        'emailID': updated_vendor.user.emailID,
                        'dob': updated_vendor.user.dob.isoformat() if updated_vendor.user.dob else None,
                        'is_verified': updated_vendor.user.is_verified,
                        'is_active': updated_vendor.user.is_active,
                        'user_mode': updated_vendor.user.user_mode,
                        'user_type': updated_vendor.user.user_type,
                        'status': updated_vendor.user.status,
                        'created_at': updated_vendor.user.created_at.isoformat(),
                        'updated_at': updated_vendor.user.updated_at.isoformat(),
                    },
                    'vendor': {
                        'vendor_id': updated_vendor.vendor_id,
                        'shop_name': updated_vendor.shop_name,
                        'shop_slug': updated_vendor.shop_slug,
                        'business_type': updated_vendor.business_type,
                        'gst_number': updated_vendor.gst_number,
                        'aadhar_number': updated_vendor.aadhar_number,
                        'shop_address': updated_vendor.shop_address,
                        'shipping_from': updated_vendor.shipping_from,
                        'business_category': updated_vendor.business_category,
                        'business_description': updated_vendor.business_description,
                        'years_in_business': updated_vendor.years_in_business,
                        'contact_email': updated_vendor.contact_email,
                        'contact_phone': updated_vendor.contact_phone,
                        'website_url': updated_vendor.website_url,
                       
                        'logo_url': updated_vendor.logo_url,
                        'is_active': updated_vendor.is_active,
                        'approval_status': updated_vendor.approval_status,
                        'is_vendor_approved': updated_vendor.is_vendor_approved,
                        'created_at': updated_vendor.created_at.isoformat() if updated_vendor.created_at else None,
                        'updated_at': updated_vendor.updated_at.isoformat() if updated_vendor.updated_at else None,
                    }
                }
                
                return Response(response_data, status=status.HTTP_200_OK)
            
            except Exception as e:
                return Response(
                    {'error': f'An unexpected error occurred: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

class VendorProductAPIView(APIView):
    """
    API View for managing vendor products
    """
    
    def post(self, request, vendor_id=None, user_id=None, *args, **kwargs):
        """
        Create a new product for a vendor
        
        Args:
            vendor_id: The vendor ID (optional if user_id provided)
            user_id: The user ID (optional if vendor_id provided)
            
        Request Body:
            - business_id, product_name, original_price (required)
            - product_type, description, short_description, brand_name, base_sku,
              hsn_code, category_name, sub_category_name, selling_price, gst_percentage,
              weight, weight_unit, dimensions, images, variants, inventory, etc. (optional)
        
        Returns:
            201: Product created successfully
            400: Validation error
            404: Vendor not found
            500: Server error
        """
        from .serializers import VendorProductSerializer
        from .models import VendorProduct
        
        # Verify vendor exists by vendor_id or user_id
        try:
            if vendor_id:
                vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if vendor is approved
        if not vendor.is_vendor_approved:
            return Response(
                {'error': 'Vendor must be approved before adding products'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = VendorProductSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                # Add vendor_id to validated data
                validated_data = serializer.validated_data
                validated_data['vendor_id'] = vendor.vendor_id
                
                # Create product
                product = serializer.save()
                
                # Build media base url using S3
                media_base_url = build_s3_file_url('') or settings.MEDIA_URL

                # Build response data
                response_data = {
                    'product_id': product.product_id,
                    'vendor_id': product.vendor_id,
                    'user_id': vendor.user_id,
                    'business_id': product.business_id,
                    'product_name': product.product_name,
                    'product_slug': product.product_slug,
                    'product_type': product.product_type,
                    'description': product.description,
                    'short_description': product.short_description,
                    'brand_name': product.brand_name,
                    'base_sku': product.base_sku,
                    'hsn_code': product.hsn_code,
                    'item_placed_at': product.item_placed_at,
                    'category_name': product.category_name,
                    'category_id': getattr(product, 'category_id', None),
                    'sub_category_name': product.sub_category_name,
                    'sub_category_id': getattr(product, 'sub_category_id', None),
                    'original_price': str(product.original_price),
                    'selling_price': str(product.selling_price) if product.selling_price else None,
                    'gst_percentage': str(product.gst_percentage),
                    'weight': str(product.weight) if product.weight else None,
                    'weight_unit': product.weight_unit,
                    'length_cm': str(product.length_cm) if product.length_cm else None,
                    'width_cm': str(product.width_cm) if product.width_cm else None,
                    'height_cm': str(product.height_cm) if product.height_cm else None,
                    'condition_new': product.condition_new,
                    'is_returnable': product.is_returnable,
                    'return_days': product.return_days,
                    'images': product.images,
                    'media_url': media_base_url,
                    'variants': product.variants,
                    'inventory': product.inventory,
                    'attributes': product.attributes,
                    'sizes_available': product.sizes_available,
                    'colors_available': product.colors_available,
                    'has_variants': product.has_variants,
                    'manage_stock': product.manage_stock,
                    'stock_quantity': product.stock_quantity,
                    'stock_status': product.stock_status,
                    'is_active': product.is_active,
                    'is_approved': product.is_approved,
                    'approval_status': product.approval_status,
                    'created_at': product.created_at.isoformat(),
                    'updated_at': product.updated_at.isoformat(),
                }
                
                return Response(response_data, status=status.HTTP_201_CREATED)
            
            except Exception as e:
                return Response(
                    {'error': f'An unexpected error occurred: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def get(self, request, vendor_id=None, user_id=None, product_id=None, *args, **kwargs):
        """
        Get vendor products
        
        Args:
            vendor_id: The vendor ID (optional if user_id provided)
            user_id: The user ID (optional if vendor_id provided)
            product_id: The product ID (optional, if not provided returns all products)
            
        Returns:
            200: Product(s) retrieved successfully
            404: Vendor or product not found
        """
        from .models import VendorProduct
        
        # Verify vendor exists by vendor_id or user_id
        try:
            if vendor_id:
                vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            if product_id:
                # Get single product
                product = VendorProduct.objects.get(product_id=product_id, vendor_id=vendor.vendor_id)
                
                # Build media base url using S3
                media_base_url = build_s3_file_url('') or settings.MEDIA_URL

                response_data = {
                    'product_id': product.product_id,
                    'vendor_id': product.vendor_id,
                    'user_id': vendor.user_id,
                    'business_id': product.business_id,
                    'product_name': product.product_name,
                    'product_slug': product.product_slug,
                    'product_type': product.product_type,
                    'description': product.description,
                    'short_description': product.short_description,
                    'brand_name': product.brand_name,
                    'base_sku': product.base_sku,
                    'hsn_code': product.hsn_code,
                    'item_placed_at': product.item_placed_at,
                    'category_name': product.category_name,
                    'category_id': getattr(product, 'category_id', None),
                    'sub_category_name': product.sub_category_name,
                    'sub_category_id': getattr(product, 'sub_category_id', None),
                    'original_price': str(product.original_price),
                    'selling_price': str(product.selling_price) if product.selling_price else None,
                    'gst_percentage': str(product.gst_percentage),
                    'weight': str(product.weight) if product.weight else None,
                    'weight_unit': product.weight_unit,
                    'length_cm': str(product.length_cm) if product.length_cm else None,
                    'width_cm': str(product.width_cm) if product.width_cm else None,
                    'height_cm': str(product.height_cm) if product.height_cm else None,
                    'condition_new': product.condition_new,
                    'is_returnable': product.is_returnable,
                    'return_days': product.return_days,
                    'images': product.images,
                    'media_url': media_base_url,
                    'variants': product.variants,
                    'inventory': product.inventory,
                    'attributes': product.attributes,
                    'sizes_available': product.sizes_available,
                    'colors_available': product.colors_available,
                    'has_variants': product.has_variants,
                    'manage_stock': product.manage_stock,
                    'stock_quantity': product.stock_quantity,
                    'stock_status': product.stock_status,
                    'is_active': product.is_active,
                    'is_approved': product.is_approved,
                    'approval_status': product.approval_status,
                    'created_at': product.created_at.isoformat(),
                    'updated_at': product.updated_at.isoformat(),
                }
                
                return Response(response_data, status=status.HTTP_200_OK)
            else:
                # Get all products for vendor
                products = VendorProduct.objects.filter(vendor_id=vendor.vendor_id)
                
                products_list = []
                for product in products:
                    products_list.append({
                        'product_id': product.product_id,
                        'vendor_id': product.vendor_id,
                        'user_id': vendor.user_id,
                        'business_id': product.business_id,
                        'product_name': product.product_name,
                        'product_slug': product.product_slug,
                        'product_type': product.product_type,
                        'category_name': product.category_name,
                        'category_id': getattr(product, 'category_id', None),
                        'sub_category_name': product.sub_category_name,
                        'sub_category_id': getattr(product, 'sub_category_id', None),
                        'original_price': str(product.original_price),
                        'selling_price': str(product.selling_price) if product.selling_price else None,
                        'gst_percentage': str(product.gst_percentage),
                        'stock_quantity': product.stock_quantity,
                        'stock_status': product.stock_status,
                        'is_active': product.is_active,
                        'is_approved': product.is_approved,
                        'approval_status': product.approval_status,
                        'created_at': product.created_at.isoformat(),
                        'updated_at': product.updated_at.isoformat(),
                    })
                
                return Response({
                    'vendor_id': vendor.vendor_id,
                    'user_id': vendor.user_id,
                    'total_products': len(products_list),
                    'products': products_list
                }, status=status.HTTP_200_OK)
        
        except VendorProduct.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    
    def put(self, request, vendor_id=None, user_id=None, product_id=None, *args, **kwargs):
        """
        Update a product (full update)
        
        Args:
            vendor_id: The vendor ID (optional if user_id provided)
            user_id: The user ID (optional if vendor_id provided)
            product_id: The product ID
            
        Request Body:
            All product fields (same as POST)
        
        Returns:
            200: Product updated successfully
            400: Validation error
            404: Vendor or product not found
            500: Server error
        """
        from .serializers import VendorProductSerializer
        from .models import VendorProduct
        
        # Verify vendor exists by vendor_id or user_id
        try:
            if vendor_id:
                vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get product
        try:
            product = VendorProduct.objects.get(product_id=product_id, vendor_id=vendor.vendor_id)
        except VendorProduct.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = VendorProductSerializer(product, data=request.data, partial=False)
        
        if serializer.is_valid():
            try:
                # Ensure vendor_id doesn't change
                validated_data = serializer.validated_data
                validated_data['vendor_id'] = vendor.vendor_id
                
                # Update product
                updated_product = serializer.save()
                
                # Build media base url using S3
                media_base_url = build_s3_file_url('') or settings.MEDIA_URL

                # Build response data
                response_data = {
                    'product_id': updated_product.product_id,
                    'vendor_id': updated_product.vendor_id,
                    'business_id': updated_product.business_id,
                    'product_name': updated_product.product_name,
                    'product_slug': updated_product.product_slug,
                    'product_type': updated_product.product_type,
                    'description': updated_product.description,
                    'short_description': updated_product.short_description,
                    'brand_name': updated_product.brand_name,
                    'base_sku': updated_product.base_sku,
                    'hsn_code': updated_product.hsn_code,
                    'item_placed_at': updated_product.item_placed_at,
                    'category_name': updated_product.category_name,
                    'category_id': getattr(updated_product, 'category_id', None),
                    'sub_category_name': updated_product.sub_category_name,
                    'sub_category_id': getattr(updated_product, 'sub_category_id', None),
                    'original_price': str(updated_product.original_price),
                    'selling_price': str(updated_product.selling_price) if updated_product.selling_price else None,
                    'gst_percentage': str(updated_product.gst_percentage),
                    'weight': str(updated_product.weight) if updated_product.weight else None,
                    'weight_unit': updated_product.weight_unit,
                    'length_cm': str(updated_product.length_cm) if updated_product.length_cm else None,
                    'width_cm': str(updated_product.width_cm) if updated_product.width_cm else None,
                    'height_cm': str(updated_product.height_cm) if updated_product.height_cm else None,
                    'condition_new': updated_product.condition_new,
                    'is_returnable': updated_product.is_returnable,
                    'return_days': updated_product.return_days,
                    'images': updated_product.images,
                    'media_url': media_base_url,
                    'variants': updated_product.variants,
                    'inventory': updated_product.inventory,
                    'attributes': updated_product.attributes,
                    'sizes_available': updated_product.sizes_available,
                    'colors_available': updated_product.colors_available,
                    'has_variants': updated_product.has_variants,
                    'manage_stock': updated_product.manage_stock,
                    'stock_quantity': updated_product.stock_quantity,
                    'stock_status': updated_product.stock_status,
                    'is_active': updated_product.is_active,
                    'is_approved': updated_product.is_approved,
                    'approval_status': updated_product.approval_status,
                    'created_at': updated_product.created_at.isoformat(),
                    'updated_at': updated_product.updated_at.isoformat(),
                }
                
                return Response(response_data, status=status.HTTP_200_OK)
            
            except Exception as e:
                return Response(
                    {'error': f'An unexpected error occurred: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def patch(self, request, vendor_id=None, user_id=None, product_id=None, *args, **kwargs):
        """
        Partially update a product
        
        Args:
            vendor_id: The vendor ID (optional if user_id provided)
            user_id: The user ID (optional if vendor_id provided)
            product_id: The product ID
            
        Request Body:
            Any product fields to update (partial)
        
        Returns:
            200: Product updated successfully
            400: Validation error
            404: Vendor or product not found
            500: Server error
        """
        from .serializers import VendorProductSerializer
        from .models import VendorProduct
        
        # Verify vendor exists by vendor_id or user_id
        try:
            if vendor_id:
                vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get product
        try:
            product = VendorProduct.objects.get(product_id=product_id, vendor_id=vendor.vendor_id)
        except VendorProduct.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = VendorProductSerializer(product, data=request.data, partial=True)
        
        if serializer.is_valid():
            try:
                # Ensure vendor_id doesn't change
                validated_data = serializer.validated_data
                if 'vendor_id' in validated_data:
                    validated_data['vendor_id'] = vendor.vendor_id
                
                # Update product
                updated_product = serializer.save()
                
                # Build media base url using S3
                media_base_url = build_s3_file_url('') or settings.MEDIA_URL

                # Build response data
                response_data = {
                    'product_id': updated_product.product_id,
                    'vendor_id': updated_product.vendor_id,
                    'business_id': updated_product.business_id,
                    'product_name': updated_product.product_name,
                    'product_slug': updated_product.product_slug,
                    'product_type': updated_product.product_type,
                    'description': updated_product.description,
                    'short_description': updated_product.short_description,
                    'brand_name': updated_product.brand_name,
                    'base_sku': updated_product.base_sku,
                    'hsn_code': updated_product.hsn_code,
                    'item_placed_at': updated_product.item_placed_at,
                    'category_name': updated_product.category_name,
                    'category_id': getattr(updated_product, 'category_id', None),
                    'sub_category_name': updated_product.sub_category_name,
                    'sub_category_id': getattr(updated_product, 'sub_category_id', None),
                    'original_price': str(updated_product.original_price),
                    'selling_price': str(updated_product.selling_price) if updated_product.selling_price else None,
                    'gst_percentage': str(updated_product.gst_percentage),
                    'weight': str(updated_product.weight) if updated_product.weight else None,
                    'weight_unit': updated_product.weight_unit,
                    'length_cm': str(updated_product.length_cm) if updated_product.length_cm else None,
                    'width_cm': str(updated_product.width_cm) if updated_product.width_cm else None,
                    'height_cm': str(updated_product.height_cm) if updated_product.height_cm else None,
                    'condition_new': updated_product.condition_new,
                    'is_returnable': updated_product.is_returnable,
                    'return_days': updated_product.return_days,
                    'images': updated_product.images,
                    'media_url': media_base_url,
                    'variants': updated_product.variants,
                    'inventory': updated_product.inventory,
                    'attributes': updated_product.attributes,
                    'sizes_available': updated_product.sizes_available,
                    'colors_available': updated_product.colors_available,
                    'has_variants': updated_product.has_variants,
                    'manage_stock': updated_product.manage_stock,
                    'stock_quantity': updated_product.stock_quantity,
                    'stock_status': updated_product.stock_status,
                    'is_active': updated_product.is_active,
                    'is_approved': updated_product.is_approved,
                    'approval_status': updated_product.approval_status,
                    'created_at': updated_product.created_at.isoformat(),
                    'updated_at': updated_product.updated_at.isoformat(),
                }
                
                return Response(response_data, status=status.HTTP_200_OK)
            
            except Exception as e:
                return Response(
                    {'error': f'An unexpected error occurred: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(
            {'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def delete(self, request, vendor_id=None, user_id=None, product_id=None, *args, **kwargs):
        """
        Soft delete a product (sets is_active to False)
        
        Args:
            vendor_id: The vendor ID (optional if user_id provided)
            user_id: The user ID (optional if vendor_id provided)
            product_id: The product ID
            
        Returns:
            200: Product deleted successfully
            404: Vendor or product not found
            500: Server error
        """
        from .models import VendorProduct
        
        # Verify vendor exists by vendor_id or user_id
        try:
            if vendor_id:
                vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get product
        try:
            product = VendorProduct.objects.get(product_id=product_id, vendor_id=vendor.vendor_id)
        except VendorProduct.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            # Soft delete - set is_active to False
            product.is_active = False
            product.save()
            
            return Response({
                'message': 'Product deleted successfully',
                'product_id': product_id,
                'vendor_id': vendor.vendor_id,
                'user_id': vendor.user_id,
                'is_active': product.is_active
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class VendorProductApprovalAPIView(APIView):
    """API View for approving/rejecting vendor products and syncing to business tables"""

    def patch(self, request, business_id, businessType, vendor_id, product_id, *args, **kwargs):
        """
        Approve or reject a vendor product
        
        Args:
            vendor_id: The vendor ID
            product_id: The product ID
            
        Request Body:
            - approval_status: 'approved' or 'rejected' (required)
            - rejection_reason: Reason for rejection (optional, for rejected status)
        
        Returns:
            200: Product approval status updated
            400: Validation error
            404: Vendor or product not found
            500: Server error
        """
        from .models import VendorProduct
        from django.db import transaction, connection
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Verify vendor exists
        try:
            vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get product
        try:
            product = VendorProduct.objects.get(product_id=product_id, vendor_id=vendor_id)
        except VendorProduct.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get approval status from request
        approval_status_value = request.data.get('approval_status')
        
        if not approval_status_value:
            return Response(
                {'error': 'approval_status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if approval_status_value not in ['approved', 'rejected']:
            return Response(
                {'error': 'approval_status must be either "approved" or "rejected"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            logger.info(
                f"Approving vendor product {product_id} for business {business_id} / type {businessType}: "
                f"current is_approved={product.is_approved}, approval_status={product.approval_status}"
            )

            bt = (businessType or '').strip().upper()

            with transaction.atomic():
                # 1) Update approval flags on vendor_products
                product.approval_status = approval_status_value
                product.is_approved = (approval_status_value == 'approved')
                product.save(update_fields=['approval_status', 'is_approved'])

                sync_message = "No sync performed"
                new_live_product_id = None

                # 2) Route based on businessType
                if approval_status_value == 'approved':
                    if bt == 'R01':
                        # Grocery: create Groceries_Products + Groceries_ProductVariants_1
                        from consumer.gro_models import GroceriesProducts, GroceriesProductVariants, GroceriesCategories
                        from kirazee_app.models import Business as Biz
                        import json as _json

                        biz = Biz.objects.filter(business_id=business_id).first()
                        if not biz:
                            raise ValueError(f"Business {business_id} not found for groceries sync")

                        # Resolve or create category
                        category_obj = None
                        if product.category_name:
                            category_obj = GroceriesCategories.objects.filter(
                                category_name__iexact=product.category_name
                            ).first()
                        if not category_obj:
                            category_obj, _ = GroceriesCategories.objects.get_or_create(
                                category_name=product.category_name or 'Uncategorized'
                            )

                        # Parse images as JSON dict
                        raw_images = product.images
                        main_image = None
                        sub_images_dict = None
                        if raw_images:
                            if isinstance(raw_images, dict):
                                img_map = raw_images
                            else:
                                try:
                                    img_map = _json.loads(raw_images) if isinstance(raw_images, str) else {}
                                except Exception:
                                    img_map = {}
                            if isinstance(img_map, dict):
                                main_image = img_map.get('image1') or img_map.get('image_1')
                                # everything except the first becomes sub_images
                                sub_images_dict = {}
                                for k, v in img_map.items():
                                    if k in ('image1', 'image_1'):
                                        continue
                                    # keep original keys so consumer side logic still works
                                    sub_images_dict[k] = v
                                if not sub_images_dict:
                                    sub_images_dict = None

                        gp = GroceriesProducts.objects.create(
                            business=biz,
                            product_name=product.product_name,
                            brand_name=product.brand_name or '',
                            category=category_obj,
                            sub_category_id=product.sub_category_id,
                            sub_category=product.sub_category_name or '',
                            description=product.description or '',
                            item_placed_at=product.item_placed_at or '',
                            main_image=main_image,
                            sub_images=sub_images_dict,
                            is_featured=False,
                            is_customizable=False,
                            is_organic=False,
                            base_price=product.original_price,
                            is_visible=product.is_active,
                        )

                        # Expand variants using sizes_available, colors_available, stock_quantity
                        sizes = []
                        colors_map = {}
                        stock_map = {}

                        try:
                            if product.sizes_available:
                                sizes = product.sizes_available if isinstance(product.sizes_available, list) else _json.loads(product.sizes_available)
                        except Exception:
                            sizes = []
                        try:
                            if product.colors_available:
                                colors_map = product.colors_available if isinstance(product.colors_available, dict) else _json.loads(product.colors_available)
                        except Exception:
                            colors_map = {}
                        try:
                            if product.stock_quantity:
                                stock_map = product.stock_quantity if isinstance(product.stock_quantity, dict) else _json.loads(product.stock_quantity)
                        except Exception:
                            stock_map = {}

                        # Map vendor weight_unit to groceries net_weight_unit
                        weight_unit_map = {
                            'kg': 'kg',
                            'g': 'g',
                            'ltr': 'l',
                            'ml': 'ml',
                            'unit': 'pcs'
                        }

                        def _create_variant(size_val, color_val, stock_val):
                            size_json = None
                            if size_val is not None:
                                size_json = {"value": str(size_val)}
                            GroceriesProductVariants.objects.create(
                                product=gp,
                                net_weight=int(product.weight) if product.weight is not None else None,
                                net_weight_unit=weight_unit_map.get(product.weight_unit, 'pcs'),
                                size=size_json,
                                original_cost=product.original_price,
                                selling_price=product.selling_price or product.original_price,
                                gst=product.gst_percentage,
                                stock=int(stock_val) if stock_val is not None else 0,
                                color=str(color_val) if color_val is not None else None,
                                is_active=True,
                            )

                        if sizes:
                            for s in sizes:
                                s_key = str(s)
                                raw_stock = stock_map.get(s_key, 0)
                                try:
                                    raw_stock = int(raw_stock)
                                except Exception:
                                    raw_stock = 0
                                color_list = colors_map.get(s_key) or [None]
                                color_count = len(color_list)
                                if color_count <= 0:
                                    _create_variant(s_key, None, raw_stock)
                                else:
                                    base = raw_stock // color_count
                                    rem = raw_stock % color_count
                                    for idx, c in enumerate(color_list):
                                        stock_for_variant = base + (1 if idx < rem else 0)
                                        _create_variant(s_key, c, stock_for_variant)
                        else:
                            # Fallback: single variant using total stock (if numeric)
                            simple_stock = None
                            if product.stock_quantity and isinstance(product.stock_quantity, (int, float, str)):
                                try:
                                    simple_stock = int(product.stock_quantity)
                                except Exception:
                                    simple_stock = None
                            _create_variant(None, None, simple_stock)

                        new_live_product_id = gp.product_id
                        sync_message = (
                            f"Synced to Groceries_Products (product_id={gp.product_id}) "
                            f"and Groceries_ProductVariants_1 (multiple variants if sizes/colors were provided)"
                        )

                    elif bt == 'R08':
                        # Fashion: create fashion_products + fashion_product_variants (multiple variants)
                        from business.models import FashionProduct, FashionProductVariant, UniversalCategory
                        from kirazee_app.models import Business as Biz
                        import json as _json

                        biz = Biz.objects.filter(business_id=business_id).first()
                        if not biz:
                            raise ValueError(f"Business {business_id} not found for fashion sync")

                        # Resolve category by name; create generic if missing
                        category_obj = None
                        if product.category_name:
                            category_obj = UniversalCategory.objects.filter(
                                category_name__iexact=product.category_name
                            ).first()
                        if not category_obj:
                            category_obj, _ = UniversalCategory.objects.get_or_create(
                                category_name=product.category_name or 'Uncategorized'
                            )

                        # Parse images as JSON dict
                        raw_images = product.images
                        main_image = None
                        sub_images_dict = None
                        if raw_images:
                            if isinstance(raw_images, dict):
                                img_map = raw_images
                            else:
                                try:
                                    img_map = _json.loads(raw_images) if isinstance(raw_images, str) else {}
                                except Exception:
                                    img_map = {}
                            if isinstance(img_map, dict):
                                main_image = img_map.get('image1') or img_map.get('image_1')
                                # everything except the first becomes sub_images
                                sub_images_dict = {}
                                for k, v in img_map.items():
                                    if k in ('image1', 'image_1'):
                                        continue
                                    # keep original keys so consumer side logic still works
                                    sub_images_dict[k] = v
                                if not sub_images_dict:
                                    sub_images_dict = None

                        fp = FashionProduct.objects.create(
                            business_id=biz,
                            category=category_obj,
                            subcategory=product.sub_category_name or (str(product.sub_category_id) if product.sub_category_id else None),
                            sub_images=sub_images_dict,
                            name=product.product_name,
                            description=product.description or '',
                            brand=product.brand_name or None,
                            base_price=product.original_price,
                            gst_rate_default=product.gst_percentage,
                            hsn_code=product.hsn_code or None,
                            main_image=main_image,
                            is_featured=False,
                            rating=None,
                            item_placed_at=product.item_placed_at or None,
                            is_customizable=False,
                            is_visible=True,
                            is_active=True,
                        )

                        # Expand variants using sizes_available, colors_available, stock_quantity
                        sizes = []
                        colors_map = {}
                        stock_map = {}

                        try:
                            if product.sizes_available:
                                sizes = product.sizes_available if isinstance(product.sizes_available, list) else _json.loads(product.sizes_available)
                        except Exception:
                            sizes = []
                        try:
                            if product.colors_available:
                                colors_map = product.colors_available if isinstance(product.colors_available, dict) else _json.loads(product.colors_available)
                        except Exception:
                            colors_map = {}
                        try:
                            if product.stock_quantity:
                                stock_map = product.stock_quantity if isinstance(product.stock_quantity, dict) else _json.loads(product.stock_quantity)
                        except Exception:
                            stock_map = {}

                        created_variant = None

                        def _create_fashion_variant(size_val, color_val, stock_val):
                            nonlocal created_variant
                            v = FashionProductVariant.objects.create(
                                business_id=biz,
                                product=fp,
                                sku=product.base_sku or '',
                                selling_price=product.selling_price or product.original_price,
                                mrp=product.original_price,
                                stock_qty=int(stock_val) if stock_val is not None else 0,
                                stock=int(stock_val) if stock_val is not None else 0,
                                original_cost=product.original_price,
                                size=str(size_val) if size_val is not None else None,
                                color=str(color_val) if color_val is not None else None,
                                is_active=True,
                            )
                            if created_variant is None:
                                created_variant = v

                        if sizes:
                            for s in sizes:
                                s_key = str(s)
                                raw_stock = stock_map.get(s_key, 0)
                                try:
                                    raw_stock = int(raw_stock)
                                except Exception:
                                    raw_stock = 0
                                color_list = colors_map.get(s_key) or [None]
                                color_count = len(color_list)
                                if color_count <= 0:
                                    _create_fashion_variant(s_key, None, raw_stock)
                                else:
                                    base = raw_stock // color_count
                                    rem = raw_stock % color_count
                                    for idx, c in enumerate(color_list):
                                        stock_for_variant = base + (1 if idx < rem else 0)
                                        _create_fashion_variant(s_key, c, stock_for_variant)
                        else:
                            # Fallback: single variant using total stock (if numeric)
                            simple_stock = None
                            if product.stock_quantity and isinstance(product.stock_quantity, (int, float, str)):
                                try:
                                    simple_stock = int(product.stock_quantity)
                                except Exception:
                                    simple_stock = None
                            _create_fashion_variant(None, None, simple_stock)

                        # Point product.variant_id to the first created variant as default
                        if created_variant is not None:
                            fp.variant_id = created_variant.variant_id
                            fp.save(update_fields=['variant_id'])

                        new_live_product_id = fp.product_id
                        sync_message = (
                            f"Synced to fashion_products (product_id={fp.product_id}) "
                            f"and fashion_product_variants (multiple variants if sizes/colors were provided)"
                        )

                    else:
                        sync_message = f"No sync implemented for businessType={bt}"

                # 3) For groceries and fashion, align vendor_products.product_id with live product_id
                if approval_status_value == 'approved' and bt in ('R01', 'R08') and new_live_product_id:
                    old_id = product.product_id
                    if old_id != new_live_product_id:
                        logger.info(
                            f"Updating vendor_products.product_id from {old_id} to {new_live_product_id} "
                            f"for vendor_id={vendor_id}"
                        )
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "UPDATE vendor_products SET product_id = %s WHERE product_id = %s AND vendor_id = %s",
                                [new_live_product_id, old_id, vendor_id],
                            )
                        product.product_id = new_live_product_id

            message = (
                f"Product {product.product_id} has been {approval_status_value}. "
                f"Sync: {sync_message}"
            )

            return Response({
                'message': message,
                'product_id': product.product_id,
                'vendor_id': vendor_id,
                'business_id': business_id,
                'businessType': bt,
                'approval_status': product.approval_status,
                'is_approved': product.is_approved,
                'sync_status': sync_message,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error approving product {product_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class VendorProductSyncStatusAPIView(APIView):
    """
    API View to check if a vendor product is synced to Groceries_Products
    """
    
    def get(self, request, vendor_id, product_id, *args, **kwargs):
        """
        Check sync status of a vendor product
        
        Args:
            vendor_id: The vendor ID
            product_id: The product ID
            
        Returns:
            200: Sync status information
            404: Vendor or product not found
        """
        from .models import VendorProduct
        from consumer.gro_models import GroceriesProducts, GroceriesProductVariants
        
        # Verify vendor exists
        try:
            vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get product
        try:
            product = VendorProduct.objects.get(product_id=product_id, vendor_id=vendor_id)
        except VendorProduct.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if exists in Groceries_Products
        grocery_product = GroceriesProducts.objects.filter(product_id=product_id).first()
        
        # Check variants
        variants = []
        if grocery_product:
            variants_qs = GroceriesProductVariants.objects.filter(product=grocery_product)
            variants = [{
                'variant_id': v.variant_id,
                'sku': v.sku,
                'selling_price': str(v.selling_price),
                'stock': v.stock,
                'is_active': v.is_active
            } for v in variants_qs]
        
        return Response({
            'vendor_product': {
                'product_id': product.product_id,
                'product_name': product.product_name,
                'is_approved': product.is_approved,
                'approval_status': product.approval_status,
                'is_active': product.is_active
            },
            'synced_to_groceries': grocery_product is not None,
            'grocery_product': {
                'product_id': grocery_product.product_id if grocery_product else None,
                'product_name': grocery_product.product_name if grocery_product else None,
                'is_visible': grocery_product.is_visible if grocery_product else None,
                'variants_count': len(variants)
            } if grocery_product else None,
            'variants': variants if grocery_product else []
        }, status=status.HTTP_200_OK)
    
    def post(self, request, vendor_id, product_id, *args, **kwargs):
        """
        Manually trigger sync for a vendor product
        
        Args:
            vendor_id: The vendor ID
            product_id: The product ID
            
        Returns:
            200: Sync triggered successfully
            400: Product not approved or sync failed
            404: Vendor or product not found
        """
        from .models import VendorProduct
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Verify vendor exists
        try:
            vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get product
        try:
            product = VendorProduct.objects.get(product_id=product_id, vendor_id=vendor_id)
        except VendorProduct.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if approved
        if not product.is_approved or product.approval_status != 'approved':
            return Response(
                {'error': 'Product must be approved before syncing', 'is_approved': product.is_approved, 'approval_status': product.approval_status},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Trigger manual sync
        logger.info(f"Manual sync triggered for product {product_id}")
        success, message = product.sync_to_groceries()
        
        if success:
            return Response({
                'success': True,
                'message': message,
                'product_id': product_id,
                'vendor_id': vendor_id
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': message,
                'product_id': product_id,
                'vendor_id': vendor_id
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Trigger manual sync
        success, message = product.sync_to_groceries()
        
        if success:
            return Response({
                'success': True,
                'message': message,
                'product_id': product_id
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': message,
                'product_id': product_id
            }, status=status.HTTP_400_BAD_REQUEST)

class VendorProductBulkUploadAPIView(APIView):
    """
    API View for bulk uploading vendor products
    """
    
    def post(self, request, vendor_id=None, user_id=None, *args, **kwargs):
        """
        Bulk upload vendor products
        
        Args:
            vendor_id: The vendor ID (optional if user_id provided)
            user_id: The user ID (optional if vendor_id provided)
            
        Request Body:
            {
                "products": [
                    {
                        "business_id": "R01",
                        "product_name": "Product 1",
                        "original_price": 100.00,
                        "category_name": "Category",
                        ...
                    },
                    {
                        "business_id": "R01",
                        "product_name": "Product 2",
                        "original_price": 200.00,
                        ...
                    }
                ]
            }
        
        Returns:
            201: Products created successfully
            400: Validation error
            404: Vendor not found
            500: Server error
        """
        from .models import VendorProduct
        from .serializers import VendorProductSerializer
        from django.db import transaction
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Verify vendor exists by vendor_id or user_id
        try:
            if vendor_id:
                vendor = VendorProfiles.objects.get(vendor_id=vendor_id)
            elif user_id:
                vendor = VendorProfiles.objects.get(user_id=user_id)
            else:
                return Response(
                    {'error': 'Either vendor_id or user_id is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if vendor is approved
        if not vendor.is_vendor_approved:
            return Response(
                {'error': 'Vendor must be approved before adding products'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get products array from request
        products_data = request.data.get('products', [])
        
        if not products_data:
            return Response(
                {'error': 'products array is required and cannot be empty'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not isinstance(products_data, list):
            return Response(
                {'error': 'products must be an array'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Limit bulk upload size
        max_products = 100
        if len(products_data) > max_products:
            return Response(
                {'error': f'Maximum {max_products} products allowed per bulk upload'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # First pass: Validate all products
        validated_products = []
        failed_products = []
        
        for index, product_data in enumerate(products_data):
            serializer = VendorProductSerializer(data=product_data)
            
            if serializer.is_valid():
                validated_products.append({
                    'index': index,
                    'serializer': serializer,
                    'product_name': product_data.get('product_name', 'Unknown')
                })
            else:
                failed_products.append({
                    'index': index,
                    'product_name': product_data.get('product_name', 'Unknown'),
                    'errors': serializer.errors,
                    'status': 'validation_failed'
                })
                logger.warning(f"Bulk upload: Validation failed for product at index {index}: {serializer.errors}")
        
        # If any validation failed, return error without creating anything
        if failed_products:
            return Response({
                'success': False,
                'message': 'Validation failed for some products. No products were created.',
                'created_count': 0,
                'failed_count': len(failed_products),
                'failed_products': failed_products
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Second pass: Create all products in a transaction
        created_products = []
        
        try:
            with transaction.atomic():
                for item in validated_products:
                    try:
                        serializer = item['serializer']
                        index = item['index']
                        
                        # Add vendor_id to validated data
                        validated_data = serializer.validated_data
                        validated_data['vendor_id'] = vendor.vendor_id
                        
                        # Create product
                        product = serializer.save()
                        
                        created_products.append({
                            'index': index,
                            'product_id': product.product_id,
                            'product_name': product.product_name,
                            'product_slug': product.product_slug,
                            'status': 'success'
                        })
                        
                        logger.info(f"Bulk upload: Created product {product.product_id} - {product.product_name}")
                    
                    except Exception as e:
                        logger.error(f"Bulk upload: Error creating product at index {index}: {str(e)}")
                        # Raise to rollback transaction
                        raise
        
        except Exception as e:
            logger.error(f"Bulk upload transaction failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response({
                'success': False,
                'message': f'Bulk upload failed during creation: {str(e)}',
                'created_count': 0,
                'failed_count': len(validated_products),
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Success response
        return Response({
            'success': True,
            'message': f'Successfully created {len(created_products)} products',
            'vendor_id': vendor.vendor_id,
            'user_id': vendor.user_id,
            'created_count': len(created_products),
            'failed_count': 0,
            'created_products': created_products
        }, status=status.HTTP_201_CREATED)

class VendorApprovalAPIView(APIView):
    """
    API View for approving/rejecting vendor profiles (Admin only)
    """
    
    def patch(self, request, vendor_id, *args, **kwargs):
        """
        Approve or reject a vendor profile
        
        Args:
            vendor_id: The vendor ID
            
        Request Body:
            - approval_status: 'approved' or 'rejected' (required)
            - rejection_reason: Reason for rejection (optional, for rejected status)
            - commission_percentage: Commission percentage (optional, for approved vendors)
            - max_products_limit: Maximum products limit (optional, for approved vendors)
        
        Returns:
            200: Vendor approval status updated
            400: Validation error
            404: Vendor not found
            500: Server error
        """
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Get vendor
        try:
            vendor = VendorProfiles.objects.select_related('user').get(vendor_id=vendor_id)
        except VendorProfiles.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get approval status from request
        approval_status_value = request.data.get('approval_status')
        
        if not approval_status_value:
            return Response(
                {'error': 'approval_status is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if approval_status_value not in ['approved', 'rejected']:
            return Response(
                {'error': 'approval_status must be either "approved" or "rejected"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            logger.info(f"Updating vendor {vendor_id}: current is_vendor_approved={vendor.is_vendor_approved}, approval_status={vendor.approval_status}")
            
            # Update approval status
            vendor.approval_status = approval_status_value
            vendor.is_vendor_approved = (approval_status_value == 'approved')
            
            # Handle rejection reason
            if approval_status_value == 'rejected':
                rejection_reason = request.data.get('rejection_reason')
                if rejection_reason:
                    vendor.rejection_reason = rejection_reason
                else:
                    vendor.rejection_reason = 'No reason provided'
            else:
                vendor.rejection_reason = None
            
            # Handle commission and product limit for approved vendors
            if approval_status_value == 'approved':
                commission_percentage = request.data.get('commission_percentage')
                if commission_percentage is not None:
                    try:
                        vendor.commission_percentage = float(commission_percentage)
                    except (ValueError, TypeError):
                        return Response(
                            {'error': 'commission_percentage must be a valid number'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                
                max_products_limit = request.data.get('max_products_limit')
                if max_products_limit is not None:
                    try:
                        vendor.max_products_limit = int(max_products_limit)
                    except (ValueError, TypeError):
                        return Response(
                            {'error': 'max_products_limit must be a valid integer'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
            
            logger.info(f"Updated vendor {vendor_id}: new is_vendor_approved={vendor.is_vendor_approved}, approval_status={vendor.approval_status}")
            
            # Save vendor
            vendor.save()
            
            logger.info(f"Vendor {vendor_id} saved successfully")
            
            message = f"Vendor {vendor_id} has been {approval_status_value}"
            if approval_status_value == 'rejected' and vendor.rejection_reason:
                message += f". Reason: {vendor.rejection_reason}"
            
            return Response({
                'message': message,
                'vendor_id': vendor_id,
                'approval_status': vendor.approval_status,
                'is_vendor_approved': vendor.is_vendor_approved,
                'rejection_reason': vendor.rejection_reason,
                'commission_percentage': str(vendor.commission_percentage) if vendor.commission_percentage else None,
                'max_products_limit': vendor.max_products_limit,
                'shop_name': vendor.shop_name,
                'business_type': vendor.business_type
            }, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error approving vendor {vendor_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'An unexpected error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def get(self, request, vendor_id=None, *args, **kwargs):
        """
        Get vendor approval status or list all vendors pending approval
        
        Args:
            vendor_id: The vendor ID (optional)
            
        Query Parameters:
            - status: Filter by approval_status ('pending', 'approved', 'rejected')
            - limit: Number of results to return (default: 50)
            - offset: Offset for pagination (default: 0)
        
        Returns:
            200: Vendor approval status or list of vendors
            404: Vendor not found (if vendor_id provided)
        """
        if vendor_id:
            # Get single vendor approval status
            try:
                vendor = VendorProfiles.objects.select_related('user').get(vendor_id=vendor_id)
                
                return Response({
                    'vendor_id': vendor.vendor_id,
                    'shop_name': vendor.shop_name,
                    'shop_slug': vendor.shop_slug,
                    'business_type': vendor.business_type,
                    'approval_status': vendor.approval_status,
                    'is_vendor_approved': vendor.is_vendor_approved,
                    'rejection_reason': vendor.rejection_reason,
                    'commission_percentage': str(vendor.commission_percentage) if vendor.commission_percentage else None,
                    'max_products_limit': vendor.max_products_limit,
                    'is_gst_verified': vendor.is_gst_verified,
                    'is_active': vendor.is_active,
                    'user': {
                        'user_id': vendor.user.user_id,
                        'firstName': vendor.user.firstName,
                        'lastName': vendor.user.lastName,
                        'emailID': vendor.user.emailID,
                        'mobileNumber': vendor.user.mobileNumber
                    },
                    'created_at': vendor.created_at.isoformat() if vendor.created_at else None,
                    'updated_at': vendor.updated_at.isoformat() if vendor.updated_at else None
                }, status=status.HTTP_200_OK)
            
            except VendorProfiles.DoesNotExist:
                return Response(
                    {'error': 'Vendor not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # List vendors with optional filtering
            status_filter = request.query_params.get('status', None)
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))
            
            # Build query
            vendors_query = VendorProfiles.objects.select_related('user').all()
            
            if status_filter and status_filter in ['pending', 'approved', 'rejected']:
                vendors_query = vendors_query.filter(approval_status=status_filter)
            
            # Get total count
            total_count = vendors_query.count()
            
            # Apply pagination
            vendors = vendors_query[offset:offset + limit]
            
            vendors_list = []
            for vendor in vendors:
                vendors_list.append({
                    'vendor_id': vendor.vendor_id,
                    'shop_name': vendor.shop_name,
                    'shop_slug': vendor.shop_slug,
                    'business_type': vendor.business_type,
                    'approval_status': vendor.approval_status,
                    'is_vendor_approved': vendor.is_vendor_approved,
                    'rejection_reason': vendor.rejection_reason,
                    'commission_percentage': str(vendor.commission_percentage) if vendor.commission_percentage else None,
                    'max_products_limit': vendor.max_products_limit,
                    'is_gst_verified': vendor.is_gst_verified,
                    'is_active': vendor.is_active,
                    'user': {
                        'user_id': vendor.user.user_id,
                        'firstName': vendor.user.firstName,
                        'lastName': vendor.user.lastName,
                        'emailID': vendor.user.emailID,
                        'mobileNumber': vendor.user.mobileNumber
                    },
                    'created_at': vendor.created_at.isoformat() if vendor.created_at else None,
                    'updated_at': vendor.updated_at.isoformat() if vendor.updated_at else None
                })
            
            return Response({
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'vendors': vendors_list
            }, status=status.HTTP_200_OK)