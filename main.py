import os
import uuid
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

load_dotenv()

# Environment variables will be set in the Render Dashboard
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="NotesHere API", version="1.0.0")

# --- UPDATED CORS SETTINGS FOR FIREBASE ---
# Replace 'your-project-id' with your actual Firebase Project ID
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://noteshere-frontend.web.app/",
        "https://noteshere-frontend.firebaseapp.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BUCKET_NAME = "notes-files"
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".docx", ".doc"}


def get_file_extension(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def get_public_url(file_path: str) -> str:
    result = supabase.storage.from_(BUCKET_NAME).get_public_url(file_path)
    return result


# ──────────────────────────── UPLOAD ────────────────────────────


@app.post("/api/notes/upload")
async def upload_note(
    title: str = Form(...),
    subject: str = Form(...),
    author: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
):
    ext = get_file_extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    file_id = str(uuid.uuid4())
    storage_path = f"{file_id}{ext}"

    contents = await file.read()
    file_size = len(contents)

    # Upload to Supabase Storage
    supabase.storage.from_(BUCKET_NAME).upload(
        storage_path,
        contents,
        file_options={"content-type": file.content_type},
    )

    file_url = get_public_url(storage_path)

    # Determine a human‑friendly file type label
    type_map = {
        ".pdf": "PDF",
        ".png": "Image",
        ".jpg": "Image",
        ".jpeg": "Image",
        ".gif": "Image",
        ".docx": "Word",
        ".doc": "Word",
    }
    file_type = type_map.get(ext, "Other")

    # Save metadata to Supabase DB
    note_data = {
        "id": file_id,
        "title": title,
        "subject": subject,
        "author": author,
        "description": description,
        "file_name": file.filename,
        "file_url": file_url,
        "file_type": file_type,
        "file_size": file_size,
        "created_at": datetime.utcnow().isoformat(),
    }

    try:
        result = supabase.table("notes").insert(note_data).execute()
    except Exception as e:
        print(f"DB INSERT ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Note uploaded successfully", "note": result.data[0]}


# ──────────────────────────── LIST ──────────────────────────────


@app.get("/api/notes")
async def list_notes(search: str = "", subject: str = ""):
    query = supabase.table("notes").select("*").order("created_at", desc=True)

    if search:
        query = query.or_(
            f"title.ilike.%{search}%,author.ilike.%{search}%,description.ilike.%{search}%"
        )

    if subject:
        query = query.eq("subject", subject)

    result = query.execute()
    return {"notes": result.data}


# ──────────────────────────── GET ONE ───────────────────────────


@app.get("/api/notes/{note_id}")
async def get_note(note_id: str):
    result = supabase.table("notes").select("*").eq("id", note_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Note not found")

    return {"note": result.data[0]}


# ──────────────────────────── DELETE ────────────────────────────


@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: str):
    # Get note to find the storage path
    result = supabase.table("notes").select("*").eq("id", note_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Note not found")

    note = result.data[0]

    # Determine the storage path from file_name extension
    ext = get_file_extension(note["file_name"])
    storage_path = f"{note_id}{ext}"

    # Delete from storage
    supabase.storage.from_(BUCKET_NAME).remove([storage_path])

    # Delete from DB
    supabase.table("notes").delete().eq("id", note_id).execute()

    return {"message": "Note deleted successfully"}


# ──────────────────────────── HEALTH ────────────────────────────


@app.get("/api/health")
async def health():
    return {"status": "ok"}
