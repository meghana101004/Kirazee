# utils/google_maps.py
import re
import requests
from urllib.parse import unquote
from django.conf import settings
import math

def parse_google_maps_url(maps_url):
    """
    Parse Google Maps URL to extract address components and coordinates
    Returns: dict with address components and coordinates
    """
    try:
        # Handle mobile/desktop URLs and extract the place ID or coordinates
        place_id_match = re.search(r'place/([^/]+)/', maps_url)
        coords_match = re.search(r'@([-+]?[0-9]*\.?[0-9]+),([-+]?[0-9]*\.?[0-9]+)', maps_url)
        
        if place_id_match:
            # Use Google Places API to get details
            place_id = place_id_match.group(1).split('/')[0].split(',')[0]
            return get_place_details(place_id)
        elif coords_match:
            # Extract coordinates directly from URL
            lat, lng = map(float, coords_match.groups())
            return reverse_geocode(lat, lng)
        else:
            return {'error': 'Invalid Google Maps URL format'}
    except Exception as e:
        print(f"Error parsing Google Maps URL: {e}")
        return {'error': str(e)}

def get_place_details(place_id):
    """Get place details using Google Places API"""
    if not hasattr(settings, 'GOOGLE_MAPS_API_KEY'):
        return {'error': 'Google Maps API key not configured'}
        
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&key={settings.GOOGLE_MAPS_API_KEY}"
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'OK':
            return {'error': data.get('error_message', 'Failed to fetch place details')}
            
        result = data.get('result', {})
        address_components = result.get('address_components', [])
        
        # Parse address components
        address_data = {
            'formatted_address': result.get('formatted_address', ''),
            'latitude': result.get('geometry', {}).get('location', {}).get('lat'),
            'longitude': result.get('geometry', {}).get('location', {}).get('lng'),
        }
        
        # Map address components to fields
        address_data.update(parse_address_components(address_components))
        return address_data
        
    except requests.exceptions.RequestException as e:
        return {'error': f'API request failed: {str(e)}'}
    except Exception as e:
        return {'error': f'Error processing place details: {str(e)}'}

def reverse_geocode(lat, lng):
    """Reverse geocode coordinates to get address"""
    if not hasattr(settings, 'GOOGLE_MAPS_API_KEY'):
        return {'error': 'Google Maps API key not configured'}
        
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={settings.GOOGLE_MAPS_API_KEY}"
    
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'OK':
            return {'error': data.get('error_message', 'Failed to fetch address')}
            
        result = data.get('results', [{}])[0]
        address_components = result.get('address_components', [])
        
        return {
            'formatted_address': result.get('formatted_address', ''),
            'latitude': lat,
            'longitude': lng,
            **parse_address_components(address_components)
        }
        
    except requests.exceptions.RequestException as e:
        return {'error': f'API request failed: {str(e)}'}
    except Exception as e:
        return {'error': f'Error in reverse geocoding: {str(e)}'}

def parse_address_components(components):
    """Helper to parse address components from Google's response"""
    data = {}
    for component in components:
        types = component.get('types', [])
        if 'street_number' in types:
            data['street_number'] = component.get('long_name')
        elif 'route' in types:
            data['route'] = component.get('long_name')
        elif 'sublocality_level_1' in types or 'sublocality' in types:
            data['sublocality'] = component.get('long_name')
        elif 'locality' in types:
            data['city'] = component.get('long_name')
        elif 'administrative_area_level_1' in types:
            data['state'] = component.get('long_name')
        elif 'postal_code' in types:
            data['pincode'] = component.get('long_name')
        elif 'country' in types:
            data['country'] = component.get('long_name')
    
    # Combine street number and route for full address
    street_parts = []
    if 'street_number' in data:
        street_parts.append(data.pop('street_number'))
    if 'route' in data:
        street_parts.append(data.pop('route'))
    if street_parts:
        data['address'] = ' '.join(street_parts)
    
    return data

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_route_and_eta(*args, mode='driving'):
    """
    Compute route distance and ETA between origin and destination.
    Supports both signatures:
      - get_route_and_eta(origin_lat, origin_lng, dest_lat, dest_lng, mode='driving')
      - get_route_and_eta((origin_lat, origin_lng), (dest_lat, dest_lng), mode='driving')

    Returns dict: { distance_km, duration_minutes, distance_text, duration_text, mode }
    Uses Google Distance Matrix API if GOOGLE_MAPS_API_KEY is configured, else haversine fallback.
    """
    try:
        # Parse arguments
        if len(args) == 4:
            o_lat, o_lng, d_lat, d_lng = map(float, args)
        elif len(args) == 2:
            origin, dest = args
            if isinstance(origin, (list, tuple)) and isinstance(dest, (list, tuple)):
                o_lat, o_lng = map(float, origin)
                d_lat, d_lng = map(float, dest)
            elif isinstance(origin, dict) and isinstance(dest, dict):
                o_lat, o_lng = float(origin['lat']), float(origin['lng'])
                d_lat, d_lng = float(dest['lat']), float(dest['lng'])
            else:
                return {"error": "Invalid arguments for get_route_and_eta"}
        else:
            return {"error": "Invalid number of arguments for get_route_and_eta"}

        # Prefer Google Distance Matrix API if key is available
        api_key = getattr(settings, 'GOOGLE_MAPS_API_KEY', None)
        if api_key:
            url = (
                "https://maps.googleapis.com/maps/api/distancematrix/json"
                f"?origins={o_lat},{o_lng}&destinations={d_lat},{d_lng}&mode={mode}&key={api_key}"
            )
            try:
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                data = resp.json()
                if data.get('status') == 'OK':
                    rows = data.get('rows', [])
                    if rows and rows[0].get('elements'):
                        el = rows[0]['elements'][0]
                        if el.get('status') == 'OK':
                            dist_m = el['distance']['value']
                            dur_s = el['duration']['value']
                            dist_km = round(dist_m / 1000.0, 2)
                            dur_min = int(round(dur_s / 60.0))
                            return {
                                'distance_km': dist_km,
                                'duration_minutes': dur_min,
                                'distance_text': el['distance'].get('text'),
                                'duration_text': el['duration'].get('text'),
                                'mode': mode
                            }
                # Fall through to fallback on non-OK
            except requests.exceptions.RequestException:
                pass

        # Fallback: straight-line distance and rough ETA by average speed
        dist_km = round(_haversine_km(o_lat, o_lng, d_lat, d_lng), 2)
        # Rough average speeds (km/h)
        avg_speeds = {
            'driving': 30.0,
            'walking': 5.0,
            'bicycling': 15.0,
            'transit': 25.0,
        }
        speed = avg_speeds.get(mode, 30.0)
        dur_min = int(round((dist_km / speed) * 60)) if speed > 0 else None
        return {
            'distance_km': dist_km,
            'duration_minutes': dur_min,
            'distance_text': f"{dist_km} km",
            'duration_text': f"{dur_min} mins" if dur_min is not None else None,
            'mode': mode
        }
    except Exception as e:
        return {"error": str(e)}