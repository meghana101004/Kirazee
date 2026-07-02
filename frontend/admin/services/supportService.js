/**
 * Support Service
 * Handles all support ticket related API calls
 */

export class SupportService {
  static get SUPPORT_BASE_URL() {
    return `https://kirazee.com/kirazee/api/v1/admin/support`;
  }

  /**
   * Get support dashboard overview
   */
  static async getSupportDashboard() {
    try {
      const response = await fetch(`${this.SUPPORT_BASE_URL}/dashboard/`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching support dashboard:', error);
      throw error;
    }
  }

  /**
   * Get list of support tickets with filters
   */
  static async getSupportTickets(params = {}) {
    try {
      const queryParams = new URLSearchParams();
      
      if (params.status) queryParams.append('status', params.status);
      if (params.category) queryParams.append('category', params.category);
      if (params.priority) queryParams.append('priority', params.priority);
      if (params.search) queryParams.append('search', params.search);
      if (params.page) queryParams.append('page', params.page);
      if (params.limit) queryParams.append('limit', params.limit);

      const queryString = queryParams.toString();
      const url = `${this.SUPPORT_BASE_URL}/tickets/${queryString ? `?${queryString}` : ''}`;

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching support tickets:', error);
      throw error;
    }
  }

  /**
   * Get specific ticket details
   */
  static async getTicketDetails(ticketId) {
    try {
      const response = await fetch(`${this.SUPPORT_BASE_URL}/tickets/${ticketId}/`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching ticket details:', error);
      throw error;
    }
  }

  /**
   * Update ticket status or details
   */
  static async updateTicket(ticketId, updateData) {
    try {
      const response = await fetch(`${this.SUPPORT_BASE_URL}/tickets/${ticketId}/`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updateData)
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error updating ticket:', error);
      throw error;
    }
  }

  /**
   * Transform support data for dashboard display
   */
  static transformSupportData(apiResponse) {
    const data = apiResponse.data;
    
    // Capitalize first letter helper
    const capitalize = (str) => str.charAt(0).toUpperCase() + str.slice(1).replace('_', ' ');
    
    return {
      supportTickets: {
        total: data.overview.total_tickets,
        open: data.overview.open_tickets,
        inProgress: data.overview.in_progress_tickets,
        resolved: data.overview.resolved_tickets,
        closed: data.overview.closed_tickets,
        averageResolutionTime: data.performance.avg_resolution_time_formatted
      },
      customerIssues: {
        total: data.overview.total_tickets,
        orderRelated: data.category_breakdown.find(c => c.category === 'order_issue')?.count || 0,
        paymentRelated: data.category_breakdown.find(c => c.category === 'payment_issue')?.count || 0,
        deliveryRelated: data.category_breakdown.find(c => c.category === 'delivery_issue')?.count || 0,
        accountRelated: data.category_breakdown.find(c => c.category === 'account_issue')?.count || 0
      },
      performance: {
        resolutionRate: data.performance.resolution_rate,
        ticketsLast24h: data.overview.tickets_today,
        ticketsLast7d: data.overview.tickets_this_week
      },
      recentActivity: data.recent_tickets.map(ticket => ({
        ticket_id: ticket.ticket_id,
        customer_name: ticket.customer_name,
        subject: ticket.subject,
        category: capitalize(ticket.category),
        priority: capitalize(ticket.priority),
        status: capitalize(ticket.status),
        assigned_agent: ticket.assigned_agent,
        created_at: ticket.created_at
      }))
    };
  }
}

export default SupportService;
