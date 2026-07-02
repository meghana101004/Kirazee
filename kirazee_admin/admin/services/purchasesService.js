import { API_ENDPOINTS } from '../utils/config';
import { AuthService } from './authService';

export class PurchasesService {
  static getActiveIds() {
    const user = AuthService.getUserData();
    const user_id = user?.user_id;

    // Try multiple sources to get business_id
    let business_id = null;
    try {
      const allBusinesses = JSON.parse(localStorage.getItem('allBusinessesData') || '[]');
      if (allBusinesses?.length) business_id = allBusinesses[0]?.business_id;
    } catch {}

    if (!business_id) {
      try {
        const comprehensive = JSON.parse(localStorage.getItem('userComprehensiveData') || 'null');
        business_id = comprehensive?.user_business?.business_id || comprehensive?.business_details?.business_id || null;
      } catch {}
    }

    return { user_id, business_id };
  }

  static async createPurchase(payload, user_id, business_id) {
    if (!user_id || !business_id) {
      const ids = this.getActiveIds();
      user_id = user_id || ids.user_id;
      business_id = business_id || ids.business_id;
    }

    if (!user_id || !business_id) {
      throw new Error('Missing user_id or business_id');
    }

    const url = `${API_ENDPOINTS.BASE_URL}/management/purchases/create/?user_id=${encodeURIComponent(
      user_id
    )}&business_id=${encodeURIComponent(business_id)}`;

    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const message = data?.error || resp.statusText || 'Request failed';
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data;
  }

  static async getSuppliers(business_id, { limit = 50, offset = 0, search = '' } = {}) {
    if (!business_id) {
      business_id = this.getActiveIds().business_id;
    }
    if (!business_id) throw new Error('Missing business_id');

    const params = new URLSearchParams({ business_id, limit: String(limit), offset: String(offset) });
    if (search) params.set('search', search);

    const url = `${API_ENDPOINTS.BASE_URL}/management/suppliers/?${params.toString()}`;
    const resp = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const message = data?.error || resp.statusText || 'Request failed';
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data; // {suppliers: [...], count: n}
  }

  static async getPurchasesByBusiness(business_id, { limit = 100, offset = 0 } = {}) {
    if (!business_id) {
      business_id = this.getActiveIds().business_id;
    }
    if (!business_id) throw new Error('Missing business_id');

    const params = new URLSearchParams({ business_id, limit: String(limit), offset: String(offset) });
    const url = `${API_ENDPOINTS.BASE_URL}/management/purchases/business/?${params.toString()}`;

    const resp = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const message = data?.error || resp.statusText || 'Request failed';
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data; // {purchases: [...], count, business_id}
  }

  static async updatePurchaseStatus(purchase_id, { payment_status, payment_method }, user_id, business_id) {
    if (!purchase_id) throw new Error('Missing purchase_id');
    const ids = this.getActiveIds();
    user_id = user_id || ids.user_id;
    business_id = business_id || ids.business_id;
    if (!user_id || !business_id) throw new Error('Missing user_id or business_id');

    const url = `${API_ENDPOINTS.BASE_URL}/management/purchases/${encodeURIComponent(purchase_id)}/status/`;
    try {
      console.debug('[PurchasesService.updatePurchaseStatus] PUT', url, { user_id, business_id, payment_status, payment_method });
      const resp = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id, business_id, payment_status, payment_method })
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        console.error('[PurchasesService.updatePurchaseStatus] Failed', { status: resp.status, url, data });
        const message = data?.error || resp.statusText || 'Request failed';
        throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
      }
      return data; // {message, purchase}
    } catch (err) {
      console.error('[PurchasesService.updatePurchaseStatus] Error', err);
      throw err;
    }
  }

  static async deletePurchase(purchase_id, user_id, business_id) {
    if (!purchase_id) throw new Error('Missing purchase_id');
    if (!user_id || !business_id) {
      const ids = this.getActiveIds();
      user_id = user_id || ids.user_id;
      business_id = business_id || ids.business_id;
    }
    if (!user_id || !business_id) throw new Error('Missing user_id or business_id');

    const url = `${API_ENDPOINTS.BASE_URL}/management/purchases/${encodeURIComponent(purchase_id)}/delete/?user_id=${encodeURIComponent(user_id)}&business_id=${encodeURIComponent(business_id)}`;
    try {
      console.debug('[PurchasesService.deletePurchase] DELETE', url);
      const resp = await fetch(url, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        console.error('[PurchasesService.deletePurchase] Failed', { status: resp.status, url, data });
        const message = data?.error || resp.statusText || 'Request failed';
        throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
      }
      return data; // {message, deleted_purchase}
    } catch (err) {
      console.error('[PurchasesService.deletePurchase] Error', err);
      throw err;
    }
  }

  static async updatePurchase(purchase_id, payload, user_id, business_id) {
    if (!purchase_id) throw new Error('Missing purchase_id');
    if (!user_id || !business_id) {
      const ids = this.getActiveIds();
      user_id = user_id || ids.user_id;
      business_id = business_id || ids.business_id;
    }
    if (!user_id || !business_id) throw new Error('Missing user_id or business_id');

    const url = `${API_ENDPOINTS.BASE_URL}/management/purchases/${encodeURIComponent(purchase_id)}/update/?user_id=${encodeURIComponent(user_id)}&business_id=${encodeURIComponent(business_id)}`;
    try {
      console.debug('[PurchasesService.updatePurchase] PUT', url, { payload });
      const resp = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        console.error('[PurchasesService.updatePurchase] Failed', { status: resp.status, url, data });
        const message = data?.error || resp.statusText || 'Request failed';
        throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
      }
      return data; // {message, purchase}
    } catch (err) {
      console.error('[PurchasesService.updatePurchase] Error', err);
      throw err;
    }
  }

  static async searchProductBySku(sku, { exact_match = false, business_id = null } = {}) {
    if (!sku || !sku.trim()) {
      throw new Error('SKU is required');
    }

    if (!business_id) {
      business_id = this.getActiveIds().business_id;
    }

    const params = new URLSearchParams({ 
      sku: sku.trim(),
      exact_match: exact_match.toString()
    });
    
    if (business_id) {
      params.set('business_id', business_id);
    }

    const url = `${API_ENDPOINTS.BASE_URL}/management/products/search-by-sku/?${params.toString()}`;
    
    try {
      console.debug('[PurchasesService.searchProductBySku] GET', url);
      const resp = await fetch(url, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
      });
      
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        console.error('[PurchasesService.searchProductBySku] Failed', { status: resp.status, url, data });
        const message = data?.error || resp.statusText || 'Request failed';
        throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
      }
      
      return data; // {message, sku_searched, exact_match, business_id, results_count, results}
    } catch (err) {
      console.error('[PurchasesService.searchProductBySku] Error', err);
      throw err;
    }
  }
}
