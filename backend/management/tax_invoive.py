from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from kirazee_app.models import Business
from .models import BusinessTaxInvoice
from .serializers import BusinessTaxInvoiceSerializer


@api_view(['GET', 'POST'])
def tax_invoices_list_create(request, business_id):
	"""
	GET  -> List all tax invoices for a business_id
	POST -> Create a new tax invoice for a business_id

	Path parameter:
	- business_id (required)

	For POST, expected payload (example):
	{
	  "business_name": "ABC Traders",           // optional, defaults from Business if omitted
	  "business_address": "Address...",        // optional
	  "customer_details": "Customer details",  // optional
	  "invoice_number": "INV-001",             // required
	  "invoice_date": "2025-11-25",            // optional (YYYY-MM-DD)
	  "due_date": "2025-12-05",                // optional
	  "billing_address": "Billing addr",       // optional
	  "shipping_address": "Shipping addr",     // optional
	  "place_of_supply": "Karnataka",          // optional
	  "items": [                                // required - JSON (list or object)
	     {"name": "Item 1", "qty": 2, "rate": 100}
	  ],
	  "total_taxable_value": "200.00",         // optional
	  "total_amount": "236.00",                // optional
	  "bank_name": "XYZ Bank",                // optional
	  "bank_account_holder": "ABC Traders",    // optional
	  "bank_account_number": "1234567890",     // optional
	  "bank_ifsc": "XYZB0000123",             // optional
	  "bank_branch": "Main Branch"            // optional
	}
	"""
	try:
		try:
			business = Business.objects.get(business_id=business_id)
		except Business.DoesNotExist:
			return Response(
				{"error": f"Business with business_id {business_id} does not exist"},
				status=status.HTTP_400_BAD_REQUEST,
			)

		if request.method == 'GET':
			invoice_number = request.GET.get('invoice_number')
			queryset = BusinessTaxInvoice.objects.filter(business_id=business)
			if invoice_number:
				queryset = queryset.filter(invoice_number=invoice_number)
			queryset = queryset.order_by('-invoice_date', '-invoice_id')
			serializer = BusinessTaxInvoiceSerializer(queryset, many=True)
			return Response(
				{
					'business_id': business.business_id,
					'count': len(serializer.data),
					'invoices': serializer.data,
				},
				status=status.HTTP_200_OK,
			)

		# POST - create
		data = request.data.copy()
		# Ensure business_id is bound to the path value
		data['business_id'] = business.business_id

		# Optionally default business_name and address if not provided
		data.setdefault('business_name', getattr(business, 'business_name', ''))
		data.setdefault('business_address', getattr(business, 'business_address', ''))

		serializer = BusinessTaxInvoiceSerializer(data=data)
		if serializer.is_valid():
			invoice = serializer.save()
			response_serializer = BusinessTaxInvoiceSerializer(invoice)
			return Response(
				{
					'message': 'Tax invoice created successfully',
					'invoice': response_serializer.data,
				},
				status=status.HTTP_201_CREATED,
			)

		return Response(
			{
				'error': 'Validation failed',
				'details': serializer.errors,
			},
			status=status.HTTP_400_BAD_REQUEST,
		)

	except Exception as e:
		return Response(
			{
				'error': 'An error occurred while processing tax invoices',
				'details': str(e),
			},
			status=status.HTTP_500_INTERNAL_SERVER_ERROR,
		)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
def tax_invoice_detail(request, business_id, invoice_number):
	"""
	Work with a single tax invoice identified by (business_id, invoice_number).

	Path parameters:
	- business_id (required)
	- invoice_number (required)
	"""
	try:
		try:
			business = Business.objects.get(business_id=business_id)
		except Business.DoesNotExist:
			return Response(
				{"error": f"Business with business_id {business_id} does not exist"},
				status=status.HTTP_400_BAD_REQUEST,
			)

		# Try to find invoice by invoice_number first, then fall back to numeric invoice_id
		invoice = None
		try:
			invoice = BusinessTaxInvoice.objects.get(
				business_id=business,
				invoice_number=invoice_number,
			)
		except BusinessTaxInvoice.DoesNotExist:
			# If the path segment looks like a number, treat it as invoice_id
			if str(invoice_number).isdigit():
				try:
					invoice = BusinessTaxInvoice.objects.get(
						business_id=business,
						invoice_id=int(invoice_number),
					)
				except BusinessTaxInvoice.DoesNotExist:
					invoice = None

		if invoice is None:
			return Response(
				{
					'error': 'Tax invoice not found',
					'details': f'No invoice found for business_id={business_id} with invoice_number or id={invoice_number}',
				},
				status=status.HTTP_404_NOT_FOUND,
			)

		if request.method == 'GET':
			serializer = BusinessTaxInvoiceSerializer(invoice)
			return Response({'invoice': serializer.data}, status=status.HTTP_200_OK)

		if request.method in ['PUT', 'PATCH']:
			data = request.data.copy()
			# Force business_id from path so it cannot be changed
			data['business_id'] = business.business_id
			partial = request.method == 'PATCH'
			serializer = BusinessTaxInvoiceSerializer(invoice, data=data, partial=partial)
			if serializer.is_valid():
				updated_invoice = serializer.save()
				response_serializer = BusinessTaxInvoiceSerializer(updated_invoice)
				return Response(
					{
						'message': 'Tax invoice updated successfully',
						'invoice': response_serializer.data,
					},
					status=status.HTTP_200_OK,
				)

			return Response(
				{
					'error': 'Validation failed',
					'details': serializer.errors,
				},
				status=status.HTTP_400_BAD_REQUEST,
			)

		# DELETE
		invoice.delete()
		return Response(
			{
				'message': 'Tax invoice deleted successfully',
				'business_id': business.business_id,
				'invoice_number': invoice_number,
			},
			status=status.HTTP_200_OK,
		)

	except Exception as e:
		return Response(
			{
				'error': 'An error occurred while processing tax invoice details',
				'details': str(e),
			},
			status=status.HTTP_500_INTERNAL_SERVER_ERROR,
		)

