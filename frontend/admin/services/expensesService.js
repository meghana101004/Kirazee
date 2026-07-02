import { API_ENDPOINTS } from '../utils/config';
import { AuthService } from './authService';

export class ExpensesService {
  static getActiveIds() {
    const user = AuthService.getUserData();
    const user_id = user?.user_id;

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

  static async createExpense(payload, user_id, business_id) {
    if (!user_id || !business_id) {
      const ids = this.getActiveIds();
      user_id = user_id || ids.user_id;
      business_id = business_id || ids.business_id;
    }

    if (!user_id || !business_id) {
      throw new Error('Missing user_id or business_id');
    }

    const url = `${API_ENDPOINTS.BASE_URL}/management/expenses/create/?user_id=${encodeURIComponent(
      user_id
    )}&business_id=${encodeURIComponent(business_id)}`;

    // If a File object is present, use FormData (multipart)
    const hasFile = payload && (payload.receipt_file instanceof File || payload.receipt_file instanceof Blob);

    let fetchOptions;
    if (hasFile) {
      const form = new FormData();
      Object.entries(payload).forEach(([k, v]) => {
        if (v === undefined || v === null) return;
        if (k === 'receipt_file' && (v instanceof File || v instanceof Blob)) {
          form.append('receipt_file', v);
        } else {
          form.append(k, String(v));
        }
      });
      fetchOptions = { method: 'POST', body: form };
    } else {
      fetchOptions = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      };
    }

    const resp = await fetch(url, fetchOptions);

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const message = data?.error || resp.statusText || 'Request failed';
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data; // { message, expense }
  }

  static async getExpensesByBusiness(business_id, { limit = 50, offset = 0, ...filters } = {}) {
    if (!business_id) {
      business_id = this.getActiveIds().business_id;
    }
    if (!business_id) throw new Error('Missing business_id');

    const params = new URLSearchParams({ business_id, limit: String(limit), offset: String(offset) });
    if (filters.user_id) params.set('user_id', filters.user_id);
    if (filters.supplier_id) params.set('supplier_id', String(filters.supplier_id));
    if (filters.payment_status) params.set('payment_status', filters.payment_status);
    if (filters.start_date) params.set('start_date', filters.start_date);
    if (filters.end_date) params.set('end_date', filters.end_date);
    if (filters.search) params.set('search', filters.search);

    const url = `${API_ENDPOINTS.BASE_URL}/management/expenses/?${params.toString()}`;
    const resp = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const message = data?.error || resp.statusText || 'Request failed';
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data; // { expenses, count, business_id, filters }
  }

  static async updateExpense(expense_id, payload, user_id, business_id) {
    if (!expense_id) throw new Error('Missing expense_id');
    if (!user_id || !business_id) {
      const ids = this.getActiveIds();
      user_id = user_id || ids.user_id;
      business_id = business_id || ids.business_id;
    }
    if (!user_id || !business_id) throw new Error('Missing user_id or business_id');

    const url = `${API_ENDPOINTS.BASE_URL}/management/expenses/${encodeURIComponent(expense_id)}/update/?user_id=${encodeURIComponent(user_id)}&business_id=${encodeURIComponent(business_id)}`;
    const resp = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const message = data?.error || resp.statusText || 'Request failed';
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data; // { message, expense }
  }

  static async deleteExpense(expense_id, { reason } = {}, user_id, business_id) {
    if (!expense_id) throw new Error('Missing expense_id');
    if (!user_id || !business_id) {
      const ids = this.getActiveIds();
      user_id = user_id || ids.user_id;
      business_id = business_id || ids.business_id;
    }
    if (!user_id || !business_id) throw new Error('Missing user_id or business_id');

    const params = new URLSearchParams({ user_id, business_id });
    if (reason) params.set('reason', reason);
    const url = `${API_ENDPOINTS.BASE_URL}/management/expenses/${encodeURIComponent(expense_id)}/delete/?${params.toString()}`;
    const resp = await fetch(url, { method: 'DELETE', headers: { 'Content-Type': 'application/json' } });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const message = data?.error || resp.statusText || 'Request failed';
      throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
    }
    return data; // { message, deleted_expense }
  }
}
