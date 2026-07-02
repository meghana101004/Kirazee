import React, { useState, useEffect } from 'react';
import AdminService from '../../../services/adminService';
import { 
  FaFileAlt, FaDownload, FaCalendar, FaChartBar, FaSpinner,
  FaMoneyBillWave, FaShoppingCart, FaUsers, FaStore
} from 'react-icons/fa';
import { MdRefresh } from 'react-icons/md';

const ReportsSection = () => {
  const [reportType, setReportType] = useState('revenue');
  const [dateRange, setDateRange] = useState('this_month');
  const [customDateFrom, setCustomDateFrom] = useState('');
  const [customDateTo, setCustomDateTo] = useState('');
  const [reportData, setReportData] = useState(null);
  const [businessesData, setBusinessesData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    generateReport();
  }, [reportType, dateRange]);

  const generateReport = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch data based on report type
      const [snapshot, summary, businesses] = await Promise.all([
        AdminService.getDashboardSnapshot(),
        AdminService.getDashboardSummary(),
        AdminService.getBusinessesComprehensive({ limit: 100 })
      ]);

      if (snapshot.success && summary.success) {
        setReportData({
          snapshot: snapshot.data,
          summary: summary
        });
      }

      if (businesses.success) {
        setBusinessesData(businesses.businesses || []);
      }
    } catch (error) {
      console.error('Error generating report:', error);
      setError('Failed to generate report');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(amount || 0);
  };

  const formatNumber = (num) => {
    return new Intl.NumberFormat('en-IN').format(num || 0);
  };

  const exportToPDF = () => {
    try {
      // Create a printable version of the report
      const printWindow = window.open('', '_blank');
      const reportTitle = `${reportType.charAt(0).toUpperCase() + reportType.slice(1)} Report - ${dateRange}`;
      
      let tableHTML = '';
      
      if (reportType === 'revenue' && reportData) {
        const revenueMetrics = reportData.summary?.revenue_metrics || {};
        tableHTML = `
          <h2>Revenue Summary</h2>
          <table border="1" cellpadding="10" cellspacing="0" style="width: 100%; border-collapse: collapse;">
            <thead>
              <tr style="background-color: #f0f0f0;">
                <th>Business Name</th>
                <th>Revenue</th>
                <th>Orders</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              ${businessesData.slice(0, 20).map(business => `
                <tr>
                  <td>${business.businessName || 'N/A'}</td>
                  <td>${formatCurrency(business.analytics?.total_revenue || 0)}</td>
                  <td>${business.analytics?.total_orders || 0}</td>
                  <td>${business.status || 'N/A'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      } else if (reportType === 'orders' && reportData) {
        tableHTML = `
          <h2>Orders Summary</h2>
          <table border="1" cellpadding="10" cellspacing="0" style="width: 100%; border-collapse: collapse;">
            <thead>
              <tr style="background-color: #f0f0f0;">
                <th>Business Name</th>
                <th>Total Orders</th>
                <th>Completed Orders</th>
                <th>Completion Rate</th>
              </tr>
            </thead>
            <tbody>
              ${businessesData.slice(0, 20).map(business => `
                <tr>
                  <td>${business.businessName || 'N/A'}</td>
                  <td>${business.analytics?.total_orders || 0}</td>
                  <td>${business.analytics?.completed_orders || 0}</td>
                  <td>${business.analytics?.completion_rate || 0}%</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }
      
      printWindow.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
          <title>${reportTitle}</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 20px; }
            h1 { color: #333; }
            h2 { color: #666; margin-top: 30px; }
            table { margin-top: 20px; }
            th { text-align: left; }
            @media print {
              button { display: none; }
            }
          </style>
        </head>
        <body>
          <h1>${reportTitle}</h1>
          <p>Generated on: ${new Date().toLocaleString()}</p>
          ${tableHTML}
          <br><br>
          <button onclick="window.print()">Print / Save as PDF</button>
        </body>
        </html>
      `);
      printWindow.document.close();
    } catch (error) {
      console.error('Error exporting to PDF:', error);
      alert('Failed to export PDF. Please try again.');
    }
  };

  const exportToExcel = () => {
    try {
      let csvContent = '';
      const reportTitle = `${reportType.charAt(0).toUpperCase() + reportType.slice(1)} Report - ${dateRange}\n`;
      const timestamp = `Generated on: ${new Date().toLocaleString()}\n\n`;
      
      if (reportType === 'revenue' && reportData) {
        csvContent = reportTitle + timestamp;
        csvContent += 'Business Name,Revenue,Orders,Status\n';
        
        businessesData.slice(0, 50).forEach(business => {
          csvContent += `"${business.businessName || 'N/A'}",`;
          csvContent += `"${business.analytics?.total_revenue || 0}",`;
          csvContent += `"${business.analytics?.total_orders || 0}",`;
          csvContent += `"${business.status || 'N/A'}"\n`;
        });
      } else if (reportType === 'orders' && reportData) {
        csvContent = reportTitle + timestamp;
        csvContent += 'Business Name,Total Orders,Completed Orders,Completion Rate\n';
        
        businessesData.slice(0, 50).forEach(business => {
          csvContent += `"${business.businessName || 'N/A'}",`;
          csvContent += `"${business.analytics?.total_orders || 0}",`;
          csvContent += `"${business.analytics?.completed_orders || 0}",`;
          csvContent += `"${business.analytics?.completion_rate || 0}%"\n`;
        });
      } else if (reportType === 'customers' && reportData) {
        csvContent = reportTitle + timestamp;
        csvContent += 'Metric,Value\n';
        const customers = reportData.snapshot?.customers || {};
        csvContent += `"Total Users","${customers.total_users || 0}"\n`;
        csvContent += `"Active Users","${customers.active_users || 0}"\n`;
        csvContent += `"Unique Customers","${customers.unique_customers || 0}"\n`;
      } else if (reportType === 'business' && reportData) {
        csvContent = reportTitle + timestamp;
        csvContent += 'Business Name,Type,Status,City,Total Orders,Total Revenue\n';
        
        businessesData.slice(0, 50).forEach(business => {
          csvContent += `"${business.businessName || 'N/A'}",`;
          csvContent += `"${business.business_type_name || 'N/A'}",`;
          csvContent += `"${business.status || 'N/A'}",`;
          csvContent += `"${business.city || 'N/A'}",`;
          csvContent += `"${business.analytics?.total_orders || 0}",`;
          csvContent += `"${business.analytics?.total_revenue || 0}"\n`;
        });
      }
      
      // Create blob and download
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      
      link.setAttribute('href', url);
      link.setAttribute('download', `${reportType}_report_${Date.now()}.csv`);
      link.style.visibility = 'hidden';
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error('Error exporting to Excel:', error);
      alert('Failed to export Excel. Please try again.');
    }
  };

  const exportReport = (format) => {
    if (format === 'pdf') {
      exportToPDF();
    } else if (format === 'excel') {
      exportToExcel();
    }
  };

  const renderRevenueReport = () => {
    if (!reportData) return null;

    const revenue = reportData.snapshot?.revenue || {};
    const revenueMetrics = reportData.summary?.revenue_metrics || {};

    // Sort businesses by revenue
    const sortedBusinesses = [...businessesData]
      .filter(b => b.analytics && b.analytics.total_revenue > 0)
      .sort((a, b) => (b.analytics?.total_revenue || 0) - (a.analytics?.total_revenue || 0))
      .slice(0, 15);

    return (
      <div className="report-content">
        <div className="report-summary">
          <h3>Revenue Summary</h3>
          <div className="summary-cards">
            <div className="summary-card">
              <FaMoneyBillWave className="card-icon" />
              <div className="card-info">
                <span className="card-label">Total Revenue</span>
                <span className="card-value">{formatCurrency(revenue.total_revenue)}</span>
              </div>
            </div>
            <div className="summary-card">
              <FaChartBar className="card-icon" />
              <div className="card-info">
                <span className="card-label">Average Order Value</span>
                <span className="card-value">{formatCurrency(revenue.average_order_value)}</span>
              </div>
            </div>
            <div className="summary-card">
              <FaShoppingCart className="card-icon" />
              <div className="card-info">
                <span className="card-label">Total Orders</span>
                <span className="card-value">{formatNumber(reportData.snapshot?.orders?.total_orders || 0)}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="report-table">
          <h4>Top Revenue Generating Businesses</h4>
          <table>
            <thead>
              <tr>
                <th>Business Name</th>
                <th>Revenue</th>
                <th>Orders</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedBusinesses.length > 0 ? (
                sortedBusinesses.map((business, index) => (
                  <tr key={index}>
                    <td>{business.businessName}</td>
                    <td>{formatCurrency(business.analytics?.total_revenue || 0)}</td>
                    <td>{formatNumber(business.analytics?.total_orders || 0)}</td>
                    <td>
                      <span className={`status-badge ${business.status?.toLowerCase()}`}>
                        {business.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="4" style={{ textAlign: 'center' }}>No revenue data available</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderOrdersReport = () => {
    if (!reportData) return null;

    const orders = reportData.snapshot?.orders || {};
    const orderMetrics = reportData.summary?.order_metrics || {};

    // Sort businesses by order count
    const sortedBusinesses = [...businessesData]
      .filter(b => b.analytics && b.analytics.total_orders > 0)
      .sort((a, b) => (b.analytics?.total_orders || 0) - (a.analytics?.total_orders || 0))
      .slice(0, 15);

    return (
      <div className="report-content">
        <div className="report-summary">
          <h3>Orders Summary</h3>
          <div className="summary-cards">
            <div className="summary-card">
              <FaShoppingCart className="card-icon" />
              <div className="card-info">
                <span className="card-label">Total Orders</span>
                <span className="card-value">{formatNumber(orders.total_orders || 0)}</span>
              </div>
            </div>
            <div className="summary-card">
              <FaChartBar className="card-icon success" />
              <div className="card-info">
                <span className="card-label">Completed Orders</span>
                <span className="card-value">{formatNumber(orders.completed_orders || 0)}</span>
              </div>
            </div>
            <div className="summary-card">
              <FaChartBar className="card-icon warning" />
              <div className="card-info">
                <span className="card-label">Active Orders</span>
                <span className="card-value">{formatNumber(orders.active_orders || 0)}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="report-table">
          <h4>Top Businesses by Order Volume</h4>
          <table>
            <thead>
              <tr>
                <th>Business Name</th>
                <th>Total Orders</th>
                <th>Completed</th>
                <th>Completion Rate</th>
              </tr>
            </thead>
            <tbody>
              {sortedBusinesses.length > 0 ? (
                sortedBusinesses.map((business, index) => (
                  <tr key={index}>
                    <td>{business.businessName}</td>
                    <td>{formatNumber(business.analytics?.total_orders || 0)}</td>
                    <td>{formatNumber(business.analytics?.completed_orders || 0)}</td>
                    <td>{business.analytics?.completion_rate || 0}%</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="4" style={{ textAlign: 'center' }}>No order data available</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderCustomersReport = () => {
    if (!reportData) return null;

    const customers = reportData.snapshot?.customers || {};

    return (
      <div className="report-content">
        <div className="report-summary">
          <h3>Customers Summary</h3>
          <div className="summary-cards">
            <div className="summary-card">
              <FaUsers className="card-icon" />
              <div className="card-info">
                <span className="card-label">Total Users</span>
                <span className="card-value">{customers.total_users || 0}</span>
              </div>
            </div>
            <div className="summary-card">
              <FaUsers className="card-icon success" />
              <div className="card-info">
                <span className="card-label">Active Users</span>
                <span className="card-value">{customers.active_users || 0}</span>
              </div>
            </div>
            <div className="summary-card">
              <FaUsers className="card-icon" />
              <div className="card-info">
                <span className="card-label">Unique Customers</span>
                <span className="card-value">{customers.unique_customers || 0}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderBusinessReport = () => {
    if (!reportData) return null;

    const businesses = reportData.snapshot?.businesses || {};

    return (
      <div className="report-content">
        <div className="report-summary">
          <h3>Business Summary</h3>
          <div className="summary-cards">
            <div className="summary-card">
              <FaStore className="card-icon" />
              <div className="card-info">
                <span className="card-label">Total Businesses</span>
                <span className="card-value">{formatNumber(businesses.total_businesses || 0)}</span>
              </div>
            </div>
            <div className="summary-card">
              <FaStore className="card-icon success" />
              <div className="card-info">
                <span className="card-label">Active Businesses</span>
                <span className="card-value">{formatNumber(businesses.active_businesses || 0)}</span>
              </div>
            </div>
            <div className="summary-card">
              <FaStore className="card-icon" />
              <div className="card-info">
                <span className="card-label">Paid Businesses</span>
                <span className="card-value">{formatNumber(businesses.paid_businesses || 0)}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="report-table">
          <h4>Business Performance Overview</h4>
          <table>
            <thead>
              <tr>
                <th>Business Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Total Orders</th>
                <th>Total Revenue</th>
              </tr>
            </thead>
            <tbody>
              {businessesData.slice(0, 15).map((business, index) => (
                <tr key={index}>
                  <td>{business.businessName}</td>
                  <td>{business.business_type_name || 'N/A'}</td>
                  <td>
                    <span className={`status-badge ${business.status?.toLowerCase()}`}>
                      {business.status}
                    </span>
                  </td>
                  <td>{formatNumber(business.analytics?.total_orders || 0)}</td>
                  <td>{formatCurrency(business.analytics?.total_revenue || 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="reports-section">
      {/* Header */}
      <div className="reports-header">
        <div className="header-left">
          <h2>
            <FaFileAlt /> Reports & Analytics
          </h2>
          <p>Generate and export detailed reports</p>
        </div>
        <button onClick={generateReport} className="refresh-btn" disabled={loading}>
          <MdRefresh className={loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      {/* Report Controls */}
      <div className="report-controls">
        <div className="control-group">
          <label>Report Type:</label>
          <select value={reportType} onChange={(e) => setReportType(e.target.value)}>
            <option value="revenue">Revenue Report</option>
            <option value="orders">Orders Report</option>
            <option value="customers">Customers Report</option>
            <option value="business">Business Report</option>
          </select>
        </div>

        <div className="control-group">
          <label>Date Range:</label>
          <select value={dateRange} onChange={(e) => setDateRange(e.target.value)}>
            <option value="today">Today</option>
            <option value="this_week">This Week</option>
            <option value="this_month">This Month</option>
            <option value="last_month">Last Month</option>
            <option value="this_year">This Year</option>
            <option value="custom">Custom Range</option>
          </select>
        </div>

        {dateRange === 'custom' && (
          <>
            <div className="control-group">
              <label>From:</label>
              <input
                type="date"
                value={customDateFrom}
                onChange={(e) => setCustomDateFrom(e.target.value)}
              />
            </div>
            <div className="control-group">
              <label>To:</label>
              <input
                type="date"
                value={customDateTo}
                onChange={(e) => setCustomDateTo(e.target.value)}
              />
            </div>
          </>
        )}

        <div className="export-buttons">
          <button className="export-btn" onClick={() => exportReport('pdf')}>
            <FaDownload /> Export PDF
          </button>
          <button className="export-btn" onClick={() => exportReport('excel')}>
            <FaDownload /> Export Excel
          </button>
        </div>
      </div>

      {/* Report Content */}
      {loading ? (
        <div className="reports-loading">
          <FaSpinner className="loading-spinner" />
          <p>Generating report...</p>
        </div>
      ) : error ? (
        <div className="reports-error">
          <p>{error}</p>
        </div>
      ) : (
        <>
          {reportType === 'revenue' && renderRevenueReport()}
          {reportType === 'orders' && renderOrdersReport()}
          {reportType === 'customers' && renderCustomersReport()}
          {reportType === 'business' && renderBusinessReport()}
        </>
      )}
    </div>
  );
};

export default ReportsSection;
