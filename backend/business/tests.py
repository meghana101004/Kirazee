import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the project root to Python path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

# Now set up Django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kirazee.settings')
import django
django.setup()

from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from business.views import parse_address_from_maps

def test_parse_address_from_maps():
    # Create a test request
    factory = APIRequestFactory()
    request = factory.post(
        '/business/parse-address/',
        {'maps_url': 'https://www.google.com/maps/place/Taj+Mahal/@27.1750151,78.0421552,17z/'},
        format='json'
    )
    
    # Mock the parse_google_maps_url function
    mock_address_data = {
        'address': '123 Taj Road',
        'city': 'Agra',
        'state': 'Uttar Pradesh',
        'pincode': '282001',
        'country': 'India',
        'latitude': 27.1750151,
        'longitude': 78.0421552,
        'formatted_address': 'Taj Mahal, Dharmapuri Forest Colony, Tajganj, Agra, Uttar Pradesh 282001, India'
    }
    
    with patch('business.views.parse_google_maps_url') as mock_parse:
        # Configure the mock to return our test data
        mock_parse.return_value = mock_address_data
        
        # Call the view
        response = parse_address_from_maps(request)
        
        # Check the response
        print("Status Code:", response.status_code)
        print("Response:", response.data)
        
        # Assert the response data
        assert response.status_code == 200
        data = response.data
        assert data['address'] == '123 Taj Road'
        assert data['city'] == 'Agra'
        assert data['state'] == 'Uttar Pradesh'
        assert data['pincode'] == '282001'
        assert data['country'] == 'India'
        assert data['latitude'] == 27.1750151
        assert data['longitude'] == 78.0421552
        assert 'Taj Mahal' in data['formatted_address']

if __name__ == "__main__":
    test_parse_address_from_maps()