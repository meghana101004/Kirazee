"""
Image Utilities Module for S3-based Image Handling
Provides centralized functions for CRUD operations on images with S3 support.

Usage:
    from business.image_utils import (
        build_s3_file_url,
        build_s3_image_url_field,
        process_uploaded_image,
        ImageCRUDMixin
    )
"""

import os
import io
import time
from typing import Optional, Dict, Any, List, Union
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image
import hashlib
import uuid


# =============================================================================
# S3 URL BUILDERS - Primary Functions for URL Conversion
# =============================================================================

def build_s3_file_url(file_path: Union[str, Any], bucket_name: Optional[str] = None,
                      region: Optional[str] = None, prefix: str = "prod/media") -> Optional[str]:
    """
    Build a direct S3 URL for a file.
    
    Args:
        file_path: File path (string) or FileField instance
        bucket_name: S3 bucket name (defaults to settings.AWS_STORAGE_BUCKET_NAME)
        region: AWS region (defaults to settings.AWS_S3_REGION_NAME or 'ap-south-1')
        prefix: S3 key prefix (default: 'prod/media')
    
    Returns:
        Full S3 URL or None if invalid
        
    Examples:
        >>> build_s3_file_url("logo.png")
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/logo.png'
        
        >>> build_s3_file_url(business.logo)
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/business/logos/logo.png'
    """
    if not file_path:
        return None

    bucket = bucket_name or getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
    reg = region or getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')

    if not bucket:
        # Fallback to local media URL if S3 not configured
        return _build_local_url(file_path)

    # Extract file name/path
    if hasattr(file_path, 'name'):
        path = file_path.name
    else:
        path = str(file_path)

    # Clean up the path
    path = path.lstrip('/')
    
    # Remove duplicate media/ prefix if present
    if path.startswith('media/'):
        path = path[6:]
    
    # Remove duplicate prefix if present
    if prefix and path.startswith(f"{prefix}/"):
        path = path[len(prefix) + 1:]

    # Build S3 URL
    s3_url = f"https://{bucket}.s3.{reg}.amazonaws.com/{prefix}/{path}"
    return s3_url.replace(' ', '%20')


def _build_local_url(file_path: Union[str, Any]) -> Optional[str]:
    """Build local media URL as fallback."""
    if not file_path:
        return None
    
    if hasattr(file_path, 'url'):
        return file_path.url
    
    path = str(file_path).lstrip('/')
    base_url = getattr(settings, 'BASE_URL', '')
    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    
    if base_url:
        return f"{base_url.rstrip('/')}{media_url}{path}"
    return f"{media_url}{path}"


def build_s3_image_url_field(obj: Any, field_name: str, 
                              bucket_name: Optional[str] = None,
                              region: Optional[str] = None) -> Optional[str]:
    """
    Build S3 URL for an object's image field.
    
    Args:
        obj: Model instance containing the image field
        field_name: Name of the image field (e.g., 'logo', 'banner', 'item_image')
        bucket_name: S3 bucket name
        region: AWS region
    
    Returns:
        Full S3 URL or None
        
    Example:
        >>> build_s3_image_url_field(business, 'logo')
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/business/logo.png'
    """
    field_value = getattr(obj, field_name, None)
    return build_s3_file_url(field_value, bucket_name, region)


# =============================================================================
# IMAGE PROCESSING - Compression & Duplication Prevention
# =============================================================================

MAX_IMAGE_SIZE = (1920, 1080)  # Max dimensions
JPEG_QUALITY = 85
WEBP_QUALITY = 85
MAX_FILE_SIZE_MB = 5


