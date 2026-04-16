"""FastAPI server for Mentor AI — chat, file upload, streaming."""

import os
import json
import uuid
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
import httpx

from .mentors import MENTORS
from .file_parser import parse_file
from . import db
from . import retriever

logger = logging.getLogger("mentor-ai")

app = FastAPI(title="Mentor AI")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL_PREFERRED = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:14b")
OLLAMA_MODEL_FALLBACK = "qwen2.5-coder:7b"


def _detect_model() -> str:
    """Use preferred model if available, otherwise fall back."""
    try:
        resp = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        names = [m["name"] for m in resp.json().get("models", [])]
        if OLLAMA_MODEL_PREFERRED in names or OLLAMA_MODEL_PREFERRED.split(":")[0] in [n.split(":")[0] for n in names if OLLAMA_MODEL_PREFERRED in n]:
            return OLLAMA_MODEL_PREFERRED
        # Check without tag (ollama may list as "qwen2.5-coder:14b" or just match prefix)
        for n in names:
            if n.startswith(OLLAMA_MODEL_PREFERRED.split(":")[0]) and OLLAMA_MODEL_PREFERRED.split(":")[1] in n:
                return n
        if OLLAMA_MODEL_FALLBACK in names or any(OLLAMA_MODEL_FALLBACK in n for n in names):
            return OLLAMA_MODEL_FALLBACK
    except Exception:
        pass
    return OLLAMA_MODEL_PREFERRED  # hope for the best


OLLAMA_MODEL = _detect_model()

STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# In-memory cache for file content (text parsed from uploads)
# Metadata lives in SQLite; content is parsed fresh or cached here
_file_content_cache = {}

# Phrases that explicitly trigger RAG file search
_RAG_TRIGGERS = [
    "from the file", "from the manual", "from the doc", "from the pdf",
    "from the reference", "check the file", "check the doc", "check the manual",
    "in the file", "in the manual", "in the doc", "in the pdf",
    "in the reference", "look up", "search the",
]
# Patterns that auto-trigger RAG (register names, hex addresses, section refs)
import re as _re
_RAG_AUTO_PATTERNS = _re.compile(
    r'0x[0-9a-fA-F]{4,}'          # hex addresses (0x40020000)
    r'|[A-Z]{2,}_[A-Z]{2,}'       # register-style names (GPIO_MODER, RCC_AHB1ENR)
    r'|section\s+\d+\.\d+'        # section references (section 2.3.1)
    r'|register\s+\w+'            # "register FLASH_CR"
    r'|RM0368',                    # specific reference manual ID
    _re.IGNORECASE
)


def _should_use_rag(message: str) -> bool:
    """Determine if RAG retrieval should be used for this message."""
    msg_lower = message.lower()
    # Explicit trigger phrases
    if any(trigger in msg_lower for trigger in _RAG_TRIGGERS):
        return True
    # Auto-detect: register names, hex addresses, section references
    if _RAG_AUTO_PATTERNS.search(message):
        return True
    return False


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
    result = {}
    for k, v in MENTORS.items():
        info = {"name": v["name"], "icon": v["icon"], "description": v["description"]}
        if "model" in v:
            info["model"] = v["model"]
        result[k] = info
    return result


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

    # Chunk and index for retrieval
    num_chunks = retriever.index_file(file_id, mentor, file.filename, text_content)
    logger.info(f"Indexed {file.filename}: {num_chunks} chunks for [{mentor}]")

    return {
        "id": file_id, "name": file.filename,
        "size": len(content_bytes), "mentor": mentor,
        "chunks": num_chunks,
    }


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str):
    files = db.get_files()
    match = [f for f in files if f["id"] == file_id]
    if match:
        path = match[0]["path"]
        if os.path.exists(path):
            os.remove(path)
        db.delete_file_meta(file_id)
        retriever.remove_file(file_id)
        _file_content_cache.pop(file_id, None)
        return {"ok": True}
    return JSONResponse({"error": "Not found"}, status_code=404)


@app.post("/api/reindex")
async def reindex_files(request: Request):
    """Re-chunk and re-index all existing uploaded files."""
    body = await request.json()
    mentor = body.get("mentor", "")
    files = db.get_files(mentor)
    total_chunks = 0
    for f in files:
        content = _load_file_content(f["id"], f["path"], f["name"])
        if content:
            n = retriever.index_file(f["id"], f["mentor"], f["name"], content)
            total_chunks += n
    return {"ok": True, "files": len(files), "chunks": total_chunks}


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

    # RAG retrieval — only when explicitly requested or auto-detected
    use_rag = _should_use_rag(message)
    mentor_files = db.get_files(mentor_key)
    if mentor_files and use_rag:
        chunk_context = retriever.build_context(message, mentor_key)
        if chunk_context:
            system_prompt += chunk_context

    # Save user message to DB
    db.save_message(mentor_key, "user", message)

    # Build LLM context: system prompt + recent history (last 20 messages)
    recent = db.get_recent_history(mentor_key, limit=20)
    messages = [{"role": "system", "content": system_prompt}] + recent

    # Use per-mentor model if specified, otherwise default
    chat_model = mentor.get("model", OLLAMA_MODEL)

    async def generate():
        response_text = ""
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/chat",
                    json={"model": chat_model, "messages": messages, "stream": True},
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


# ── Flashcards ──

@app.get("/api/flashcards/{mentor}")
async def list_flashcards(mentor: str):
    cards = db.get_flashcards(mentor)
    stats = db.get_flashcard_stats(mentor)
    return {"cards": cards, "stats": stats}


@app.get("/api/flashcards/{mentor}/due")
async def due_flashcards(mentor: str):
    cards = db.get_due_flashcards(mentor)
    stats = db.get_flashcard_stats(mentor)
    return {"cards": cards, "stats": stats}


