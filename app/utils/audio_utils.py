import os
from minio import Minio
from minio.error import S3Error

# Cloudflare R2 Config
R2_ENDPOINT = os.getenv('R2_ENDPOINT_URL', '').replace("https://", "").replace("http://", "")
R2_ACCESS_KEY = os.getenv('R2_ACCESS_KEY_ID')
R2_SECRET_KEY = os.getenv('R2_SECRET_ACCESS_KEY')
R2_BUCKET = os.getenv('R2_BUCKET_NAME')

# Initialize Minio Client
# secure=True ensures we use HTTPS
client = Minio(
    R2_ENDPOINT,
    access_key=R2_ACCESS_KEY,
    secret_key=R2_SECRET_KEY,
    secure=True
)

# Explicit mapping for your allowed extensions
MIME_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "mp4": "audio/mp4",
    "m4a": "audio/m4a",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "webm": "audio/webm"
}

def upload_file_to_r2(local_path: str, object_name: str) -> str:
    # 1. Detect extension from the local file path
    ext = local_path.split(".")[-1].lower()
    
    # 2. Get correct MIME type (default to binary if unknown)
    content_type = MIME_TYPES.get(ext, "application/octet-stream")

    try:
        client.fput_object(
            bucket_name=R2_BUCKET,
            object_name=object_name,
            file_path=local_path,
            content_type=content_type  # <--- Now dynamic
        )
        
        return f"https://{R2_ENDPOINT}/{R2_BUCKET}/{object_name}"

    except S3Error as e:
        print(f"[R2 ERROR] Upload failed: {e}")
        raise e

def delete_file_from_r2(object_name: str):
    """
    Deletes a file from R2. Used for rolling back a failed transaction.
    """
    try:
        client.remove_object(R2_BUCKET, object_name)
        print(f"[R2] Rollback: Deleted {object_name}")
    except S3Error as e:
        print(f"[R2 ERROR] Rollback deletion failed for {object_name}: {e}")