def compress_image(image_file: Any, output_format: str = 'JPEG',
                   quality: int = JPEG_QUALITY,
                   max_size: tuple = MAX_IMAGE_SIZE) -> ContentFile:
    """
    Compress an image file while maintaining aspect ratio.
    
    Args:
        image_file: Uploaded file object or path
        output_format: Output format (JPEG, PNG, WEBP)
        quality: Compression quality (1-100)
        max_size: Maximum (width, height) tuple
    
    Returns:
        Compressed image as ContentFile
    """
    # Open image
    if hasattr(image_file, 'seek'):
        image_file.seek(0)
        image = Image.open(image_file)
    else:
        image = Image.open(image_file)

    # Convert RGBA to RGB for JPEG
    if output_format == 'JPEG' and image.mode in ('RGBA', 'P'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background

    # Resize if larger than max_size
    if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

    # Save to buffer
    output = io.BytesIO()
    
    save_kwargs = {'quality': quality, 'optimize': True}
    if output_format == 'PNG':
        save_kwargs = {'optimize': True}
    elif output_format == 'WEBP':
        save_kwargs = {'quality': quality, 'method': 6}

    image.save(output, format=output_format, **save_kwargs)
    output.seek(0)

    # Generate filename
    original_name = getattr(image_file, 'name', 'image.jpg')
    ext = output_format.lower()
    base_name = os.path.splitext(original_name)[0]
    new_name = f"{base_name}.{ext}"

    return ContentFile(output.read(), name=new_name)


def get_file_hash(file_obj: Any) -> str:
    """
    Calculate MD5 hash of a file for duplicate detection.
    
    Args:
        file_obj: File object to hash
    
    Returns:
        MD5 hash string
    """
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    
    hasher = hashlib.md5()
    
    if hasattr(file_obj, 'chunks'):
        for chunk in file_obj.chunks():
            hasher.update(chunk)
    else:
        hasher.update(file_obj.read())
    
    if hasattr(file_obj, 'seek'):
        file_obj.seek(0)
    
    return hasher.hexdigest()


def check_duplicate_exists(file_hash: str, folder: str = "media") -> Optional[str]:
    """
    Check if a file with the same hash already exists in storage.
    
    Args:
        file_hash: MD5 hash of the file
        folder: Folder to check for duplicates
    
    Returns:
        Existing file path if found, None otherwise
    """
    # In S3 storage, we can't easily check duplicates without listing
    # This is a placeholder for custom implementation
    # You might want to store file hashes in a database table
    return None


def process_uploaded_image(image_file: Any, folder: str = "",
                           compress: bool = True,
                           check_duplicates: bool = False) -> Dict[str, Any]:
    """
    Process an uploaded image: compress, check duplicates, and prepare for storage.
    
    Args:
        image_file: The uploaded image file
        folder: Target folder (e.g., 'business', 'menuItems', 'products')
        compress: Whether to compress the image
        check_duplicates: Whether to check for duplicate files
    
    Returns:
        Dict with 'file', 'file_hash', 'is_duplicate', 'existing_path'
    """
    result = {
        'file': image_file,
        'file_hash': None,
        'is_duplicate': False,
        'existing_path': None,
        'original_name': getattr(image_file, 'name', 'unnamed')
    }

    # Calculate hash
    if check_duplicates:
        file_hash = get_file_hash(image_file)
        result['file_hash'] = file_hash
        
        existing = check_duplicate_exists(file_hash, folder)
        if existing:
            result['is_duplicate'] = True
            result['existing_path'] = existing
            return result

    # Compress if needed
    if compress:
        # Determine format based on extension
        ext = os.path.splitext(result['original_name'])[1].lower()
        if ext in ['.jpg', '.jpeg']:
            output_format = 'JPEG'
        elif ext == '.png':
            output_format = 'PNG'
        elif ext == '.webp':
            output_format = 'WEBP'
        else:
            output_format = 'JPEG'

        result['file'] = compress_image(image_file, output_format=output_format)

    return result


# =============================================================================
# SERIALIZER MIXIN - For easy integration with DRF Serializers
# =============================================================================

class ImageCRUDMixin:
    """
    Mixin for serializers that provides S3 image URL handling.
    
    Usage:
        class MySerializer(serializers.ModelSerializer, ImageCRUDMixin):
            image_url = serializers.SerializerMethodField()
            
            class Meta:
                model = MyModel
                fields = ['image', 'image_url']
            
            def get_image_url(self, obj):
                return self.get_s3_url(obj, 'image')
    """
    
    def get_s3_url(self, obj: Any, field_name: str, 
                   prefix: str = "prod/media") -> Optional[str]:
        """
        Get S3 URL for a model field.
        
        Args:
            obj: Model instance
            field_name: Name of the image field
            prefix: S3 prefix
        
        Returns:
            S3 URL or None
        """
        return build_s3_image_url_field(obj, field_name, prefix=prefix)
    
    def get_s3_url_list(self, obj: Any, field_name: str,
                        prefix: str = "prod/media") -> List[str]:
        """
        Get S3 URLs for a list of images (e.g., JSONField with multiple images).
        
        Args:
            obj: Model instance
            field_name: Name of the field containing image paths (list)
            prefix: S3 prefix
        
        Returns:
            List of S3 URLs
        """
        paths = getattr(obj, field_name, None)
        if not paths:
            return []
        
        if isinstance(paths, str):
            # Try to parse as JSON
            try:
                import json
                paths = json.loads(paths)
            except:
                paths = [paths]
        
        if not isinstance(paths, list):
            paths = [paths]
        
        urls = []
        for path in paths:
            url = build_s3_file_url(path, prefix=prefix)
            if url:
                urls.append(url)
        
        return urls
    
    def process_image_upload(self, validated_data: Dict, field_name: str,
                            folder: str = "", compress: bool = True) -> Dict:
        """
        Process an image upload during serializer create/update.
        
        Args:
            validated_data: The validated serializer data
            field_name: Name of the image field to process
            folder: Target folder for the image
            compress: Whether to compress the image
        
        Returns:
            Updated validated_data dict
        """
        image_file = validated_data.get(field_name)
        
        if not image_file:
            return validated_data
        
        result = process_uploaded_image(
            image_file,
            folder=folder,
            compress=compress,
            check_duplicates=False
        )
        
        if result['is_duplicate'] and result['existing_path']:
            # Use existing file path instead of saving new
            validated_data[field_name] = result['existing_path']
        else:
            validated_data[field_name] = result['file']
        
        return validated_data


# =============================================================================
# VIEW UTILITIES - Helper functions for views
# =============================================================================

def convert_response_urls_to_s3(data: Any, 
                                url_fields: List[str] = None,
                                prefix: str = "prod/media") -> Any:
    """
    Recursively convert all media URLs in response data to S3 URLs.
    
    Args:
        data: Response data (dict, list, or primitive)
        url_fields: Specific field names to convert (if None, auto-detect)
        prefix: S3 prefix
    
    Returns:
        Data with converted URLs
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            # Check if this is a URL field or contains URL-like values
            if url_fields and key in url_fields:
                result[key] = build_s3_file_url(value, prefix=prefix)
            elif isinstance(value, str) and ('/media/' in value or '/kirazee/media/' in value):
                result[key] = build_s3_file_url(value, prefix=prefix)
            else:
                result[key] = convert_response_urls_to_s3(value, url_fields, prefix)
        return result
    
    elif isinstance(data, list):
        return [convert_response_urls_to_s3(item, url_fields, prefix) for item in data]
    
    elif isinstance(data, str) and ('/media/' in data or '/kirazee/media/' in data):
        return build_s3_file_url(data, prefix=prefix)
    
    return data


def get_s3_presigned_url(file_path: str, expiration: int = 3600) -> Optional[str]:
    """
    Generate a presigned URL for private S3 objects.
    
    Args:
        file_path: Path to the file in S3
        expiration: URL expiration time in seconds (default: 1 hour)
    
    Returns:
        Presigned URL or None
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')
        )
        
        bucket = settings.AWS_STORAGE_BUCKET_NAME
        
        # Clean path
        file_path = file_path.lstrip('/')
        if file_path.startswith('media/'):
            file_path = f"dev/{file_path}"
        
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': file_path},
            ExpiresIn=expiration
        )
        return url
    except Exception:
        return None


