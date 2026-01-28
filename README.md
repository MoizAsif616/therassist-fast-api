# Therassist API

A FastAPI-based backend for the Therassist application, providing endpoints for audio processing, transcription, annotation, embeddings, and chat functionality.

## Table of Contents

- [Installation](#installation)
- [Running the Server](#running-the-server)
- [API Endpoints](#api-endpoints)
- [Authentication](#authentication)

---

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Install Dependencies

1. Navigate to the project root directory:

```bash
cd d:\therassist-fast-api
```

2. Install all required packages from `requirements.txt`:

```bash
pip install -r requirements.txt
```

This will install all dependencies including:
- FastAPI and Uvicorn
- Supabase client
- Audio processing tools (ffmpeg)
- HuggingFace integration
- AssemblyAI for transcription
- And other required packages

---

## Running the Server

### Start the FastAPI Application with Uvicorn

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Parameters:**
- `--reload`: Automatically reload the server when code changes (useful for development)
- `--host 0.0.0.0`: Bind to all network interfaces
- `--port 8000`: Run on port 8000

Once running, the API will be available at:
- **Base URL**: `http://localhost:8000`
- **Interactive API Docs**: `http://localhost:8000/docs` (Swagger UI)
- **Alternative API Docs**: `http://localhost:8000/redoc` (ReDoc)

---

## API Endpoints

All endpoints are prefixed with `/api/v1/` and require authentication via JWT token in the `Authorization` header.

### Authentication

All endpoints (except the root health check) require authentication. Include the JWT token in the request header:

```
Authorization: Bearer <your_jwt_token>
```

The token is obtained from the `authenticate` dependency which validates your identity as a therapist.

---

### 1. Audio Upload

**Endpoint:** `POST /api/v1/audio/upload`

**Description:** Upload an audio file for processing.

**Authentication:** Required (JWT token)

**Request:**
- **Form Data:**
  - `audio_file` (file, required): The audio file to upload
  - `payload` (string, required): JSON string containing metadata

**Payload Structure:**
```json
{
  "client_id": "string"
}
```

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/audio/upload" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -F "audio_file=@path/to/audio.wav" \
  -F "payload={\"client_id\": \"client_123\"}"
```

**Example Response:**
```json
{
  "session_id": "sess_abc123",
  "detail": "Audio uploaded and further processing started."
}
```

**Status Codes:**
- `201`: Audio uploaded successfully
- `400`: Invalid payload or client does not exist
- `401`: Unauthorized (missing or invalid token)

---

### 2. Transcription

**Endpoint:** `POST /api/v1/transcribe/{session_id}`

**Description:** Transcribe the audio for a specific session.

**Authentication:** Required (JWT token)

**Path Parameters:**
- `session_id` (string, required): The ID of the session to transcribe

**Request Body:**
```json
{
  "client_id": "string"
}
```

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/transcribe/sess_abc123" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "client_123"}'
```

**Example Response:**
```json
{
  "detail": "Transcription completed and further processing started."
}
```

**Status Codes:**
- `200`: Transcription completed successfully
- `400`: Client does not exist or session does not belong to client
- `401`: Unauthorized
- `403`: You do not have permission to access this client's session

---

### 3. Annotation

**Endpoint:** `POST /api/v1/annotate/{session_id}`

**Description:** Generate annotations for a specific session.

**Authentication:** Required (JWT token)

**Path Parameters:**
- `session_id` (string, required): The ID of the session to annotate

**Request Body:**
```json
{
  "client_id": "string"
}
```

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/annotate/sess_abc123" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "client_123"}'
```

**Example Response:**
```json
{
  "session_id": "sess_abc123",
  "detail": "Annotation completed and further processing started."
}
```

**Status Codes:**
- `200`: Annotation completed successfully
- `400`: Client does not exist or session does not belong to client
- `401`: Unauthorized
- `403`: Access denied to client's data

---

### 4. Embedding Generation

**Endpoint:** `POST /api/v1/embed/{session_id}`

**Description:** Generate vector embeddings for a specific session.

**Authentication:** Required (JWT token)

**Path Parameters:**
- `session_id` (string, required): The ID of the session to embed

**Request Body:**
```json
{
  "client_id": "string"
}
```

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/embed/sess_abc123" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "client_123"}'
```

**Example Response:**
```json
{
  "detail": "Embedding generation completed successfully."
}
```

**Status Codes:**
- `200`: Embedding generation completed successfully
- `400`: Client does not exist or session does not belong to client
- `401`: Unauthorized
- `500`: Internal server error during embedding generation

---

### 5. Chat / Query

**Endpoint:** `POST /api/v1/chat`

**Description:** Send a query to the chat service for analyzing client data.

**Authentication:** Required (JWT token)

**Request Body:**
```json
{
  "query": "string (required, min_length: 1)",
  "client_id": "string (required)",
  "session_id": "string or null (optional)"
}
```

**Field Descriptions:**
- `query` (string, required): The user's question or query
- `client_id` (string, required): The ID of the client
- `session_id` (string or null, optional): Specific session context. If null, uses global context (all sessions)

**Example Request (cURL):**
```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the key themes discussed with this client?",
    "client_id": "client_123",
    "session_id": "sess_abc123"
  }'
```

**Example Request with Global Context:**
```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Authorization: Bearer <your_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What patterns have emerged across all sessions?",
    "client_id": "client_123",
    "session_id": null
  }'
```

**Example Response:**
```
"The analysis shows that the client frequently discusses anxiety-related topics..."
```

**Status Codes:**
- `200`: Query processed successfully
- `400`: Missing session_id or invalid client
- `401`: Unauthorized
- `403`: You do not have permission to access this client's data

---

## Project Structure

```
d:\therassist-fast-api/
├── app/
│   ├── main.py                 # FastAPI app initialization and route registration
│   ├── api/
│   │   └── v1/
│   │       ├── audio_routes.py         # Audio upload endpoints
│   │       ├── transcription_routes.py # Transcription endpoints
│   │       ├── annotation_routes.py    # Annotation endpoints
│   │       ├── embedding_routes.py     # Embedding endpoints
│   │       └── chat_routes.py          # Chat/query endpoints
│   ├── core/
│   │   ├── config.py           # Configuration settings
│   │   └── supabase_client.py  # Supabase client setup
│   ├── schemas/
│   │   └── chat_schemas.py     # Pydantic models for chat endpoints
│   ├── services/
│   │   ├── auth_service.py     # JWT authentication
│   │   ├── audio_service.py    # Audio processing logic
│   │   ├── transcription_service.py
│   │   ├── annotation_service.py
│   │   ├── embedding_service.py
│   │   ├── chat_service.py
│   │   ├── user_service.py
│   │   └── db_service.py       # Database operations
│   └── utils/
│       ├── audio_utils.py
│       ├── transcription_utils.py
│       ├── annotation_utils.py
│       ├── embedding_utils.py
│       ├── chat_utils.py
│       └── validators.py
└── requirements.txt            # Python dependencies
```

---

## Development Tips

- **Interactive API Documentation**: Visit `http://localhost:8000/docs` to test all endpoints interactively
- **Enable Auto-reload**: Use the `--reload` flag during development for automatic server restart on code changes
- **Check Logs**: Monitor terminal output for detailed logging of requests and processing steps
- **CORS**: The API is configured to allow cross-origin requests from all origins (`*`)

---

## Troubleshooting

### Port Already in Use
If port 8000 is already in use, specify a different port:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### Missing Dependencies
If you encounter missing module errors, reinstall dependencies:
```bash
pip install -r requirements.txt --force-reinstall
```

### Authentication Errors
Ensure your JWT token is valid and included in the `Authorization: Bearer <token>` header for all protected endpoints.

---

## API Base Information

- **Title**: Therassist API
- **Version**: 1.0.0
- **Base URL**: `http://localhost:8000`
- **API Prefix**: `/api/v1`
