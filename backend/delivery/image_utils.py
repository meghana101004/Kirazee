"""
Delivery app S3 image utilities for consistent URL generation.

This module provides centralized S3 URL building functions for all delivery-related
image operations including CRUD operations for delivery partner documents,
profile images, and other media files.
"""

import os
from typing import Optional
from django.conf import settings


def build_s3_file_url(file_path: Optional[str]) -> Optional[str]:
    """
    Build a complete S3 URL for a given file path.
    
    This is the CENTRAL function for all S3 URL generation in the delivery app.
    All image URL methods should use this function.
    
    Args:
        file_path: Relative path to the file (e.g., 'dp_documents/license_123.pdf')
                  or full URL (returned as-is)
    
    Returns:
        Complete S3 URL or None if file_path is empty
    
    Examples:
        >>> build_s3_file_url('dp_documents/license_123.pdf')
        'https://kirazee-bucket.s3.ap-south-1.amazonaws.com/prod/media/dp_documents/license_123.pdf'
        
        >>> build_s3_file_url('https://example.com/image.jpg')
        'https://example.com/image.jpg'
    """
    if not file_path:
        return None
    
    # If it's already an absolute URL, return as-is
    file_path_str = str(file_path).strip()
    if file_path_str.startswith(('http://', 'https://')):
        return file_path_str
    
    # Get S3 configuration from settings
    bucket_name = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
    region = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-south-1')
    
    if not bucket_name:
        # Fallback: return local media URL
        return f"{settings.MEDIA_URL}{file_path_str}"
    
    # Clean up the path - remove leading slashes and 'media/' prefix if present
    clean_path = file_path_str.lstrip('/')
    if clean_path.startswith('media/'):
        clean_path = clean_path[6:]  # Remove 'media/' prefix
    
    # Build S3 URL
    s3_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/prod/media/{clean_path}"
    return s3_url.replace(' ', '%20')


def normalize_media_path(file_path: Optional[str]) -> Optional[str]:
    """
    Normalize a media path for consistent storage.
    
    Removes duplicate 'media/' prefixes and ensures clean path format.
    
    Args:
        file_path: Original file path
        
    Returns:
        Normalized path ready for storage or None if empty
    """
    if not file_path:
        return None
    
    path = str(file_path).strip().lstrip('/')
    
    # Remove duplicate media/ prefixes
    while path.startswith('media/'):
        path = path[6:]
    
    return path


def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    return os.path.splitext(filename)[1].lower()


def is_valid_image_file(filename: str) -> bool:
    """Check if file has a valid image extension."""
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    return get_file_extension(filename) in valid_extensions


def build_dp_document_url(document_path: Optional[str]) -> Optional[str]:
    """
    Build S3 URL for delivery partner documents.
    
    Args:
        document_path: Path to the document file
        
    Returns:
        S3 URL for the document or None
    """
    return build_s3_file_url(document_path)


def build_dp_profile_url(profile_image_path: Optional[str]) -> Optional[str]:
    """
    Build S3 URL for delivery partner profile images.
    
    Args:
        profile_image_path: Path to the profile image
        
    Returns:
        S3 URL for the profile image or None
    """
    return build_s3_file_url(profile_image_path)


def compress_image(image_file, max_size=(1024, 1024), quality=85):
    """
    Compress an image file before saving.
    
    Args:
        image_file: Django UploadedFile object or file path
        max_size: Maximum dimensions (width, height)
        quality: JPEG quality (1-100)
        
    Returns:
        Compressed image as BytesIO object or original file if compression fails
    """
    from PIL import Image
    from io import BytesIO
    
    try:
        # Open the image
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        img = Image.open(image_file)
        
        # Convert RGBA to RGB if necessary (for JPEG output)
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        
        # Resize if larger than max_size
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.LANCZOS)
        
        # Save to BytesIO
        output = BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        
        return output
    except Exception:
        # Return original file if compression fails
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        return image_file
