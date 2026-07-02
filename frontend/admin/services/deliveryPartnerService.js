import { API_ENDPOINTS } from '../utils/config';

export class DeliveryPartnerService {
  /**
   * Fetch delivery partners (boys) with business filter - REQUIRED
   * @param {object} params
   * @param {string} params.businessId - Business ID to filter partners (REQUIRED)
   * @param {boolean} [params.include_unassigned=false] - Include unassigned partners
   * @param {number} [params.page=1] - Page number
   * @param {number} [params.limit=25] - Items per page
   * @returns {Promise<object>} API response JSON
   */
  static async fetchPartners({ businessId, include_unassigned = false, page = 1, limit = 25 } = {}) {
    // Business ID is now required
    if (!businessId) {
      console.warn('No business ID provided - returning empty result');
      return {
        providers: [],
        pagination: { total_providers: 0, current_page: 1, per_page: limit, total_pages: 0 },
        message: 'No business ID provided'
      };
    }

    const qs = new URLSearchParams();
    qs.set('business_id', businessId); // Always set business_id
    if (include_unassigned) qs.set('include_unassigned', 'true');
    if (page) qs.set('page', String(page));
    if (limit) qs.set('limit', String(limit));
    // request server to attach order summary info when supported
    qs.set('include_order_summary', 'true');
    qs.set('include_recent_orders', 'true');

    const url = `${API_ENDPOINTS.BASE_URL}/delivery-partner/boys/${qs.toString() ? `?${qs.toString()}` : ''}`;

    try {
      const res = await fetch(url, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }

      const data = await res.json();
      
      // Log business-specific delivery partner info
      console.log(`Delivery Partners for Business ${businessId}:`, {
        businessId,
        totalPartners: data?.providers?.length || 0,
        partnersWithOrderData: data?.providers?.filter(p => p.order_summary || p.orderSummary)?.length || 0,
        message: data?.message || 'Success'
      });
      
      // Debug logging for all partners with order data
      if (data?.providers && data.providers.length > 0) {
        data.providers.forEach(partner => {
          const hasOrderData = partner.order_summary || partner.orderSummary;
          if (hasOrderData) {
            const orderSummary = partner.order_summary || partner.orderSummary;
            console.log(`Partner ${partner.user_id || partner.id} Order Data:`, {
              partnerId: partner.id,
              userId: partner.user_id,
              name: partner.name,
              hasOrderSummary: !!partner.order_summary,
              hasOrderSummaryAlt: !!partner.orderSummary,
              orderSummaryKeys: orderSummary ? Object.keys(orderSummary) : [],
              recentOrdersCount: orderSummary?.recent_orders?.length || orderSummary?.recentOrders?.length || 0
            });
          }
        });
      }
      
      // Handle empty results
      if (!data?.providers || data.providers.length === 0) {
        console.log(`No delivery partners found for business ${businessId}`);
        return {
          providers: [],
          pagination: data?.pagination || { total_providers: 0, current_page: 1, per_page: limit, total_pages: 0 },
          message: data?.message || `No delivery partners found for business ${businessId}`
        };
      }
      
      return data;
    } catch (err) {
      console.error('Error fetching delivery partners:', err);
      throw err;
    }
  }
}