@app.post("/api/flashcards")
async def create_flashcard(request: Request):
    body = await request.json()
    card_id = db.add_flashcard(body["mentor"], body["question"], body["answer"])
    return {"id": card_id, "ok": True}


@app.post("/api/flashcards/{card_id}/review")
async def review_flashcard(card_id: int, request: Request):
    body = await request.json()
    quality = body.get("quality", 2)  # 0=again, 1=hard, 2=good, 3=easy
    db.review_flashcard(card_id, quality)
    return {"ok": True}


@app.delete("/api/flashcards/{card_id}")
async def delete_flashcard(card_id: int):
    db.delete_flashcard(card_id)
    return {"ok": True}


@app.post("/api/flashcards/{mentor}/generate")
async def generate_flashcards(mentor: str):
    """Use LLM to extract flashcards from recent chat history."""
    history = db.get_recent_history(mentor, limit=40)
    if not history:
        return {"cards": [], "message": "No chat history to generate from"}

    # Build conversation text for LLM
    conv_text = ""
    for msg in history:
        role = "Student" if msg["role"] == "user" else "Mentor"
        conv_text += f"{role}: {msg['content']}\n\n"

    prompt = f"""Analyze this conversation and extract 3-5 flashcards for studying.
Each flashcard should test ONE specific concept discussed.

Rules:
- Question should be specific and testable (not vague)
- Answer should be concise (1-3 sentences max)
- Focus on facts, definitions, code patterns, and key concepts
- Output ONLY valid JSON array, no other text

Format:
[{{"q": "What does 0xFF represent in binary?", "a": "0xFF = 0b11111111 (all 8 bits set to 1), decimal 255"}}]

Conversation:
{conv_text[:4000]}

JSON output:"""

    mentor_def = MENTORS.get(mentor, {})
    fc_model = mentor_def.get("model", OLLAMA_MODEL)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": fc_model, "prompt": prompt, "stream": False},
            )
            raw = resp.json().get("response", "")

            # Parse JSON from response (handle markdown code blocks)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()

            cards = json.loads(raw)
            created = []
            for card in cards:
                if "q" in card and "a" in card:
                    cid = db.add_flashcard(mentor, card["q"], card["a"])
                    created.append({"id": cid, "question": card["q"], "answer": card["a"]})

            return {"cards": created, "count": len(created)}

    except Exception as e:
        return JSONResponse({"error": f"Generation failed: {str(e)}"}, status_code=500)


# ── Auto Flashcard Cron ──

AUTO_FC_INTERVAL = int(os.environ.get("AUTO_FC_HOURS", "4")) * 3600  # default 4 hours
AUTO_FC_MIN_MESSAGES = 6  # need at least 6 new messages (3 exchanges) to generate


async def _auto_generate_for_mentor(mentor_key: str):
    """Generate flashcards from new messages for a single mentor."""
    cursor = db.get_fc_cursor(mentor_key)
    new_msgs, max_id = db.get_new_messages(mentor_key, cursor, limit=40)

    if len(new_msgs) < AUTO_FC_MIN_MESSAGES:
        return 0

    conv_text = ""
    for msg in new_msgs:
        role = "Student" if msg["role"] == "user" else "Mentor"
        conv_text += f"{role}: {msg['content']}\n\n"

    prompt = f"""Analyze this conversation and extract 3-5 flashcards for studying.
Each flashcard should test ONE specific concept discussed.

Rules:
- Question should be specific and testable (not vague)
- Answer should be concise (1-3 sentences max)
- Focus on facts, definitions, code patterns, and key concepts
- Do NOT create duplicate or near-duplicate cards
- Output ONLY valid JSON array, no other text

Format:
[{{"q": "What does 0xFF represent in binary?", "a": "0xFF = 0b11111111 (all 8 bits set to 1), decimal 255"}}]

Conversation:
{conv_text[:4000]}

JSON output:"""

    mentor_def = MENTORS.get(mentor_key, {})
    fc_model = mentor_def.get("model", OLLAMA_MODEL)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": fc_model, "prompt": prompt, "stream": False},
            )
            raw = resp.json().get("response", "")

            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()

            cards = json.loads(raw)
            count = 0
            for card in cards:
                if "q" in card and "a" in card:
                    db.add_flashcard(mentor_key, card["q"], card["a"])
                    count += 1

            # Update cursor so we don't reprocess these messages
            db.set_fc_cursor(mentor_key, max_id)
            return count

    except Exception as e:
        logger.warning(f"Auto flashcard generation failed for {mentor_key}: {e}")
        return 0


async def _auto_fc_loop():
    """Background loop that generates flashcards periodically."""
    await asyncio.sleep(30)  # initial delay to let server settle
    logger.info(f"Auto flashcard cron started (every {AUTO_FC_INTERVAL // 3600}h)")

    while True:
        try:
            mentors_with_chat = db.get_all_mentors_with_messages()
            total = 0
            for mk in mentors_with_chat:
                count = await _auto_generate_for_mentor(mk)
                if count > 0:
                    logger.info(f"Auto-generated {count} flashcards for [{mk}]")
                    total += count
            if total > 0:
                logger.info(f"Auto flashcard cron: {total} cards created across {len(mentors_with_chat)} mentors")
        except Exception as e:
            logger.warning(f"Auto flashcard cron error: {e}")

        await asyncio.sleep(AUTO_FC_INTERVAL)


_auto_fc_task = None


@app.on_event("startup")
async def startup_auto_fc():
    global _auto_fc_task
    _auto_fc_task = asyncio.create_task(_auto_fc_loop())


@app.on_event("shutdown")
async def shutdown_auto_fc():
    if _auto_fc_task:
        _auto_fc_task.cancel()
