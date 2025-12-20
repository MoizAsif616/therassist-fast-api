import asyncio
import os
import tempfile
import time
import subprocess
import hashlib
from datetime import timedelta
from fastapi import UploadFile, HTTPException

# Import Business Logic
from app.services.db_service import session_with_same_audio_exists
from app.services.transcription_service import transcribe_session

# Import New Utilities
from app.utils.audio_utils import upload_file_to_r2, delete_file_from_r2
from app.utils.transaction_utils import create_session_transaction

ALLOWED_EXTS = {"wav", "mp3", "mp4", "m4a", "aac", "flac", "ogg", "webm"}

# --- HELPERS ---
def _run(cmd):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0: raise HTTPException(400, proc.stderr.strip())
    return proc.stdout

def _validate_ext(fn):
    ext = fn.split(".")[-1].lower()
    if ext not in ALLOWED_EXTS: raise HTTPException(400, f"Unsupported: {ext}")
    return ext

def _has_audio(path): 
    return "audio" in _run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path]).lower()

def _duration(path): 
    return float(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]).strip())

def _resample(src, dst): 
    _run(["ffmpeg", "-i", src, "-ar", "16000", "-y", dst])

def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(8192), b""): h.update(c)
    return h.hexdigest()


## MAIN SERVICE FUNCTION
def audio_service(file: UploadFile, client_id: str, therapist_id: str) -> str:
    ext = _validate_ext(file.filename)

    # 1. Save Temp File locally
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp_path = tmp.name
        tmp.write(file.file.read())

    try:
        # 2. Validation
        audio_hash = _md5(tmp_path)
        if session_with_same_audio_exists(client_id, therapist_id, audio_hash):
            raise HTTPException(400, "Duplicate audio detected.")

        if not _has_audio(tmp_path): 
            raise HTTPException(400, "No audio stream found.")
        
        dur = _duration(tmp_path)
        if not (300 <= dur <= 5400): 
            raise HTTPException(400, f"Duration {dur:.1f}s out of range (5-90m).")
        
        # 3. Processing (Resample)
        final_path = tmp_path.replace(f".{ext}", f"_processed.{ext}")
        _resample(tmp_path, final_path)

        # 4. Generate Filename & UPLOAD (Step 1 of Distributed Transaction)
        timestamp = int(time.time())
        # Format: {therapist_id}-{timestamp}.{ext}
        r2_object_name = f"{therapist_id}-{timestamp}.{ext}"

        # Upload to R2 via Minio
        try:
            uploaded_url = upload_file_to_r2(final_path, r2_object_name)
        except Exception as e:
            # Explicitly handle R2/Minio failure
            raise HTTPException(status_code=502, detail=f"Storage Upload Failed: {str(e)}")

        # 5. DB INSERT (Step 2 of Distributed Transaction)
        try:
            session_id = create_session_transaction(
                client_id=client_id,
                therapist_id=therapist_id,
                duration_hms=str(timedelta(seconds=int(dur))),
                audio_hash=audio_hash,
                audio_url=uploaded_url
            )
        except Exception as db_error:
            # --- ROLLBACK ---
            # DB failed, so we MUST undo the upload
            delete_file_from_r2(r2_object_name)
            raise db_error

        # 6. Start Async Transcription (Only runs if both steps above succeeded)
        asyncio.create_task(transcribe_session(session_id, final_path))

        return session_id

    finally:
        # Cleanup local temp files
        if os.path.exists(tmp_path): os.remove(tmp_path)
        # Note: We keep 'final_path' briefly if needed for async task or let OS clean /tmp