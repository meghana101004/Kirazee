# Package init for consumer.utils
import json
from django.conf import settings

def parse_json_input(input_data, default=None):
    """Parse JSON input safely with fallback to default value."""
    if not input_data:
        return default
    try:
        if isinstance(input_data, str):
            return json.loads(input_data)
        return input_data
    except Exception:
        return default

def build_absolute_url(request, path):
    """Build absolute URL for media files."""
    if not path:
        return None
    
    # Convert ImageFieldFile to string if needed
    if hasattr(path, 'name'):
        path = path.name
    else:
        path = str(path)
    
    if path.startswith('http'):
        return path
    
    # Clean up the path
    clean_path = path.lstrip('/')
    # Handle kirazee media structure
    if not clean_path.startswith('kirazee/'):
        clean_path = f"kirazee/{clean_path}"
    
    return request.build_absolute_uri(f"/{clean_path}")
