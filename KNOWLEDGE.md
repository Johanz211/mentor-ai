# Mentor AI — Knowledge Base

> A comprehensive guide for developers picking up this project.

## Architecture Overview

```
mentor-ai/
├── mentor.py            # Entry point: --mode web | cli
├── app/
│   ├── server.py        # FastAPI backend (all API endpoints)
│   ├── cli.py           # Terminal chat mode (Rich-powered)
│   ├── mentors.py       # Mentor persona definitions
│   ├── db.py            # SQLite persistence layer
│   ├── file_parser.py   # PDF / DOCX / code file parser
│   └── static/
│       ├── index.html   # Single-page web UI
│       ├── style.css    # Dark theme
│       └── app.js       # Frontend logic (vanilla JS)
├── data/
│   └── mentor.db        # SQLite database (auto-created)
├── uploads/             # Uploaded files stored here
├── healthcheck.sh       # Auto-restart script (cron)
├── requirements.txt     # Python dependencies
└── KNOWLEDGE.md         # This file
```

## Tech Stack

| Layer     | Tech                                       |
|-----------|--------------------------------------------|
| LLM       | Ollama (local) with `qwen2.5-coder:14b`   |
| Backend   | FastAPI + uvicorn (port 8888, 0.0.0.0)     |
| Frontend  | Vanilla HTML/CSS/JS (no build step)        |
| CLI       | Rich + httpx (streaming)                   |
| DB        | SQLite with WAL mode                       |
| Files     | PyPDF2, python-docx for parsing            |

## How It Works

### Chat Flow (Web)
1. User selects a mentor → frontend loads persisted history from `/api/history/{mentor}`
2. User sends message → `POST /api/chat` with `{mentor, message}`
3. Server builds context: system prompt + file contents + last 20 messages from DB
4. Server streams response from Ollama → SSE to frontend
5. Both user message and assistant response are saved to SQLite

### Chat Flow (CLI)
1. `mentor --mode cli` launches Rich-based terminal
2. On startup, loads history from SQLite for the active mentor
3. `/switch <name>` changes mentor and loads its history
4. Messages saved to same SQLite DB as web UI (shared history)

### File Uploads
- Files are scoped per mentor (each mentor has its own file list)
- Uploaded via `POST /api/upload` with `mentor` form field
- Parsed once (PyPDF2/docx/plaintext), content cached in memory
- File metadata stored in SQLite, actual files in `uploads/`
- File content is injected into LLM system prompt as reference

### Persistence
- **Database**: `data/mentor.db` (SQLite, WAL mode)
- **Tables**:
  - `chat_messages`: id, mentor, role, content, timestamp
  - `uploaded_files`: id, name, path, size, mentor, uploaded_at
- **One conversation per mentor** — no sessions, no "new chat"
- **Context window**: Last 20 messages sent to LLM (all stored in DB)
- **History survives** server restarts, CLI/web switches
- Web and CLI share the same database

## How to Add a New Mentor

Edit `app/mentors.py` and add an entry to the `MENTORS` dict:

```python
"your_key": {
    "name": "Display Name",
    "icon": "🎯",
    "description": "Short description shown in sidebar",
    "system_prompt": """You are an expert in X.
    Explain concepts clearly with examples.
    Use analogies when helpful.
    Format code blocks with language tags.""",
}
```

Then add quick-start prompts in `app/static/app.js` in the `QUICK_STARTS` object:

```javascript
your_key: [
    "Example question 1?",
    "Example question 2?",
    "Example question 3?",
],
```

No restart needed for the backend (dict is read at import time, so restart the server).

## Current Mentors

| Key        | Name                | Focus                                     |
|------------|---------------------|--------------------------------------------|
| embedded   | Embedded & EE       | STM32, registers, C, circuits, CAN, SPI   |
| qa         | QA Automation       | Selenium, pytest, CI/CD, test strategy     |
| leetcode   | LeetCode Coach      | DSA, patterns, complexity, interview prep  |
| mechanical | Mechanical Eng      | Thermo, FEA, GD&T, manufacturing          |
| vcs        | Version Control     | Git, GitHub, branching, CI/CD workflows    |

## API Endpoints

| Method | Path                    | Description                        |
|--------|-------------------------|------------------------------------|
| GET    | `/api/mentors`          | List all mentors                   |
| GET    | `/api/history/{mentor}` | Get chat history for a mentor      |
| POST   | `/api/chat`             | Send message (streaming response)  |
| POST   | `/api/clear`            | Clear chat history for a mentor    |
| POST   | `/api/upload`           | Upload file (scoped to mentor)     |
| GET    | `/api/files/{mentor}`   | List uploaded files for a mentor   |
| DELETE | `/api/files/{file_id}`  | Delete an uploaded file            |
| GET    | `/health`               | Health check endpoint              |

## Configuration

- **Port**: 8888 (change in `mentor.py`)
- **Ollama URL**: `http://localhost:11434` (change in `server.py` and `cli.py`)
- **Model**: `qwen2.5-coder:14b` (change in `server.py` and `cli.py`)
- **DB path**: `data/mentor.db` (change in `db.py`)
- **Context limit**: 20 messages (change in `server.py` line ~129 and `cli.py`)

## Running

```bash
# Web UI (default)
mentor              # alias in ~/.bashrc
# or
python mentor.py --mode web

# CLI mode
mentor --mode cli
# or
python mentor.py --mode cli

# Health check
./healthcheck.sh status
./healthcheck.sh restart
```

## Cron Jobs

```
*/3 * * * * /home/johannes/mentor-ai/healthcheck.sh check >> /home/johannes/mentor-ai/healthcheck.log 2>&1
```

## Design Decisions

1. **No sessions** — One continuous conversation per mentor. Simpler mental model, better context retention for learning.
2. **SQLite over PostgreSQL** — Single-user app, no need for a DB server. WAL mode handles concurrent CLI + web access.
3. **Vanilla JS** — No build step, no node_modules. Fast to iterate, easy to understand.
4. **Local LLM** — Privacy, no API costs, works offline. Trade-off: slower than cloud APIs.
5. **Streaming** — SSE for web, line-by-line for CLI. Makes responses feel fast even with local LLM.
6. **File content in system prompt** — Simple approach. Works well under ~32K context. For larger codebases, would need RAG.
7. **Per-mentor files** — Each mentor gets its own file context. An embedded C file doesn't pollute the QA mentor.

## Known Limitations

- **Context window**: qwen2.5-coder:14b has ~32K tokens. Very large files or long conversations may hit limits.
- **No RAG**: File content is injected wholesale into system prompt. For large codebases, chunking + vector search would be better.
- **No auth**: Anyone on the network can access the UI. Add a reverse proxy with auth for production.
- **Single model**: All mentors use the same LLM. Could add per-mentor model config for specialized models.

## Enhancement Ideas

- [ ] RAG with chromadb for large file collections
- [ ] Per-mentor model selection (e.g., codellama for code, mistral for general)
- [ ] Export chat history as markdown
- [ ] Quiz mode — mentor asks questions to test understanding
- [ ] Progress tracking — what topics have been covered
- [ ] Code execution sandbox — run code snippets in the chat
- [ ] Voice input/output with whisper + TTS
- [ ] Mobile-responsive UI improvements
