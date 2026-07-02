#!/usr/bin/env python3
"""
Test script for Payment Detail Reports API
Demonstrates various usage scenarios and expected responses
"""

import requests
import json
from datetime import datetime, timedelta

# Configuration
BASE_URL = "http://localhost:8000/api/v1/management"
BUSINESS_ID = "KIR1478820251021185505"  # Example business ID

def test_daily_report():
    """Test daily payment report"""
    print("=== Testing Daily Report ===")
    url = f"{BASE_URL}/reports/payment-details/"
    params = {
        "business_id": BUSINESS_ID,
        "period_type": "daily"
    }
    
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Total Orders: {data['metadata']['total_orders']}")
            print(f"Grand Total: ₹{data['summary']['grand_total']:,.2f}")
            print(f"Period: {data['metadata']['start_date']} to {data['metadata']['end_date']}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

def test_monthly_csv_export():
    """Test monthly report with CSV export"""
    print("=== Testing Monthly CSV Export ===")
    url = f"{BASE_URL}/reports/payment-details/"
    params = {
        "business_id": BUSINESS_ID,
        "period_type": "monthly",
        "export_format": "csv"
    }
    
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            # Save CSV file
            filename = f"payment_details_{BUSINESS_ID}_monthly.csv"
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"CSV exported to: {filename}")
            print(f"File size: {len(response.content)} bytes")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

def test_custom_date_range():
    """Test custom date range report"""
    print("=== Testing Custom Date Range ===")
    
    # Last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    url = f"{BASE_URL}/reports/payment-details/"
    params = {
        "business_id": BUSINESS_ID,
        "period_type": "custom",
        "from_date": start_date.strftime('%Y-%m-%d'),
        "to_date": end_date.strftime('%Y-%m-%d')
    }
    
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Date Range: {data['metadata']['start_date']} to {data['metadata']['end_date']}")
            print(f"Payment Methods Breakdown:")
            for method, stats in data['summary']['payment_methods_breakdown'].items():
                if stats['count'] > 0:
                    print(f"  {method}: {stats['count']} orders, ₹{stats['amount']:,.2f}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

def test_quarterly_report():
    """Test quarterly report with branches"""
    print("=== Testing Quarterly Report with Branches ===")
    url = f"{BASE_URL}/reports/payment-details/"
    params = {
        "business_id": BUSINESS_ID,
        "period_type": "quarterly",
        "include_branches": "true"
    }
    
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Included Businesses: {data['metadata']['included_business_ids']}")
            print(f"Source Breakdown:")
            for source, stats in data['summary']['source_breakdown'].items():
                print(f"  {source}: {stats['count']} orders, ₹{stats['amount']:,.2f}")
            print(f"Platform Breakdown:")
            for platform, stats in data['summary']['platform_breakdown'].items():
                if stats['count'] > 0:
                    print(f"  {platform}: {stats['count']} orders, ₹{stats['amount']:,.2f}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

def analyze_payment_patterns():
    """Analyze payment patterns from the data"""
    print("=== Payment Pattern Analysis ===")
    url = f"{BASE_URL}/reports/payment-details/"
    params = {
        "business_id": BUSINESS_ID,
        "period_type": "monthly"
    }
    
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            summary = data['summary']
            
            # Calculate percentages
            total = summary['grand_total']
            if total > 0:
                print("Payment Method Distribution:")
                for method, stats in summary['payment_methods_breakdown'].items():
                    if stats['amount'] > 0:
                        percentage = (stats['amount'] / total) * 100
                        print(f"  {method}: ₹{stats['amount']:,.2f} ({percentage:.1f}%)")
            
            # Source analysis
            counter = summary['source_breakdown']['counter_orders']
            online = summary['source_breakdown']['online_orders']
            total_orders = counter['count'] + online['count']
            
            if total_orders > 0:
                print(f"\nOrder Source Distribution:")
                print(f"  Counter Orders: {counter['count']} ({counter['count']/total_orders*100:.1f}%)")
                print(f"  Online Orders: {online['count']} ({online['count']/total_orders*100:.1f}%)")
            
            # Success rate
            success = summary['status_breakdown']['success']['count']
            total_status = sum(stats['count'] for stats in summary['status_breakdown'].values())
            if total_status > 0:
                success_rate = (success / total_status) * 100
                print(f"\nPayment Success Rate: {success_rate:.1f}%")
                
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")
    print()

def demonstrate_api_features():
    """Demonstrate all API features"""
    print("Payment Detail Reports API - Feature Demonstration")
    print("=" * 50)
    
    # Run all test scenarios
    test_daily_report()
    test_monthly_csv_export()
    test_custom_date_range()
    test_quarterly_report()
    analyze_payment_patterns()
    
    print("API Demonstration Complete!")
    print("\nKey Features Demonstrated:")
    print("✓ Daily, monthly, quarterly, and custom date ranges")
    print("✓ JSON and CSV export formats")
    print("✓ Payment method categorization")
    print("✓ Source and platform breakdown")
    print("✓ Business hierarchy support")
    print("✓ Comprehensive summary statistics")

if __name__ == "__main__":
    # Note: This script requires the Django server to be running
    # and the requests library to be installed (pip install requests)
    
    print("Payment Detail Reports API Test Script")
    print("Make sure Django server is running on http://localhost:8000")
    print("Press Enter to continue or Ctrl+C to exit...")
    
    try:
        input()
        demonstrate_api_features()
    except KeyboardInterrupt:
        print("\nTest cancelled by user")
