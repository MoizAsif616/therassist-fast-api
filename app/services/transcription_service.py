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
        
        t_time, t_count, c_time, c_count = 0.0, 0, 0.0, 0
        
        for u in cleaned_data["utterances"]:
            start = float(u.get("start", 0))
            end = float(u.get("end", 0))
            dur = end - start
            
            speaker = u.get("speaker") 

            if speaker == "Therapist":
                t_count += 1
                t_time += dur
            elif speaker == "Client":
                c_count += 1
                c_time += dur
        
        # Explicitly ensure floats for Postgres Double Precision
        stats = {
            "therapist_time": float(round(t_time / 1000.0, 2)), 
            "therapist_count": int(t_count),
            "client_time": float(round(c_time / 1000.0, 2)),    
            "client_count": int(c_count)
        }
        try:
            client_id = session["client_id"]
            session_number = session["session_number"]
        except Exception:
            logger.error(f"[TRANSCRIPTION] Could not fetch session metadata.")
            raise HTTPException(500, detail="Session metadata fetch failed.")

        # 4. Generate AI Insights (Sequential with Sleep to avoid Rate Limits)
        logger.info(f"[TRANSCRIPTION] Extracting insights sequentially...")
        full_text = cleaned_data["utterances"]
        
        summary = await generate_summary(session_number, full_text)
        await asyncio.sleep(2.0) # Mandatory gap
        
        sentiment = await generate_sentiment(session_id, full_text)
        await asyncio.sleep(2.0) # Mandatory gap
        
        theme_data = await generate_theme(session_number, full_text)
        await asyncio.sleep(2.0) # Mandatory gap
        
        client_profile_text = await generate_clinical_profile(
            client_id=client_id, 
            session_number=session_number, 
            utterances=full_text
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
        # Check 'file_path', not 'local_file_path'
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            try: 
                os.remove(file_path)
                logger.info(f"[TRANSCRIPTION] Cleaned up file: {file_path}")
            except Exception as e: 
                logger.warning(f"[TRANSCRIPTION] Failed to delete temp file: {e}")