from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection
from django.db import models
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import json
import logging
import math
from .models import BusinessContactUs
from kirazee_app.models import Business, Registration
from datetime import date, timedelta

logger = logging.getLogger(__name__)


# ============================================================================
# BUSINESS CONTACT US SERVICE
# ============================================================================

class BusinessContactUsView(APIView):
    """
    Business Contact Us service for handling customer inquiries to specific businesses
    POST /api/v1/admin/business-contact-us - Submit contact form to business owner
    """
    permission_classes = []  # Public endpoint
    
    def post(self, request):
        """Submit contact us form to a specific business"""
        try:
            data = request.data
            
            # Validate required fields
            required_fields = ['business_id', 'firstName', 'lastName', 'emailID', 'phoneNumber', 'subject', 'message']
            missing_fields = [field for field in required_fields if not data.get(field)]
            
            if missing_fields:
                return Response({
                    'success': False,
                    'error': f'Missing required fields: {", ".join(missing_fields)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate email format
            email = data.get('emailID', '').strip()
            if '@' not in email or '.' not in email:
                return Response({
                    'success': False,
                    'error': 'Invalid email format'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get business
            try:
                business = Business.objects.get(business_id=data.get('business_id'))
            except Business.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Business not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if business has email
            if not business.businessEmail:
                return Response({
                    'success': False,
                    'error': 'Business does not have a contact email configured'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create business contact us record
            business_contact = BusinessContactUs.objects.create(
                business=business,
                firstName=data.get('firstName', '').strip(),
                lastName=data.get('lastName', '').strip(),
                emailID=email,
                phoneNumber=data.get('phoneNumber', '').strip(),
                subject=data.get('subject', '').strip(),
                message=data.get('message', '').strip(),
                receiver=business.businessEmail  # Store where email will be sent
            )
            
            # Send email notification to business owner
            try:
                self._send_business_notification(business_contact)
                email_sent = True
                business_contact.email_sent_status = 'sent'
                business_contact.email_sent_at = timezone.now()
                business_contact.save()
            except Exception as e:
                logger.error(f"Failed to send business notification email: {str(e)}")
                email_sent = False
                business_contact.email_sent_status = 'failed'
                business_contact.save()
            
            # Send confirmation email to user
            try:
                self._send_user_confirmation(business_contact)
                user_email_sent = True
            except Exception as e:
                logger.error(f"Failed to send user confirmation email: {str(e)}")
                user_email_sent = False
            
            return Response({
                'success': True,
                'message': 'Contact form submitted successfully to business',
                'data': {
                    'contact_id': business_contact.id,
                    'business_id': business.business_id,
                    'business_name': business.businessName,
                    'submitted_at': business_contact.created_at.isoformat(),
                    'business_email_sent': email_sent,
                    'confirmation_email_sent': user_email_sent
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error submitting business contact form: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to submit contact form. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _send_business_notification(self, business_contact):
        """Send email notification to business owner"""
        subject = f"New Customer Inquiry - {business_contact.subject}"
        
        # HTML email template
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                .field {{ margin-bottom: 15px; }}
                .label {{ font-weight: bold; color: #555; }}
                .value {{ margin-top: 5px; padding: 10px; background: white; border-left: 4px solid #28a745; }}
                .message-box {{ background: white; padding: 15px; border-radius: 5px; border: 1px solid #ddd; }}
                .business-info {{ background: #e8f5e8; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📬 New Customer Inquiry</h1>
                    <p>{business_contact.business.businessName}</p>
                </div>
                <div class="content">
                    <div class="business-info">
                        <strong>🏢 Business:</strong> {business_contact.business.businessName}<br>
                        <strong>🆔 Business ID:</strong> {business_contact.business.business_id}<br>
                        <strong>📧 Business Email:</strong> {business_contact.business.businessEmail}
                    </div>
                    
                    <div class="field">
                        <div class="label">👤 Customer Name:</div>
                        <div class="value">{business_contact.full_name}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">📧 Customer Email:</div>
                        <div class="value">{business_contact.emailID}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">📱 Phone Number:</div>
                        <div class="value">{business_contact.phoneNumber}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">📋 Subject:</div>
                        <div class="value">{business_contact.subject}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">💬 Message:</div>
                        <div class="message-box">{business_contact.message}</div>
                    </div>
                    
                    <div class="field">
                        <div class="label">🕒 Submitted At:</div>
                        <div class="value">{business_contact.created_at.strftime('%B %d, %Y at %I:%M %p')}</div>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107; margin-top: 20px;">
                        <strong>⚡ Quick Action:</strong> Please respond to this customer inquiry promptly to provide excellent service.
                    </div>
                </div>
                <div class="footer">
                    <p>This inquiry was submitted through the Kirazee platform for your business.</p>
                    <p>Responding quickly helps build customer trust and loyalty.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
        New Customer Inquiry - {business_contact.business.businessName}
        
        Business: {business_contact.business.businessName} (ID: {business_contact.business.business_id})
        
        Customer Name: {business_contact.full_name}
        Email: {business_contact.emailID}
        Phone: {business_contact.phoneNumber}
        Subject: {business_contact.subject}
        
        Message:
        {business_contact.message}
        
        Submitted At: {business_contact.created_at.strftime('%B %d, %Y at %I:%M %p')}
        
        Please respond to this customer inquiry promptly.
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'EMAIL_HOST_USER', 'kirazeeofficial@gmail.com'),
            recipient_list=[business_contact.business.businessEmail],
            html_message=html_message,
            fail_silently=False
        )
    
    def _send_user_confirmation(self, business_contact):
        """Send confirmation email to user"""
        subject = f"Thank you for contacting {business_contact.business.businessName} - We've received your inquiry"
        
        # HTML confirmation email
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                .highlight {{ background: white; padding: 15px; border-radius: 5px; border-left: 4px solid #28a745; margin: 15px 0; }}
                .business-info {{ background: #e8f5e8; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Thank You for Contacting Us!</h1>
                    <p>{business_contact.business.businessName}</p>
                </div>
                <div class="content">
                    <p>Dear {business_contact.firstName},</p>
                    
                    <p>Thank you for reaching out to <strong>{business_contact.business.businessName}</strong>! We have successfully received your inquiry and the business owner will review it shortly.</p>
                    
                    <div class="business-info">
                        <strong>🏢 Business Contacted:</strong> {business_contact.business.businessName}<br>
                        <strong>📧 Business Email:</strong> {business_contact.business.businessEmail}
                    </div>
                    
                    <div class="highlight">
                        <strong>📋 Your Inquiry Details:</strong><br>
                        <strong>Subject:</strong> {business_contact.subject}<br>
                        <strong>Submitted:</strong> {business_contact.created_at.strftime('%B %d, %Y at %I:%M %p')}<br>
                        <strong>Reference ID:</strong> #{business_contact.id}
                    </div>
                    
                    <p>🕒 <strong>Response Time:</strong> The business owner typically responds within 24-48 hours during business days.</p>
                    
                    <p>📧 <strong>Next Steps:</strong> The business owner will review your message and get back to you at {business_contact.emailID} with a detailed response.</p>
                    
                    <p>If you have any urgent concerns, you can contact the business directly at {business_contact.business.businessEmail}.</p>
                    
                    <p>Thank you for choosing {business_contact.business.businessName}!</p>
                    
                    <p>Best regards,<br>
                    <strong>The {business_contact.business.businessName} Team</strong></p>
                </div>
                <div class="footer">
                    <p>This is an automated confirmation email.</p>
                    <p>© 2024 Kirazee. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
        Thank you for contacting {business_contact.business.businessName}!
        
        Dear {business_contact.firstName},
        
        We have successfully received your inquiry about "{business_contact.subject}".
        
        Business: {business_contact.business.businessName}
        Reference ID: #{business_contact.id}
        Submitted: {business_contact.created_at.strftime('%B %d, %Y at %I:%M %p')}
        
        The business owner will review your message and respond within 24-48 hours during business days.
        
        For urgent matters, you can contact the business directly at: {business_contact.business.businessEmail}
        
        Thank you for choosing {business_contact.business.businessName}!
        
        Best regards,
        The {business_contact.business.businessName} Team
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'EMAIL_HOST_USER', 'teamkirazee@gmail.com'),
            recipient_list=[business_contact.emailID],
            html_message=html_message,
            fail_silently=False
        )


class BusinessContactUsManagementView(APIView):
    """
    Business owner service for managing contact us requests for their business
    GET /api/v1/admin/business-contact-us/manage?business_id=<business_id> - List all contact requests for a business
    """
    permission_classes = []  # Add authentication as needed
    
    def get(self, request):
        """List all contact us requests for a specific business with filtering and pagination"""
        try:
            # Get query parameters
            business_id = request.query_params.get('business_id')
            if not business_id:
                return Response({
                    'success': False,
                    'error': 'business_id is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            page = int(request.query_params.get('page', 1))
            limit = min(int(request.query_params.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            # Filter parameters
            status_filter = request.query_params.get('status')  # 'resolved', 'pending'
            search_query = request.query_params.get('search')
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            
            # Get business
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Business not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Build queryset
            queryset = BusinessContactUs.objects.filter(business=business)
            
            # Apply filters
            if status_filter == 'resolved':
                queryset = queryset.filter(is_resolved=True)
            elif status_filter == 'pending':
                queryset = queryset.filter(is_resolved=False)
            
            if search_query:
                queryset = queryset.filter(
                    models.Q(firstName__icontains=search_query) |
                    models.Q(lastName__icontains=search_query) |
                    models.Q(emailID__icontains=search_query) |
                    models.Q(subject__icontains=search_query) |
                    models.Q(message__icontains=search_query)
                )
            
            if date_from:
                from datetime import datetime
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                queryset = queryset.filter(created_at__gte=date_from_obj)
            
            if date_to:
                from datetime import datetime
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                queryset = queryset.filter(created_at__lte=date_to_obj)
            
            # Get total count
            total_count = queryset.count()
            total_pages = (total_count + limit - 1) // limit
            
            # Apply pagination
            contact_requests = queryset[offset:offset + limit]
            
            # Serialize data
            requests_data = []
            for contact in contact_requests:
                requests_data.append({
                    'id': contact.id,
                    'business_id': contact.business.business_id,
                    'business_name': contact.business.businessName,
                    'firstName': contact.firstName,
                    'lastName': contact.lastName,
                    'full_name': contact.full_name,
                    'emailID': contact.emailID,
                    'phoneNumber': contact.phoneNumber,
                    'subject': contact.subject,
                    'message': contact.message,
                    'created_at': contact.created_at.isoformat(),
                    'is_resolved': contact.is_resolved,
                    'business_notes': contact.business_notes,
                    'email_sent_status': contact.email_sent_status,
                    'email_sent_at': contact.email_sent_at.isoformat() if contact.email_sent_at else None,
                    'receiver': contact.receiver,
                    'days_ago': (timezone.now() - contact.created_at).days
                })
            
            return Response({
                'success': True,
                'data': {
                    'business': {
                        'business_id': business.business_id,
                        'business_name': business.businessName,
                        'business_email': business.businessEmail
                    },
                    'pagination': {
                        'current_page': page,
                        'total_count': total_count,
                        'total_pages': total_pages,
                        'has_next_page': page < total_pages,
                        'has_prev_page': page > 1,
                        'limit': limit
                    },
                    'filters': {
                        'status': status_filter,
                        'search': search_query,
                        'date_from': date_from,
                        'date_to': date_to
                    },
                    'summary': {
                        'total_requests': BusinessContactUs.objects.filter(business=business).count(),
                        'pending_requests': BusinessContactUs.objects.filter(business=business, is_resolved=False).count(),
                        'resolved_requests': BusinessContactUs.objects.filter(business=business, is_resolved=True).count()
                    },
                    'requests': requests_data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving business contact requests: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to retrieve contact requests'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BusinessContactUsReplyView(APIView):
    """
    Business owner service for replying to contact us requests
    POST /api/v1/admin/business-contact-us/<int:contact_id>/reply - Reply to a contact request
    """
    permission_classes = []  # Add authentication as needed
    
    def post(self, request, contact_id):
        """Reply to a business contact us request with business owner notes"""
        try:
            # Get the contact request
            try:
                business_contact = BusinessContactUs.objects.get(id=contact_id)
            except BusinessContactUs.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Contact request not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            data = request.data
            business_notes = data.get('business_notes', '').strip()
            
            if not business_notes:
                return Response({
                    'success': False,
                    'error': 'Business notes are required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update the contact request
            business_contact.business_notes = business_notes
            business_contact.is_resolved = True
            business_contact.save()
            
            # Send reply email to user
            try:
                self._send_business_reply_email(business_contact, business_notes)
                email_sent = True
            except Exception as e:
                logger.error(f"Failed to send business reply email: {str(e)}")
                email_sent = False
            
            return Response({
                'success': True,
                'message': 'Reply sent successfully',
                'data': {
                    'contact_id': business_contact.id,
                    'business_id': business_contact.business.business_id,
                    'business_name': business_contact.business.businessName,
                    'is_resolved': business_contact.is_resolved,
                    'business_notes': business_contact.business_notes,
                    'email_sent': email_sent,
                    'receiver': business_contact.receiver,
                    'replied_at': timezone.now().isoformat()
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error sending business reply: {str(e)}")
            return Response({
                'success': False,
                'error': 'Failed to send reply'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _send_business_reply_email(self, business_contact, business_notes):
        """Send business owner reply email to user"""
        subject = f"Re: {business_contact.subject} - Response from {business_contact.business.businessName}"
        
        # HTML reply email template
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                .original-inquiry {{ background: #e8f4f8; padding: 15px; border-radius: 5px; border-left: 4px solid #17a2b8; margin: 15px 0; }}
                .business-response {{ background: white; padding: 20px; border-radius: 5px; border-left: 4px solid #28a745; margin: 15px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                .highlight {{ background: #fff3cd; padding: 10px; border-radius: 5px; border-left: 4px solid #ffc107; margin: 10px 0; }}
                .business-info {{ background: #e8f5e8; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📧 Response from {business_contact.business.businessName}</h1>
                    <p>Your inquiry has been resolved</p>
                </div>
                <div class="content">
                    <p>Dear {business_contact.firstName},</p>
                    
                    <p>Thank you for your patience. {business_contact.business.businessName} has reviewed your inquiry and is pleased to provide you with a response.</p>
                    
                    <div class="business-info">
                        <strong>🏢 Business:</strong> {business_contact.business.businessName}<br>
                        <strong>📧 Business Email:</strong> {business_contact.business.businessEmail}
                    </div>
                    
                    <div class="original-inquiry">
                        <strong>📋 Your Original Inquiry:</strong><br>
                        <strong>Subject:</strong> {business_contact.subject}<br>
                        <strong>Submitted:</strong> {business_contact.created_at.strftime('%B %d, %Y at %I:%M %p')}<br>
                        <strong>Reference ID:</strong> #{business_contact.id}<br><br>
                        <strong>Your Message:</strong><br>
                        <em>"{business_contact.message}"</em>
                    </div>
                    
                    <div class="business-response">
                        <strong>✅ Business Response:</strong><br><br>
                        {business_notes.replace(chr(10), '<br>')}
                    </div>
                    
                    <div class="highlight">
                        <strong>🎯 Status:</strong> Your inquiry has been marked as <strong>RESOLVED</strong>
                    </div>
                    
                    <p>If you have any follow-up questions or need further assistance, please don't hesitate to contact {business_contact.business.businessName} again.</p>
                    
                    <p>Thank you for choosing {business_contact.business.businessName}!</p>
                    
                    <p>Best regards,<br>
                    <strong>The {business_contact.business.businessName} Team</strong></p>
                </div>
                <div class="footer">
                    <p>This response was sent by {business_contact.business.businessName} through the Kirazee platform.</p>
                    <p>© 2024 Kirazee. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
        Response from {business_contact.business.businessName}
        
        Dear {business_contact.firstName},
        
        Thank you for your patience. {business_contact.business.businessName} has reviewed your inquiry and is pleased to provide you with a response.
        
        Business: {business_contact.business.businessName}
        
        Your Original Inquiry:
        Subject: {business_contact.subject}
        Submitted: {business_contact.created_at.strftime('%B %d, %Y at %I:%M %p')}
        Reference ID: #{business_contact.id}
        
        Your Message:
        "{business_contact.message}"
        
        Business Response:
        {business_notes}
        
        Status: Your inquiry has been marked as RESOLVED
        
        If you have any follow-up questions or need further assistance, please don't hesitate to contact {business_contact.business.businessName} again.
        
        Thank you for choosing {business_contact.business.businessName}!
        
        Best regards,
        The {business_contact.business.businessName} Team
        """
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, 'EMAIL_HOST_USER', 'teamkirazee@gmail.com'),
            recipient_list=[business_contact.emailID],
            html_message=html_message,
            fail_silently=False
        )
