from fastapi import FastAPI
from app.api.v1.audio_routes import router as audio_router
from app.api.v1.transcription_routes import router as transcription_router
from app.api.v1.annotation_routes import router as annotation_router

app = FastAPI(
    title="Therassist API",
    version="1.0.0"
)

# Register routes
app.include_router(audio_router, prefix="/api/v1/audio", tags=["Audio"])
app.include_router(transcription_router, prefix="/api/v1/transcription")
app.include_router(annotation_router, prefix="/api/v1/annotation")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
