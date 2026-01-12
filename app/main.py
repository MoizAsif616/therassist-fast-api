from fastapi import FastAPI
from app.api.v1.audio_routes import router as audio_router
from app.api.v1.transcription_routes import router as transcription_router
from app.api.v1.annotation_routes import router as annotation_router
from app.api.v1.embedding_routes import router as embedding_router
from fastapi.middleware.cors import CORSMiddleware
import os
# app/main.py
from app.api.v1.search_routes import router as search_router


os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)


app = FastAPI(
    title="Therassist API",
    version="1.0.0"
)
origins = [
    # Allow local development for Next.js (often on port 3000)
    # "http://localhost:3000",
    # "http://127.0.0.1:3000",
    "*",
    # If you deploy a staging or production frontend, add its URL here later
    # "https://your-production-frontend.com", 
]

app.add_middleware(
    CORSMiddleware,
    # The list of origins that should be permitted to make cross-origin requests.
    allow_origins=origins,
    # Allows cookies (usually not needed with JWT, but good practice if using cookies)
    allow_credentials=True,
    # Allows all standard methods (GET, POST, PUT, DELETE)
    allow_methods=["*"], 
    # Allows all headers, including 'Authorization' (CRITICAL for your JWT) and 'Content-Type'.
    allow_headers=["*"],
)

api_version = "/api/v1"
# Register routes
app.include_router(audio_router, prefix=f"{api_version}/audio", tags=["Audio"])
app.include_router(transcription_router, prefix=api_version)
app.include_router(annotation_router, prefix=api_version)
app.include_router(embedding_router, prefix=api_version)
app.include_router(search_router, prefix=api_version)

# Health Check / Root Endpoint
@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Therassist API is running! Access routes via /api/v1/..."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
