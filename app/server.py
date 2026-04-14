"""FastAPI server for Mentor AI — chat, file upload, streaming."""

import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
import httpx

from .mentors import MENTORS
from .file_parser import parse_file

app = FastAPI(title="Mentor AI")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")

STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory state
file_store = {}  # {id: {name, content, path, size}}
sessions = {}    # {session_id: {mentor, messages}}

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
async def list_files():
    return [{"id": k, "name": v["name"], "size": v["size"]} for k, v in file_store.items()]


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())[:8]
    content_bytes = await file.read()

    file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(content_bytes)

    text_content = parse_file(file.filename, content_bytes)

    file_store[file_id] = {
        "name": file.filename,
        "content": text_content,
        "path": str(file_path),
        "size": len(content_bytes),
    }

    return {"id": file_id, "name": file.filename, "size": len(content_bytes)}


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    if file_id in file_store:
        path = file_store[file_id]["path"]
        if os.path.exists(path):
            os.remove(path)
        del file_store[file_id]
        return {"ok": True}
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    mentor_key = body.get("mentor", "embedded")
    message = body.get("message", "")
    session_id = body.get("session_id", "default")
    file_ids = body.get("file_ids", [])

    if session_id not in sessions:
        sessions[session_id] = {"mentor": mentor_key, "messages": []}
    session = sessions[session_id]

    # Reset history if mentor changed
    if session["mentor"] != mentor_key:
        session["mentor"] = mentor_key
        session["messages"] = []

    # Build system prompt
    mentor = MENTORS.get(mentor_key, MENTORS["embedded"])
    system_prompt = mentor["system_prompt"]

    # Attach file context
    files_to_include = []
    if file_ids:
        files_to_include = [(fid, file_store[fid]) for fid in file_ids if fid in file_store]
    elif file_store:
        files_to_include = list(file_store.items())

    if files_to_include:
        file_context = "\n\n--- REFERENCE FILES (uploaded by student) ---\n"
        for fid, f in files_to_include:
            # Truncate large files to stay within context window
            content = f["content"][:6000]
            truncated = " [truncated]" if len(f["content"]) > 6000 else ""
            file_context += f"\n### File: {f['name']}{truncated}\n```\n{content}\n```\n"
        system_prompt += file_context

    session["messages"].append({"role": "user", "content": message})

    # Keep last 20 messages to avoid context overflow
    recent = session["messages"][-20:]
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

            session["messages"].append({"role": "assistant", "content": response_text})
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/clear")
async def clear_chat(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "default")
    if session_id in sessions:
        sessions[session_id]["messages"] = []
    return {"ok": True}
