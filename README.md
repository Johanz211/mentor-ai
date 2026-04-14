# Mentor AI

Your personal learning companion powered by a local LLM (Ollama). Chat with domain-specific mentors, upload reference files, generate flashcards with spaced repetition — all running locally on your machine.

## Mentors

- 🔌 **Embedded Systems & EE** — C, STM32, ARM, RTOS, CAN/SPI/I2C, circuits
- 🧪 **QA & Test Automation** — Selenium, Playwright, CI/CD, API testing, strategy
- 💻 **LeetCode & DSA** — Algorithms, patterns, Big O, interview prep
- ⚙️ **Mechanical Engineering** — Thermodynamics, materials, FEA, CAD, GD&T
- 🔀 **Version Control & Git** — Git, GitHub, branching strategies, CI/CD
- 💬 **Personal Companion** — Chat, advice, consolation, general knowledge *(uses 7B model for speed)*
- 🐛 **Debug / Sandbox** — For testing & experiments only *(uses 7B model)*

> ⚠️ **IMPORTANT:** Always use the **🐛 Debug** mentor for testing and experiments.
> Never run test/debug operations against real mentors — chat history **cannot be recovered** once cleared.

## Features

- **Web UI** — Chat interface with mentor selection, file uploads, markdown + code highlighting
- **CLI mode** — Interactive terminal chat with streaming responses
- **Chat persistence** — Conversations saved to SQLite, restored on reload (shared between web & CLI)
- **RAG Retrieval** — Uploaded files are chunked and indexed with FTS5/BM25; only relevant sections are injected into context (handles 800+ page PDFs efficiently)
- **Query Expansion** — User questions are analysed to extract key terms and expand with synonyms before searching file chunks
- **Per-mentor models** — Mentors can specify their own model (e.g. companion uses 7B for speed, others use 14B)
- **🃏 Flashcards** — Generate cards from chat history, manual creation, SM-2 spaced repetition
- **Auto Flashcards** — Background cron generates flashcards every 4 hours from new chat history (configurable via `AUTO_FC_HOURS`)
- **Streaming** — Real-time token-by-token responses
- **Health check** — Auto-restart via cron if server goes down
- **Customizable** — Add new mentors by editing `app/mentors.py`

## Quick Start

```bash
git clone https://github.com/Johanz211/mentor-ai.git
cd mentor-ai
bash setup.sh
```

`setup.sh` handles everything:
- Creates Python venv and installs dependencies
- Adds `mentor` and `mentor-cli` shell aliases to `~/.bashrc`
- Sets up healthcheck cron job (every 3 min)
- Creates required directories (`data/`, `uploads/`, `logs/`)
- Verifies Ollama and model availability

After setup, open a new terminal (or `source ~/.bashrc`):

```bash
mentor              # Start web UI at http://localhost:8888
mentor-cli          # Terminal chat mode
mentor-cli -m qa    # Jump straight to QA mentor
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.ai) running locally:
  ```bash
  ollama pull qwen2.5-coder:14b
  ```

## Usage

```bash
mentor                         # Web UI on port 8888
mentor web -p 9000             # Web UI on custom port
mentor cli                     # Terminal chat
mentor cli -m embedded         # Jump to specific mentor
mentor cli --model llama3:8b   # Use a different model
```

### CLI Commands (inside chat)

| Command | Action |
|---------|--------|
| `/file <path>` | Load a file for context |
| `/files` | List loaded files |
| `/switch` | Change mentor |
| `/clear` | Reset chat history |
| `/quit` | Exit |

### Flashcards

Click the 🃏 button in the web UI header to:
- **Generate from Chat** — LLM extracts key concepts as Q&A cards
- **Add manually** — Create your own question/answer pairs
- **Review** — Flip cards, grade yourself (Again/Hard/Good/Easy)
- **Spaced repetition** — Cards reappear based on SM-2 scheduling

### Health Check

```bash
./healthcheck.sh status    # Check if server is running
./healthcheck.sh restart   # Restart the server
./healthcheck.sh stop      # Stop the server
```

Cron runs `healthcheck.sh check` every 3 minutes to auto-restart if down.

## Adding a New Mentor

Edit `app/mentors.py` and add an entry to the `MENTORS` dict:

```python
"your_mentor": {
    "name": "Display Name",
    "icon": "🎯",
    "description": "Short description for sidebar",
    "model": "qwen2.5-coder:7b",      # optional — override default model
    "system_prompt": "Detailed instructions for the LLM...",
}
```

Add quick-start prompts in `app/static/app.js` in the `QUICK_STARTS` object.

## Architecture

```
mentor-ai/
├── mentor.py           # Entry point (--mode web | cli)
├── setup.sh            # One-command setup (venv, aliases, cron)
├── healthcheck.sh      # Auto-restart script
├── app/
│   ├── server.py       # FastAPI backend (chat, files, flashcards, auto-cron, SSE)
│   ├── cli.py          # Terminal chat mode
│   ├── db.py           # SQLite persistence (chat, files, flashcards, FTS5 chunks)
│   ├── mentors.py      # Mentor persona definitions (with per-mentor model support)
│   ├── retriever.py    # Chunking, query expansion, BM25 retrieval (RAG)
│   ├── file_parser.py  # PDF/DOCX/code file parsing
│   └── static/         # Web UI (HTML/CSS/JS)
├── data/               # SQLite database (auto-created)
├── uploads/            # Uploaded files storage
├── KNOWLEDGE.md        # Detailed project documentation
└── requirements.txt
```

See [KNOWLEDGE.md](KNOWLEDGE.md) for detailed architecture, API reference, design decisions, and enhancement ideas.
