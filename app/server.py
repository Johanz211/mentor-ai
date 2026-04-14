"""FastAPI server for Mentor AI — chat, file upload, streaming."""

import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
import httpx

from .mentors import MENTORS
from .file_parser import parse_file
from . import db

app = FastAPI(title="Mentor AI")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")

STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory cache for file content (text parsed from uploads)
# Metadata lives in SQLite; content is parsed fresh or cached here
_file_content_cache = {}


def _load_file_content(file_id: str, filepath: str, filename: str) -> str:
    """Load and cache parsed file content."""
    if file_id in _file_content_cache:
        return _file_content_cache[file_id]
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            text = parse_file(filename, f.read())
        _file_content_cache[file_id] = text
        return text
    return ""


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/mentors")
async def list_mentors():
    return {
        k: {"name": v["name"], "icon": v["icon"], "description": v["description"]}
        for k, v in MENTORS.items()
    }


@app.get("/api/files")
async def list_files(mentor: str = ""):
    files = db.get_files(mentor)
    return [{"id": f["id"], "name": f["name"], "size": f["size"], "mentor": f["mentor"]} for f in files]


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), mentor: str = Form("")):
    file_id = str(uuid.uuid4())[:8]
    content_bytes = await file.read()

    file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(content_bytes)

    text_content = parse_file(file.filename, content_bytes)
    _file_content_cache[file_id] = text_content

    db.save_file_meta(file_id, file.filename, str(file_path), len(content_bytes), mentor)

    return {"id": file_id, "name": file.filename, "size": len(content_bytes), "mentor": mentor}


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    files = db.get_files()
    match = [f for f in files if f["id"] == file_id]
    if match:
        path = match[0]["path"]
        if os.path.exists(path):
            os.remove(path)
        db.delete_file_meta(file_id)
        _file_content_cache.pop(file_id, None)
        return {"ok": True}
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.get("/api/history/{mentor}")
async def get_history(mentor: str):
    """Get full chat history for a mentor (for UI restore on load)."""
    messages = db.get_history(mentor, limit=200)
    count = db.get_message_count(mentor)
    return {"mentor": mentor, "messages": messages, "total": count}


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    mentor_key = body.get("mentor", "embedded")
    message = body.get("message", "")

    # Build system prompt
    mentor = MENTORS.get(mentor_key, MENTORS["embedded"])
    system_prompt = mentor["system_prompt"]

    # Attach file context — only files belonging to this mentor
    mentor_files = db.get_files(mentor_key)
    if mentor_files:
        file_context = "\n\n--- REFERENCE FILES (uploaded by student) ---\n"
        for f in mentor_files:
            content = _load_file_content(f["id"], f["path"], f["name"])
            content = content[:6000]
            truncated = " [truncated]" if len(content) >= 6000 else ""
            file_context += f"\n### File: {f['name']}{truncated}\n```\n{content}\n```\n"
        system_prompt += file_context

    # Save user message to DB
    db.save_message(mentor_key, "user", message)

    # Build LLM context: system prompt + recent history (last 20 messages)
    recent = db.get_recent_history(mentor_key, limit=20)
    messages = [{"role": "system", "content": system_prompt}] + recent

    async def generate():
        response_text = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/chat",
                    json={"model": OLLAMA_MODEL, "messages": messages, "stream": True},
                ) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                response_text += token
                                yield f"data: {json.dumps({'token': token})}\n\n"

            # Save assistant response to DB
            db.save_message(mentor_key, "assistant", response_text)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/clear")
async def clear_chat(request: Request):
    body = await request.json()
    mentor = body.get("mentor", "")
    if mentor:
        db.clear_history(mentor)
    return {"ok": True}
