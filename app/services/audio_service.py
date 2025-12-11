# app/services/audio_service.py

import asyncio
import os
import tempfile
import subprocess
from datetime import timedelta

from fastapi import UploadFile, HTTPException

from app.services.db_service import *
from app.core.supabase_client import storage
from app.services.transcription_service import transcribe_session


ALLOWED_EXTS = {"wav", "mp3", "mp4", "m4a", "aac", "flac", "ogg", "webm"}


# --------------------------
# FFmpeg Helpers
# --------------------------

def _run(cmd: list[str]):
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if proc.returncode != 0:
        raise HTTPException(status_code=400, detail=proc.stderr.strip())
    return proc.stdout


def _validate_ext(filename: str) -> str:
    ext = filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {ext}")
    return ext


def _has_audio_stream(path: str) -> bool:
    out = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        path
    ])
    return "audio" in out.lower()


def _duration_seconds(path: str) -> float:
    out = _run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ])
    return float(out.strip())


def _hms(sec: float) -> str:
    return str(timedelta(seconds=int(sec)))


def _resample_to_16k(src: str, dst: str):
    _run([
        "ffmpeg", "-i", src,
        "-ar", "16000",       # enforce 16 kHz sample rate
        "-y", dst
    ])

import hashlib

def _compute_md5(path: str) -> str:
    hash_md5 = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


# --------------------------
# Main Service Function
# --------------------------

def process_audio_and_create_session(
    file: UploadFile,
    client_id: str,
    therapist_id: str
) -> str:
    """
    Validates audio, converts to 16 kHz, stores metadata,
    uploads file, and creates a session.
    """

    ext = _validate_ext(file.filename)

    # Save uploaded audio temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
        tmp_path = tmp.name
        tmp.write(file.file.read())

    audio_hash = _compute_md5(tmp_path)

    if session_with_same_audio_exists(client_id, therapist_id, audio_hash):
        raise HTTPException(
            status_code=400,
            detail="Duplicate audio detected. This session has already been uploaded."
        )

    # Ensure the file contains audio
    if not _has_audio_stream(tmp_path):
        raise HTTPException(status_code=400, detail="File does not contain a valid audio stream.")

    # Validate duration (5–90 minutes)
    duration_sec = _duration_seconds(tmp_path)
    if duration_sec < 300 or duration_sec > 5400:
        raise HTTPException(
            status_code=400,
            detail=f"Audio duration must be between 5 and 90 minutes. Got {duration_sec:.1f}s."
        )

    duration_hms = _hms(duration_sec)

    # Resample audio to 16 kHz (no trimming)
    final_path = tmp_path.replace(f".{ext}", f"_processed.{ext}")
    _resample_to_16k(tmp_path, final_path)

    # Create DB session
    session_id = create_session(
        client_id=client_id,
        therapist_id=therapist_id,
        duration_hms=duration_hms,
        audio_hash=audio_hash
    )

    # Upload processed file to Supabase
    final_name = f"{session_id}.{ext}"
    storage_path = f"{final_name}"
    logger.info(f"[AUDIO UPLOAD] Uploading session {session_id} audio to storage at {storage_path}")
    bucket = storage.from_("therapy-sessions")

    try:
        with open(final_path, "rb") as f:
            resp = bucket.upload(storage_path, f)
        logger.info(f"[AUDIO UPLOAD] Uploaded audio for session {session_id} to storage.")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload audio to storage: {e}"
        )

    # Update DB
    update_session_audio_path(session_id, storage_path)
    update_processing_state(session_id, "UPLOADED")

    asyncio.create_task(
      transcribe_session(
          session_id=session_id,
          local_file_path=final_path,   # your processed file
        
      )
    )   
   
    # Cleanup
    os.remove(tmp_path)

    return session_id
