#!/usr/bin/env python3
"""
Script to upload local media files to S3 bucket under prod/media/ prefix.
Usage: python upload_media_to_s3.py
"""

import os
import sys
from pathlib import Path
from tqdm import tqdm

# Add the project directory to Python path so we can import settings
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kirazee.settings')

import django
django.setup()

from django.conf import settings
import boto3
from botocore.exceptions import ClientError


def get_s3_client():
    """Create S3 client using settings from Django configuration."""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )


def upload_media_to_s3(s3_prefix='prod/media'):
    """
    Upload all files from MEDIA_ROOT to S3 bucket under specified prefix.
    
    Args:
        s3_prefix: The prefix path in S3 (default: 'prod/media')
    """
    s3_client = get_s3_client()
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    media_root = settings.MEDIA_ROOT
    
    if not bucket_name:
        print("Error: AWS_STORAGE_BUCKET_NAME not configured in settings")
        sys.exit(1)
    
    if not os.path.exists(media_root):
        print(f"Error: Media root directory does not exist: {media_root}")
        sys.exit(1)
    
    print(f"Uploading media from: {media_root}")
    print(f"Target S3 bucket: {bucket_name}")
    print(f"S3 prefix: {s3_prefix}")
    print("-" * 50)
    
    # Collect all files to upload
    files_to_upload = []
    for root, dirs, files in os.walk(media_root):
        for file in files:
            local_path = os.path.join(root, file)
            # Calculate relative path from media_root
            relative_path = os.path.relpath(local_path, media_root)
            # S3 key will be: prefix/relative_path
            s3_key = f"{s3_prefix}/{relative_path}".replace("\\", "/")
            files_to_upload.append((local_path, s3_key))
    
    if not files_to_upload:
        print("No files found in media directory.")
        return
    
    print(f"Found {len(files_to_upload)} files to upload")
    
    # Upload files with progress bar
    uploaded = 0
    failed = 0
    
    for local_path, s3_key in tqdm(files_to_upload, desc="Uploading", unit="file"):
        try:
            # Determine content type (optional, but helpful)
            content_type = None
            ext = os.path.splitext(local_path)[1].lower()
            content_type_map = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.svg': 'image/svg+xml',
                '.pdf': 'application/pdf',
                '.mp4': 'video/mp4',
                '.webm': 'video/webm',
                '.mp3': 'audio/mpeg',
                '.wav': 'audio/wav',
                '.txt': 'text/plain',
                '.json': 'application/json',
            }
            content_type = content_type_map.get(ext)
            
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            
            # Upload file
            s3_client.upload_file(
                local_path,
                bucket_name,
                s3_key,
                ExtraArgs=extra_args
            )
            uploaded += 1
            
        except ClientError as e:
            print(f"\nFailed to upload {local_path}: {e}")
            failed += 1
        except Exception as e:
            print(f"\nError uploading {local_path}: {e}")
            failed += 1
    
    print("-" * 50)
    print(f"Upload complete: {uploaded} successful, {failed} failed")
    
    if uploaded > 0:
        print(f"\nFiles are now available at:")
        print(f"  https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_prefix}/")


def verify_upload(s3_prefix='prod/media', sample_size=5):
    """
    Verify uploaded files by listing objects in S3.
    """
    s3_client = get_s3_client()
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    
    print("\nVerifying upload...")
    try:
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=s3_prefix,
            MaxKeys=sample_size
        )
        
        if 'Contents' in response:
            print(f"Found {response['KeyCount']} objects in S3 under {s3_prefix}/")
            print("Sample files:")
            for obj in response['Contents'][:sample_size]:
                size_kb = obj['Size'] / 1024
                print(f"  - {obj['Key']} ({size_kb:.2f} KB)")
        else:
            print(f"No objects found in S3 under {s3_prefix}/")
            
    except ClientError as e:
        print(f"Error verifying upload: {e}")


if __name__ == "__main__":
    # Check if AWS credentials are configured
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
        print("Error: AWS credentials not configured in environment variables")
        print("Please set: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME")
        sys.exit(1)
    
    # Upload with prod/media prefix
    upload_media_to_s3(s3_prefix='prod/media')
    
    # Verify the upload
    verify_upload(s3_prefix='prod/media')