# =============================================================================
# DECORATORS - Easy application to existing views
# =============================================================================

def s3_url_response(url_fields: List[str] = None, prefix: str = "prod/media"):
    """
    Decorator to automatically convert media URLs to S3 URLs in response.
    
    Usage:
        @api_view(['GET'])
        @s3_url_response(url_fields=['logo_url', 'banner_url'])
        def my_view(request):
            return Response({'logo_url': '/media/logo.png'})
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            response = func(*args, **kwargs)
            
            if hasattr(response, 'data'):
                response.data = convert_response_urls_to_s3(
                    response.data, url_fields, prefix
                )
            
            return response
        return wrapper
    return decorator


# =============================================================================
# UPLOAD HELPERS - For direct S3 uploads (without model.save)
# =============================================================================

def upload_image_to_s3(image_file: Any, folder: str, filename: str = None,
                       compress: bool = True, use_uuid: bool = True) -> Optional[str]:
    """
    Upload an image directly to S3 and return the stored path.
    
    This function compresses the image, generates a unique filename if needed,
    and saves directly to S3 using default_storage.
    
    Args:
        image_file: The uploaded file object (from request.FILES)
        folder: Target folder (e.g., 'business_logos', 'fashion_images', 'groceries_images')
        filename: Optional custom filename (without extension). If None, uses UUID by default
        compress: Whether to compress the image (default: True)
        use_uuid: Whether to use UUID for filename (default: True, uses secure UUID)
    
    Returns:
        Stored path like "media/folder/filename.jpg" or None on failure
        
    Example:
        >>> upload_image_to_s3(request.FILES['logo'], 'business_logos')
        'media/business_logos/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg'
        
        >>> upload_image_to_s3(request.FILES['image'], 'fashion_images')
        'media/fashion_images/f4e5d6c7-b8a9-0123-4567-89abcdef0123.jpg'
    """
    if not image_file:
        return None
    
    try:
        # Compress if needed
        file_to_save = image_file
        if compress:
            file_to_save = compress_image(image_file)
            if not file_to_save:
                print(f"[upload_image_to_s3] Compression failed for {getattr(image_file, 'name', 'unknown')}")
                return None
        
        # Generate filename
        if use_uuid:
            final_filename = f"{uuid.uuid4()}.jpg"
        elif filename:
            final_filename = f"{filename}.jpg"
        else:
            # Use original filename base
            orig_name = getattr(image_file, 'name', 'image.jpg')
            base_name = os.path.splitext(os.path.basename(orig_name))[0]
            timestamp = int(time.time())
            final_filename = f"{base_name}_{timestamp}.jpg"
        
        # Build full relative path
        rel_path = os.path.join(folder, final_filename).replace('\\', '/')
        
        # Save to S3 using default_storage
        saved_name = default_storage.save(rel_path, file_to_save)
        
        # Return path with media/ prefix for consistency
        if saved_name.startswith('media/'):
            return saved_name
        return f"media/{saved_name}"
        
    except Exception as e:
        print(f"[upload_image_to_s3] Error uploading image: {e}")
        import traceback
        traceback.print_exc()
        return None


def save_model_image_field(model_instance: Any, field_name: str, 
                           image_file: Any, folder: str,
                           compress: bool = True) -> Optional[str]:
    """
    Save image to a model's ImageField and return the S3 URL.
    
    This deletes the old image if it exists, then saves the new one.
    Uses model.field.save() which triggers S3 upload via default_storage.
    
    Args:
        model_instance: The model instance (e.g., Business object)
        field_name: Name of the ImageField (e.g., 'logo', 'banner')
        image_file: The uploaded file object
        folder: Target folder for S3 storage
        compress: Whether to compress before saving
    
    Returns:
        Full S3 URL of the saved image, or None on failure
        
    Example:
        >>> save_model_image_field(business, 'logo', request.FILES['logo'], 'business_logos')
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/business_logos/logo_123.jpg'
    """
    if not image_file or not model_instance:
        return None
    
    try:
        field = getattr(model_instance, field_name, None)
        
        # Delete old image if exists
        if field and hasattr(field, 'name') and field.name:
            try:
                field.delete(save=False)
                print(f"[save_model_image_field] Deleted old {field_name}")
            except Exception as e:
                print(f"[save_model_image_field] Failed to delete old {field_name}: {e}")
        
        # Compress if needed
        file_to_save = image_file
        if compress:
            file_to_save = compress_image(image_file)
            if not file_to_save:
                return None
        
        # Generate filename with timestamp and business/model identifier
        orig_name = getattr(image_file, 'name', 'image.jpg')
        base_name = os.path.splitext(os.path.basename(orig_name))[0]
        timestamp = int(time.time())
        
        # Include model identifier if available
        model_id = getattr(model_instance, 'business_id', None) or \
                   getattr(model_instance, 'id', None) or \
                   getattr(model_instance, 'pk', 'unknown')
        
        final_filename = f"{field_name}_{model_id}_{timestamp}.jpg"
        rel_path = os.path.join(folder, final_filename).replace('\\', '/')
        
        # Save to model field (this triggers S3 upload)
        field.save(rel_path, file_to_save, save=False)
        
        # Build and return S3 URL
        s3_url = build_s3_file_url(getattr(model_instance, field_name))
        print(f"[save_model_image_field] Saved {field_name} to: {s3_url}")
        return s3_url
        
    except Exception as e:
        print(f"[save_model_image_field] Error saving {field_name}: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_image_filename(image_file: Any, use_uuid: bool = True) -> str:
    """
    Generate a unique filename for an uploaded image using UUID + timestamp format.
    
    Args:
        image_file: The uploaded file object
        use_uuid: Whether to use UUID for filename (always uses UUID + timestamp)
    
    Returns:
        Generated filename with extension
    """
    # Always use UUID + timestamp format for consistency
    unique_id = uuid.uuid4()
    timestamp = int(time.time())
    return f"{unique_id}_{timestamp}.jpg"


def upload_multiple_images_as_array(image_files: List[Any], folder: str,
                                   compress: bool = True, use_uuid: bool = True) -> List[str]:
    """
    Upload multiple images and return as a list (array).
    
    Used for sub_images in products when array format is preferred.
    
    Args:
        image_files: List of uploaded file objects
        folder: Target folder (e.g., 'fashion_images', 'groceries_images')
        compress: Whether to compress images (default: True)
        use_uuid: Whether to use UUID filenames (default: True)
    
    Returns:
        List like ["media/folder/file1.jpg", "media/folder/file2.jpg"]
        
    Example:
        >>> files = request.FILES.getlist('sub_images')
        >>> upload_multiple_images_as_array(files, 'fashion_images')
        ['media/fashion_images/uuid1.jpg', 'media/fashion_images/uuid2.jpg']
    """
    result = []
    
    if not image_files:
        return result
    
    for img_file in image_files:
        try:
            if not img_file or not hasattr(img_file, 'read'):
                continue
                
            # Generate filename
            filename = generate_image_filename(img_file, use_uuid=use_uuid)
            
            # Compress if needed
            if compress:
                compressed = compress_image(img_file)
            else:
                compressed = img_file
            
            # Upload to S3
            rel_path = f"{folder}/{filename}"
            saved_name = default_storage.save(rel_path, compressed)
            
            if saved_name:
                result.append(f"media/{saved_name}")
                print(f"[upload_multiple_images_as_array] Uploaded: {f'media/{saved_name}'}")
            else:
                print(f"[upload_multiple_images_as_array] Failed to upload: {getattr(img_file, 'name', 'unknown')}")
                
        except Exception as e:
            print(f"[upload_multiple_images_as_array] Error uploading file: {e}")
            continue
    
    return result


def upload_multiple_images(image_files: List[Any], folder: str,
                          compress: bool = True, use_uuid: bool = True,
                          start_index: int = 2) -> Dict[str, str]:
    """
    Upload multiple images and return as a dict with indexed keys.
    
    Used for sub_images in products (image2, image3, image4, etc.)
    
    Args:
        image_files: List of uploaded file objects
        folder: Target folder (e.g., 'fashion_images', 'groceries_images')
        compress: Whether to compress each image
        use_uuid: Whether to use UUID filenames (recommended for sub_images)
        start_index: Starting index for keys (default: 2 for image2, image3...)
    
    Returns:
        Dict like {"image2": "media/folder/file1.jpg", "image3": "media/folder/file2.jpg"}
        
    Example:
        >>> files = request.FILES.getlist('sub_images')
        >>> upload_multiple_images(files, 'fashion_images')
        {'image2': 'media/fashion_images/uuid1.jpg', 'image3': 'media/fashion_images/uuid2.jpg'}
    """
    result = {}
    
    if not image_files:
        return result
    
    current_index = start_index
    
    for img_file in image_files:
        try:
            saved_path = upload_image_to_s3(
                img_file, 
                folder=folder,
                compress=compress,
                use_uuid=use_uuid
            )
            
            if saved_path:
                key = f"image{current_index}"
                result[key] = saved_path
                current_index += 1
                print(f"[upload_multiple_images] Uploaded {key}: {saved_path}")
            else:
                print(f"[upload_multiple_images] Failed to upload: {getattr(img_file, 'name', 'unknown')}")
                
        except Exception as e:
            print(f"[upload_multiple_images] Error uploading file: {e}")
            continue
    
    return result


# =============================================================================
# SHORTCUT FUNCTIONS - For quick one-off usage
# =============================================================================

def s3_url(value: Any) -> Optional[str]:
    """
    Quick shortcut to get S3 URL for any file/path.
    
    Example:
        >>> s3_url(business.logo)
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/logo.png'
    """
    return build_s3_file_url(value)


def s3_urls(values: List[Any]) -> List[str]:
    """
    Get S3 URLs for a list of files/paths.
    
    Example:
        >>> s3_urls(['img1.png', 'img2.png'])
        ['https://.../img1.png', 'https://.../img2.png']
    """
    return [url for url in [build_s3_file_url(v) for v in values] if url]


def update_serializer_image_urls(serializer_data: Dict, 
                                 image_fields: List[str]) -> Dict:
    """
    Update serializer data to include S3 URLs for image fields.
    
    Args:
        serializer_data: The serializer's representation data
        image_fields: List of field names that are images
    
    Returns:
        Updated data with {field}_url keys added
    """
    for field in image_fields:
        value = serializer_data.get(field)
        if value:
            s3_url = build_s3_file_url(value)
            serializer_data[f"{field}_url"] = s3_url
    return serializer_data
