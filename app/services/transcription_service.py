import os
import asyncio
import tempfile
from fastapi import HTTPException
from loguru import logger

from app.services.db_service import get_session
from app.services.annotation_service import annotation_service

# Import our modular utilities
from app.utils.audio_utils import (
    download_audio_from_r2,
    upload_audio_to_assembly,
    create_transcription_job,
    poll_transcription_result,
    clean_transcription_data
)
from app.utils.transcription_utils import (
    generate_summary,
    generate_theme,
    generate_sentiment,
    generate_clinical_profile,
    identify_speaker_roles,
    impute_speaker_labels

)
from app.utils.transaction_utils import commit_transcription_transaction


async def transcribe_session(session_id: str, local_file_path: str | None = None):
    
    session = get_session(session_id)
    if session["processing_state"] != "UPLOADED":
        raise HTTPException(400, detail=f"Invalid state: {session['processing_state']}")

    # 1. Prepare Audio File
    if local_file_path:
        file_path = local_file_path
    else:
        if not session["audio_url"]: raise HTTPException(400, "No audio_url found")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as tmp:
            file_path = tmp.name
        await download_audio_from_r2(session["audio_url"], file_path)

    try:
        # 2. Transcribe (AssemblyAI)
        try:
          logger.info(f"[TRANSCRIPTION] Uploading to AssemblyAI.")
          upload_url = await upload_audio_to_assembly(file_path)
        except Exception as e:
          logger.error(f"[TRANSCRIPTION] Upload failed: {e}")
          raise HTTPException(500, detail="Audio upload failed.")
        
        try:
          logger.info(f"[TRANSCRIPTION] Waiting for transcription.")
          tid = await create_transcription_job(upload_url)
          raw_data = await poll_transcription_result(tid)
          cleaned_data = clean_transcription_data(raw_data)
          print(cleaned_data["text"][:200])
          print(cleaned_data["utterances"][:2])
          role_map = await identify_speaker_roles(cleaned_data["utterances"])
          cleaned_data = await impute_speaker_labels(cleaned_data, role_map)
        except Exception as e:
          logger.error(f"[TRANSCRIPTION] Transcription failed: {e}")
          raise HTTPException(500, detail="Transcription failed.")
        
        logger.info(f"[TRANSCRIPTION] Speaker roles identified: {role_map}")
        
        # 3. Calculate Speaker Stats
        t_time, t_count, c_time, c_count = 0, 0, 0, 0
        for u in raw_data.get("utterances", []):
            dur = u.get("end") - u.get("start")
            if u.get("speaker") == 'A': t_count += 1; t_time += dur
            elif u.get("speaker") == 'B': c_count += 1; c_time += dur
        
        stats = {
            "therapist_time": round(t_time / 1000.0, 2),
            "therapist_count": t_count,
            "client_time": round(c_time / 1000.0, 2),
            "client_count": c_count
        }
        try:
            client_id = session["client_id"]
            session_number = session["session_number"]
        except Exception:
            logger.error(f"[TRANSCRIPTION] Could not fetch session metadata.")
            raise HTTPException(500, detail="Session metadata fetch failed.")

        # 4. Generate AI Insights (Parallel)
        logger.info(f"[TRANSCRIPTION] Exracting insights.")
        full_text = cleaned_data["text"]
        
        summary, sentiment, theme_data, client_profile_text = await asyncio.gather(
            generate_summary(session_id, full_text),
            generate_sentiment(session_id, full_text),
            generate_theme(session_id, full_text),
            generate_clinical_profile(client_id, session_number, full_text)
        )

        # 5. Atomic DB Commit
        logger.info(f"[TRANSCRIPTION] Committing transaction.")
        commit_transcription_transaction(
            session_id=session_id,
            summary=summary,
            sentiment_score=sentiment,
            theme=theme_data["theme"],
            explanation=theme_data["explanation"],
            utterances=cleaned_data["utterances"],
            stats=stats,
            client_id=client_id,
            client_profile=client_profile_text
        )

        # 6. Trigger Annotation
        asyncio.create_task(annotation_service(session_id))

        return {
            "detail": "Transcription completed and further processing started.",
        }

    except Exception as e:
        logger.error(f"[TRANSCRIPTION] Transcription failed: {e}")
        raise HTTPException(500, detail=f"Transcription failed: {e}")

    finally:
        if local_file_path and os.path.exists(local_file_path):
            try: os.remove(local_file_path)
            except: pass