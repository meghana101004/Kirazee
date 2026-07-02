"""
Support Dashboard Views
Handles support ticket management and analytics
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import timedelta
from .models import SupportTicket
import logging

logger = logging.getLogger(__name__)


class SupportDashboardView(APIView):
    """
    Get support dashboard overview with ticket statistics
    """
    permission_classes = []  # Remove authentication for testing
    
    def get(self, request):
        """Get support dashboard data"""
        try:
            # Get all tickets
            all_tickets = SupportTicket.objects.all()
            
            # Calculate statistics
            total_tickets = all_tickets.count()
            open_tickets = all_tickets.filter(status='open').count()
            in_progress_tickets = all_tickets.filter(status='in_progress').count()
            resolved_tickets = all_tickets.filter(status='resolved').count()
            closed_tickets = all_tickets.filter(status='closed').count()
            
            # Calculate average resolution time (only for resolved/closed tickets)
            resolved_with_time = all_tickets.filter(
                status__in=['resolved', 'closed'],
                resolution_time_minutes__isnull=False
            )
            avg_resolution_time = resolved_with_time.aggregate(
                avg_time=Avg('resolution_time_minutes')
            )['avg_time'] or 0
            
            # Convert to hours and minutes
            avg_hours = int(avg_resolution_time // 60)
            avg_minutes = int(avg_resolution_time % 60)
            avg_resolution_formatted = f"{avg_hours}h {avg_minutes}m" if avg_hours > 0 else f"{avg_minutes}m"
            
            # Get tickets by category
            category_breakdown = all_tickets.values('category').annotate(
                count=Count('ticket_id')
            ).order_by('-count')
            
            # Get tickets by priority
            priority_breakdown = all_tickets.values('priority').annotate(
                count=Count('ticket_id')
            ).order_by('-count')
            
            # Get recent tickets (last 10)
            recent_tickets = all_tickets.order_by('-created_at')[:10].values(
                'ticket_id', 'customer_name', 'subject', 'category', 
                'priority', 'status', 'created_at', 'assigned_agent'
            )
            
            # Get tickets created today
            today = timezone.now().date()
            tickets_today = all_tickets.filter(created_at__date=today).count()
            
            # Get tickets created this week
            week_ago = timezone.now() - timedelta(days=7)
            tickets_this_week = all_tickets.filter(created_at__gte=week_ago).count()
            
            # Get customer satisfaction (average rating)
            avg_rating = all_tickets.filter(
                customer_rating__isnull=False
            ).aggregate(avg_rating=Avg('customer_rating'))['avg_rating'] or 0
            
            # Response data
            dashboard_data = {
                'success': True,
                'message': 'Support dashboard data retrieved successfully',
                'data': {
                    'overview': {
                        'total_tickets': total_tickets,
                        'open_tickets': open_tickets,
                        'in_progress_tickets': in_progress_tickets,
                        'resolved_tickets': resolved_tickets,
                        'closed_tickets': closed_tickets,
                        'tickets_today': tickets_today,
                        'tickets_this_week': tickets_this_week
                    },
                    'performance': {
                        'avg_resolution_time_minutes': round(avg_resolution_time, 2),
                        'avg_resolution_time_formatted': avg_resolution_formatted,
                        'customer_satisfaction': round(avg_rating, 2),
                        'resolution_rate': round((resolved_tickets + closed_tickets) / total_tickets * 100, 2) if total_tickets > 0 else 0
                    },
                    'category_breakdown': list(category_breakdown),
                    'priority_breakdown': list(priority_breakdown),
                    'recent_tickets': list(recent_tickets)
                }
            }
            
            return Response(dashboard_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving support dashboard data: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving support dashboard data: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SupportTicketsListView(APIView):
    """
    Get list of support tickets with filtering and pagination
    """
    permission_classes = []
    
    def get(self, request):
        """Get filtered list of support tickets"""
        try:
            # Get query parameters
            status_filter = request.GET.get('status', None)
            category_filter = request.GET.get('category', None)
            priority_filter = request.GET.get('priority', None)
            search = request.GET.get('search', None)
            page = int(request.GET.get('page', 1))
            limit = int(request.GET.get('limit', 20))
            
            # Base queryset
            tickets = SupportTicket.objects.all()
            
            # Apply filters
            if status_filter:
                tickets = tickets.filter(status=status_filter)
            if category_filter:
                tickets = tickets.filter(category=category_filter)
            if priority_filter:
                tickets = tickets.filter(priority=priority_filter)
            if search:
                tickets = tickets.filter(
                    Q(ticket_id__icontains=search) |
                    Q(customer_name__icontains=search) |
                    Q(subject__icontains=search) |
                    Q(customer_email__icontains=search)
                )
            
            # Get total count
            total_count = tickets.count()
            
            # Pagination
            start = (page - 1) * limit
            end = start + limit
            tickets = tickets.order_by('-created_at')[start:end]
            
            # Serialize tickets
            tickets_data = []
            for ticket in tickets:
                tickets_data.append({
                    'ticket_id': ticket.ticket_id,
                    'customer_name': ticket.customer_name,
                    'customer_email': ticket.customer_email,
                    'customer_phone': ticket.customer_phone,
                    'subject': ticket.subject,
                    'description': ticket.description,
                    'category': ticket.category,
                    'priority': ticket.priority,
                    'status': ticket.status,
                    'assigned_agent': ticket.assigned_agent,
                    'resolution_notes': ticket.resolution_notes,
                    'resolution_time_minutes': ticket.resolution_time_minutes,
                    'created_at': ticket.created_at.isoformat(),
                    'updated_at': ticket.updated_at.isoformat(),
                    'resolved_at': ticket.resolved_at.isoformat() if ticket.resolved_at else None,
                    'order_id': ticket.order_id,
                    'business_name': ticket.business_name,
                    'customer_rating': ticket.customer_rating
                })
            
            return Response({
                'success': True,
                'message': 'Support tickets retrieved successfully',
                'data': {
                    'tickets': tickets_data,
                    'pagination': {
                        'total': total_count,
                        'page': page,
                        'limit': limit,
                        'total_pages': (total_count + limit - 1) // limit
                    }
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving support tickets: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving support tickets: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SupportTicketDetailView(APIView):
    """
    Get, update, or delete a specific support ticket
    """
    permission_classes = []
    
    def get(self, request, ticket_id):
        """Get ticket details"""
        try:
            ticket = SupportTicket.objects.get(ticket_id=ticket_id)
            
            ticket_data = {
                'ticket_id': ticket.ticket_id,
                'customer_name': ticket.customer_name,
                'customer_email': ticket.customer_email,
                'customer_phone': ticket.customer_phone,
                'subject': ticket.subject,
                'description': ticket.description,
                'category': ticket.category,
                'priority': ticket.priority,
                'status': ticket.status,
                'assigned_agent': ticket.assigned_agent,
                'resolution_notes': ticket.resolution_notes,
                'resolution_time_minutes': ticket.resolution_time_minutes,
                'created_at': ticket.created_at.isoformat(),
                'updated_at': ticket.updated_at.isoformat(),
                'resolved_at': ticket.resolved_at.isoformat() if ticket.resolved_at else None,
                'order_id': ticket.order_id,
                'business_name': ticket.business_name,
                'customer_rating': ticket.customer_rating
            }
            
            return Response({
                'success': True,
                'message': 'Ticket details retrieved successfully',
                'data': ticket_data
            }, status=status.HTTP_200_OK)
            
        except SupportTicket.DoesNotExist:
            return Response({
                'success': False,
                'message': f'Ticket {ticket_id} not found',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error retrieving ticket details: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error retrieving ticket details: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def patch(self, request, ticket_id):
        """Update ticket status or details"""
        try:
            ticket = SupportTicket.objects.get(ticket_id=ticket_id)
            
            # Update fields
            if 'status' in request.data:
                ticket.status = request.data['status']
                if request.data['status'] in ['resolved', 'closed'] and not ticket.resolved_at:
                    ticket.resolved_at = timezone.now()
                    # Calculate resolution time
                    time_diff = ticket.resolved_at - ticket.created_at
                    ticket.resolution_time_minutes = int(time_diff.total_seconds() / 60)
            
            if 'assigned_agent' in request.data:
                ticket.assigned_agent = request.data['assigned_agent']
            
            if 'resolution_notes' in request.data:
                ticket.resolution_notes = request.data['resolution_notes']
            
            if 'priority' in request.data:
                ticket.priority = request.data['priority']
            
            ticket.save()
            
            return Response({
                'success': True,
                'message': 'Ticket updated successfully',
                'data': {'ticket_id': ticket.ticket_id}
            }, status=status.HTTP_200_OK)
            
        except SupportTicket.DoesNotExist:
            return Response({
                'success': False,
                'message': f'Ticket {ticket_id} not found',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating ticket: {str(e)}")
            return Response({
                'success': False,
                'message': f'Error updating ticket: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
