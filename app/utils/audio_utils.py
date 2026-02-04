import os
import asyncio 
import httpx
from urllib.parse import urlparse
from fastapi import HTTPException
from minio import Minio
from minio.error import S3Error
from loguru import logger

# --- CONFIGURATION ---
R2_ENDPOINT = os.getenv('R2_ENDPOINT_URL', '').replace("https://", "").replace("http://", "").strip()
R2_ACCESS_KEY = os.getenv('R2_ACCESS_KEY_ID', '').strip()
R2_SECRET_KEY = os.getenv('R2_SECRET_ACCESS_KEY', '').strip()
R2_BUCKET = os.getenv('R2_BUCKET_NAME', '').strip()

ASSEMBLY_KEY = os.getenv("ASSEMBLYAI_API_KEY", "").strip()
UPLOAD_URL = "https://api.assemblyai.com/v2/upload"
TRANSCRIPT_URL = "https://api.assemblyai.com/v2/transcript"

client = Minio(R2_ENDPOINT, access_key=R2_ACCESS_KEY, secret_key=R2_SECRET_KEY, secure=True)

MIME_TYPES = {
    "wav": "audio/wav", "mp3": "audio/mpeg", "mp4": "audio/mp4",
    "m4a": "audio/mp4", "aac": "audio/aac", "flac": "audio/flac",
    "ogg": "audio/ogg", "webm": "audio/webm"
}

# --- R2 FUNCTIONS ---
def upload_file_to_r2(local_path: str, object_name: str) -> str:
    ext = local_path.split(".")[-1].lower()
    content_type = MIME_TYPES.get(ext, "application/octet-stream")
    try:
        client.fput_object(R2_BUCKET, object_name, local_path, content_type=content_type)
        return f"https://{R2_ENDPOINT}/{R2_BUCKET}/{object_name}"
    except S3Error as e:
        logger.error(f"[R2 ERROR] Upload failed: {e}")
        raise e

def delete_file_from_r2(object_name: str):
    try:
        client.remove_object(R2_BUCKET, object_name)
        logger.info(f"[R2] Rollback: Deleted {object_name}")
    except S3Error as e:
        logger.error(f"[R2 ERROR] Rollback deletion failed: {e}")

async def download_audio_from_r2(storage_path: str, dst_path: str):
    try:
        if "://" in storage_path:
            parsed = urlparse(storage_path)
            path = parsed.path.lstrip("/")
            object_name = path.replace(f"{R2_BUCKET}/", "", 1) if path.startswith(f"{R2_BUCKET}/") else path
        else:
            object_name = storage_path
        await asyncio.to_thread(client.fget_object, R2_BUCKET, object_name, dst_path)
    except Exception as e:
        logger.error(f"[R2 ERROR] Download failed: {e}")
        raise HTTPException(500, detail=f"Failed to download audio: {e}")

# --- ASSEMBLYAI FUNCTIONS ---
async def upload_audio_to_assembly(file_path: str) -> str:
    if not ASSEMBLY_KEY: raise HTTPException(500, detail="ASSEMBLYAI_API_KEY missing")
    headers = {"authorization": ASSEMBLY_KEY}
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30), trust_env=False) as client:
        with open(file_path, "rb") as f:
            try:
                resp = await client.post(UPLOAD_URL, headers=headers, content=f.read())
                resp.raise_for_status()
            except httpx.ConnectError as e:
                logger.error(f"[ASSEMBLY] Connection failed: {e}")
                raise HTTPException(502, detail="Failed to connect to AssemblyAI. Network Error.")
    return resp.json()["upload_url"]

async def create_transcription_job(upload_url: str) -> str:
    headers = {"authorization": ASSEMBLY_KEY, "content-type": "application/json"}
    payload = {"audio_url": upload_url, "speaker_labels": True, "speakers_expected": 2, "punctuate": True, "format_text": True, "language_code": "en"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30), trust_env=False) as client:
        resp = await client.post(TRANSCRIPT_URL, headers=headers, json=payload)
        resp.raise_for_status()
    return resp.json()["id"]

async def poll_transcription_result(tid: str) -> dict:
    headers = {"authorization": ASSEMBLY_KEY}
    url = f"{TRANSCRIPT_URL}/{tid}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=30), trust_env=False) as client:
        while True:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            j = resp.json()
            if j["status"] == "completed": return j
            if j["status"] == "error": raise HTTPException(502, detail=f"AssemblyAI error: {j.get('error')}")
            await asyncio.sleep(3)

def clean_transcription_data(raw_json: dict) -> dict:
    cleaned = {"text": raw_json.get("text", ""), "utterances": []}
    def ms_to_hms(ms: int) -> str:
        s = ms // 1000
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"
    for u in raw_json.get("utterances", []):
        cleaned["utterances"].append({
            "speaker": u.get("speaker"),
            "start_time": ms_to_hms(u.get("start", 0)),
            "end_time": ms_to_hms(u.get("end", 0)),
            "text": u.get("text", "")
        })
    return cleaned