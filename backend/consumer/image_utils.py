"""
Image Utilities for Consumer App - S3 URL Handling
====================================================
This module provides centralized image handling utilities for the consumer app,
including S3 URL generation, image processing, and helper functions for
CRUD operations.

Usage:
    from consumer.image_utils import build_s3_file_url, process_uploaded_image
    
    # Generate S3 URL for an image field
    url = build_s3_file_url(obj.logo)
    
    # Process uploaded image (compress, check duplicates)
    processed_path = process_uploaded_image(uploaded_file)
"""

import os
import hashlib
import uuid
import time
import boto3
from PIL import Image
from io import BytesIO
from django.conf import settings
from django.core.files.storage import default_storage

# ============================================================================
# UUID-based Upload Helper Functions
# ============================================================================

def upload_image_to_s3(image_file, folder, filename=None, compress=True, use_uuid=True):
    """
    Upload an image directly to S3 with UUID encryption and return the stored path.
    
    This function compresses the image, generates a secure UUID filename,
    and saves directly to S3 using default_storage.
    
    Args:
        image_file: The uploaded file object (from request.FILES)
        folder: Target folder (e.g., 'consumer_images', 'profile_pics')
        filename: Optional custom filename (without extension). If None, uses UUID by default
        compress: Whether to compress the image (default: True)
        use_uuid: Whether to use UUID for filename (default: True, uses secure UUID)
    
    Returns:
        Stored path like "media/folder/uuid.jpg" or None on failure
        
    Example:
        >>> upload_image_to_s3(request.FILES['avatar'], 'profile_pics')
        'media/profile_pics/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg'
        
        >>> upload_image_to_s3(request.FILES['banner'], 'banners')
        'media/banners/f4e5d6c7-b8a9-0123-4567-89abcdef0123.jpg'
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
        
        # Generate secure filename
        if use_uuid:
            final_filename = f"{uuid.uuid4()}.jpg"
        elif filename:
            final_filename = f"{filename}.jpg"
        else:
            # Use original filename base with timestamp
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


def upload_multiple_images(image_files, folder, compress=True, use_uuid=True, start_index=2):
    """
    Upload multiple images to S3 with UUID encryption and return as indexed object.
    
    Args:
        image_files: List of uploaded file objects
        folder: Target folder (e.g., 'consumer_images')
        compress: Whether to compress images (default: True)
        use_uuid: Whether to use UUID for filenames (default: True)
        start_index: Starting index for image keys (default: 2 for image2, image3, etc.)
    
    Returns:
        Dict with keys like 'image2', 'image3', etc. pointing to S3 paths
        
    Example:
        >>> images = upload_multiple_images([file1, file2], 'gallery')
        >>> images
        {'image2': 'media/gallery/uuid1.jpg', 'image3': 'media/gallery/uuid2.jpg'}
    """
    if not image_files:
        return {}
    
    result = {}
    for i, image_file in enumerate(image_files, start=start_index):
        saved_path = upload_image_to_s3(
            image_file,
            folder=folder,
            compress=compress,
            use_uuid=use_uuid
        )
        if saved_path:
            result[f"image{i}"] = saved_path
    
    return result


# ============================================================================
# S3 URL Building Functions
# ============================================================================

def build_s3_file_url(file_path_or_field):
    """
    Build a complete S3 URL for a file path or FileField.
    
    Args:
        file_path_or_field: Can be:
            - A FileField instance (e.g., obj.logo, obj.item_image)
            - A string path (e.g., 'groceries_images/product.jpg')
            - None
    
    Returns:
        str: Full S3 URL (e.g., 'https://bucket.s3.region.amazonaws.com/prod/media/path')
        None: If input is empty/None
    
    Examples:
        >>> build_s3_file_url(obj.logo)
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/business/logos/logo.jpg'
        
        >>> build_s3_file_url('groceries_images/product.jpg')
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/groceries_images/product.jpg'
    """
    if not file_path_or_field:
        return None
    
    # Get the file path - handle both FileField and string paths
    if hasattr(file_path_or_field, 'name'):
        # It's a FileField
        file_path = file_path_or_field.name
    elif hasattr(file_path_or_field, 'url'):
        # It's a FileField with url attribute
        file_path = file_path_or_field.url
    else:
        # It's a string path
        file_path = str(file_path_or_field)
    
    if not file_path:
        return None
    
    # Clean up the path
    file_path = file_path.strip()
    
    # If already a full URL, return as-is
    if file_path.lower().startswith(('http://', 'https://')):
        return file_path
    
    # Remove leading slashes and common prefixes
    file_path = file_path.lstrip('/')
    
    # Remove 'media/' prefix if present (since S3 location already includes it)
    if file_path.startswith('media/'):
        file_path = file_path[6:]
    
    # Remove 'kirazee/' prefix if present
    if file_path.startswith('kirazee/'):
        file_path = file_path[8:]
    
    # Get S3 configuration from settings
    bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
    region = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')
    
    if not bucket_name:
        # Fallback: return local media URL
        return f"{settings.MEDIA_URL}{file_path}"
    
    # Build S3 URL
    s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/prod/media/{file_path}"
    return s3_url.replace(' ', '%20')


def build_s3_image_url_field(obj, field_name):
    """
    Build S3 URL for an object's image field by field name.
    
    Args:
        obj: Model instance
        field_name: Name of the image field (e.g., 'logo', 'item_image')
    
    Returns:
        str: S3 URL or None
    
    Example:
        >>> build_s3_image_url_field(business, 'logo')
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/business/logos/logo.jpg'
    """
    if not obj:
        return None
    
    field = getattr(obj, field_name, None)
    return build_s3_file_url(field)


# ============================================================================
# Image Processing Functions
# ============================================================================

def compress_image(image_file, max_size=(1024, 1024), quality=85, format='JPEG'):
    """
    Compress an image file to reduce file size while maintaining quality.
    
    Args:
        image_file: Django UploadedFile or file path
        max_size: Tuple of (width, height) for maximum dimensions
        quality: JPEG quality (1-100)
        format: Output format ('JPEG', 'PNG', 'WEBP')
    
    Returns:
        BytesIO: Compressed image as BytesIO object
    
    Example:
        >>> compressed = compress_image(uploaded_file, max_size=(800, 800), quality=80)
        >>> obj.image.save('image.jpg', compressed)
    """
    try:
        # Open image
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        
        img = Image.open(image_file)
        
        # Convert RGBA to RGB if saving as JPEG
        if format == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        
        # Resize if larger than max_size
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save to BytesIO
        output = BytesIO()
        img.save(output, format=format, quality=quality, optimize=True)
        output.seek(0)
        
        return output
    except Exception as e:
        print(f"Error compressing image: {e}")
        # Return original if compression fails
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        return image_file


def get_file_hash(file_obj):
    """
    Calculate MD5 hash of a file for duplicate detection.
    
    Args:
        file_obj: File object or path
    
    Returns:
        str: MD5 hash of file content
    """
    hash_md5 = hashlib.md5()
    
    if hasattr(file_obj, 'read'):
        # It's a file-like object
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        for chunk in iter(lambda: file_obj.read(4096), b""):
            hash_md5.update(chunk)
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
    else:
        # It's a file path
        with open(file_obj, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
    
    return hash_md5.hexdigest()


def check_duplicate_exists(file_hash, model_class, field_name='image_hash'):
    """
    Check if a file with the same hash already exists in the database.
    
    Args:
        file_hash: MD5 hash of the file
        model_class: Django model class to check
        field_name: Name of the field storing file hash
    
    Returns:
        tuple: (bool, object) - (exists, existing_instance)
    """
    try:
        existing = model_class.objects.filter(**{field_name: file_hash}).first()
        if existing:
            return True, existing
    except Exception:
        pass
    return False, None


# ============================================================================
# Upload Processing with Compression and Duplicate Check
# ============================================================================

def process_uploaded_image(
    uploaded_file,
    compress=True,
    max_size=(1024, 1024),
    quality=85,
    check_duplicates=False,
    model_class=None,
    hash_field=None
):
    """
    Process an uploaded image with optional compression and duplicate checking.
    
    Args:
        uploaded_file: Django UploadedFile
        compress: Whether to compress the image
        max_size: Maximum dimensions (width, height)
        quality: JPEG quality for compression
        check_duplicates: Whether to check for duplicate files
        model_class: Model class for duplicate checking
        hash_field: Field name storing file hash
    
    Returns:
        dict: {
            'file': processed_file,
            'is_duplicate': bool,
            'existing_instance': object or None,
            'file_hash': str
        }
    
    Example:
        >>> result = process_uploaded_image(
        ...     request.FILES['image'],
        ...     compress=True,
        ...     check_duplicates=True,
        ...     model_class=Product,
        ...     hash_field='image_hash'
        ... )
        >>> if result['is_duplicate']:
        ...     # Use existing image
        ...     pass
    """
    result = {
        'file': uploaded_file,
        'is_duplicate': False,
        'existing_instance': None,
        'file_hash': None
    }
    
    if not uploaded_file:
        return result
    
    # Calculate file hash
    file_hash = get_file_hash(uploaded_file)
    result['file_hash'] = file_hash
    
    # Check for duplicates
    if check_duplicates and model_class and hash_field:
        is_dup, existing = check_duplicate_exists(file_hash, model_class, hash_field)
        result['is_duplicate'] = is_dup
        result['existing_instance'] = existing
        if is_dup:
            return result
    
    # Compress image
    if compress:
        compressed = compress_image(uploaded_file, max_size=max_size, quality=quality)
        result['file'] = compressed
    
    return result


# ============================================================================
# Batch Processing Helpers
# ============================================================================

def build_s3_urls_for_objects(objects, field_name):
    """
    Build S3 URLs for a list of objects' image fields.
    
    Args:
        objects: QuerySet or list of model instances
        field_name: Name of the image field
    
    Returns:
        dict: Mapping of object_id -> S3 URL
    
    Example:
        >>> urls = build_s3_urls_for_objects(businesses, 'logo')
        >>> urls
        {1: 'https://.../logo1.jpg', 2: 'https://.../logo2.jpg'}
    """
    urls = {}
    for obj in objects:
        obj_id = getattr(obj, 'id', None) or getattr(obj, 'pk', None)
        if obj_id:
            urls[obj_id] = build_s3_image_url_field(obj, field_name)
    return urls


def process_sub_images(sub_images_list):
    """
    Process a list of sub-images and build S3 URLs for each.
    
    Args:
        sub_images_list: List of image paths or FileFields
    
    Returns:
        list: List of S3 URLs
    
    Example:
        >>> sub_images = ['img1.jpg', 'img2.jpg']
        >>> urls = process_sub_images(sub_images)
        ['https://.../img1.jpg', 'https://.../img2.jpg']
    """
    if not sub_images_list:
        return []
    
    urls = []
    for img in sub_images_list:
        if img:
            url = build_s3_file_url(img)
            if url:
                urls.append(url)
    return urls


# ============================================================================
# Serializer Mixins (Optional)
# ============================================================================

class ImageURLMixin:
    """
    Mixin for serializers to add S3 URL generation.
    
    Usage:
        class MySerializer(ImageURLMixin, serializers.ModelSerializer):
            image_url = serializers.SerializerMethodField()
            
            def get_image_url(self, obj):
                return self.build_s3_url(obj.image)
    """
    
    def build_s3_url(self, file_field):
        """Build S3 URL for a file field."""
        return build_s3_file_url(file_field)


# ============================================================================
# View Helpers
# ============================================================================

def get_s3_presigned_url(file_path, expiration=3600):
    """
    Generate a presigned URL for private S3 objects.
    
    Args:
        file_path: Path to the file in S3
        expiration: URL expiration time in seconds (default: 1 hour)
    
    Returns:
        str: Presigned URL or None if error
    """
    try:
        bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        if not bucket_name:
            return None
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')
        )
        
        # Clean path
        file_path = file_path.lstrip('/')
        if file_path.startswith('media/'):
            file_path = file_path[6:]
        
        # Generate presigned URL
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': f'prod/media/{file_path}'
            },
            ExpiresIn=expiration
        )
        return url
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return None


# ============================================================================
# Backwards Compatibility Aliases
# ============================================================================

def s3_url(file_path_or_field):
    """Alias for build_s3_file_url()."""
    return build_s3_file_url(file_path_or_field)


def s3_urls(objects, field_name):
    """Alias for build_s3_urls_for_objects()."""
    return build_s3_urls_for_objects(objects, field_name)


def update_serializer_image_urls(serializer_instance, image_fields):
    """
    Helper to update multiple image fields in a serializer.
    
    Args:
        serializer_instance: The serializer instance
        image_fields: List of field names to update
    
    Returns:
        dict: Mapping of field names to S3 URLs
    """
    obj = serializer_instance.instance
    urls = {}
    for field in image_fields:
        urls[field] = build_s3_image_url_field(obj, field)
    return urls


# Make key functions available at module level
__all__ = [
    'upload_image_to_s3',
    'upload_multiple_images',
    'build_s3_file_url',
    'build_s3_image_url_field',
    'build_s3_urls_for_objects',
    'process_sub_images',
    'compress_image',
    'get_file_hash',
    'check_duplicate_exists',
    'process_uploaded_image',
    'get_s3_presigned_url',
    'ImageURLMixin',
    's3_url',
    's3_urls',
    'update_serializer_image_urls',
]
